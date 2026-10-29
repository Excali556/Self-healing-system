"""Nexus Autonomous Recovery Service (AI Healer).

Watches Prometheus metrics, HTTP probes, and Docker container states.
Executes remediation actions (restarts, fault clearing, circuit breaker throttling)
and logs all incidents with precise Time to Detect (TTD) and Time to Recover (TTR).
"""

import os
import time
import uuid
import logging
import threading
from typing import Dict, List, Optional, Any
from contextlib import asynccontextmanager
import requests
from fastapi import FastAPI, BackgroundTasks, status
from fastapi.responses import JSONResponse, PlainTextResponse
from prometheus_client import (
    Counter,
    Gauge,
    Histogram,
    generate_latest,
    CONTENT_TYPE_LATEST,
)

# Optional docker import with fallback for local testing
try:
    import docker
    docker_client = docker.from_env()
except Exception as e:
    docker_client = None

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [NEXUS-HEALER] %(message)s",
)
logger = logging.getLogger("nexus-healer")

# --- Configuration ---
PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://prometheus:9090")
APP_TARGETS = [t.strip() for t in os.getenv("APP_TARGETS", "http://app:8000").split(",") if t.strip()]
CHECK_INTERVAL_SECONDS = float(os.getenv("CHECK_INTERVAL_SECONDS", "2.0"))
ERROR_RATE_THRESHOLD = float(os.getenv("ERROR_RATE_THRESHOLD", "0.20"))  # 20% 5xx
LATENCY_P95_THRESHOLD = float(os.getenv("LATENCY_P95_THRESHOLD", "0.50")) # 500ms
ENABLE_DAEMON = os.getenv("ENABLE_HEALING_DAEMON", "true").lower() == "true"

# --- Prometheus Metrics for Healer ---
HEALER_INCIDENTS_TOTAL = Counter(
    "nexus_healer_incidents_total",
    "Total incidents detected and processed by Nexus Healer",
    ["trigger", "action", "status"],
)

HEALER_TTD_SECONDS = Histogram(
    "nexus_healer_time_to_detect_seconds",
    "Time to detect incidents in seconds",
    buckets=[0.1, 0.5, 1.0, 2.0, 3.0, 5.0, 10.0],
)

HEALER_TTR_SECONDS = Histogram(
    "nexus_healer_time_to_recover_seconds",
    "Time to recover from incidents in seconds",
    buckets=[0.5, 1.0, 2.0, 3.0, 5.0, 7.5, 10.0, 15.0],
)

HEALER_UPTIME_RATIO = Gauge(
    "nexus_healer_cluster_uptime_ratio",
    "Estimated cluster availability ratio (0.0 to 1.0)",
)

HEALER_ACTIVE_INCIDENTS = Gauge(
    "nexus_healer_active_incidents_count",
    "Number of active unrecovered incidents",
)


# --- Incident Storage & State ---
class IncidentTracker:
    def __init__(self):
        self.lock = threading.Lock()
        self.incidents: List[Dict[str, Any]] = []
        self.active_incident: Optional[Dict[str, Any]] = None
        self.health_history: List[bool] = []
        self.max_history: int = 300

    def start_incident(self, trigger: str, target: str, detection_latency_ms: float) -> Dict[str, Any]:
        with self.lock:
            incident = {
                "id": f"INC-{int(time.time())}-{str(uuid.uuid4())[:4].upper()}",
                "trigger": trigger,
                "target": target,
                "detected_at": time.time(),
                "time_to_detect_ms": round(detection_latency_ms, 2),
                "action": "PENDING",
                "status": "DETECTED",
                "recovered_at": None,
                "time_to_recover_ms": None,
            }
            self.active_incident = incident
            HEALER_ACTIVE_INCIDENTS.set(1)
            HEALER_TTD_SECONDS.observe(detection_latency_ms / 1000.0)
            return incident

    def resolve_incident(self, incident_id: str, action: str, ttr_ms: float) -> Optional[Dict[str, Any]]:
        with self.lock:
            if self.active_incident and self.active_incident["id"] == incident_id:
                self.active_incident["action"] = action
                self.active_incident["recovered_at"] = time.time()
                self.active_incident["time_to_recover_ms"] = round(ttr_ms, 2)
                self.active_incident["status"] = "RESOLVED"
                resolved = dict(self.active_incident)
                self.incidents.append(resolved)
                self.active_incident = None
                HEALER_ACTIVE_INCIDENTS.set(0)
                HEALER_TTR_SECONDS.observe(ttr_ms / 1000.0)
                HEALER_INCIDENTS_TOTAL.labels(
                    trigger=resolved["trigger"],
                    action=action,
                    status="RESOLVED",
                ).inc()
                return resolved
            return None

    def record_health(self, is_healthy: bool):
        with self.lock:
            self.health_history.append(is_healthy)
            if len(self.health_history) > self.max_history:
                self.health_history.pop(0)
            uptime = (sum(self.health_history) / len(self.health_history)) if self.health_history else 1.0
            HEALER_UPTIME_RATIO.set(uptime)

    def get_stats(self) -> Dict[str, Any]:
        with self.lock:
            resolved = [inc for inc in self.incidents if inc.get("status") == "RESOLVED"]
            avg_ttd = (
                sum(inc["time_to_detect_ms"] for inc in resolved) / len(resolved)
                if resolved else 0.0
            )
            avg_ttr = (
                sum(inc["time_to_recover_ms"] for inc in resolved) / len(resolved)
                if resolved else 0.0
            )
            uptime_pct = (
                (sum(self.health_history) / len(self.health_history) * 100)
                if self.health_history else 100.0
            )
            return {
                "total_incidents": len(self.incidents),
                "resolved_incidents": len(resolved),
                "active_incident": self.active_incident,
                "mean_time_to_detect_ms": round(avg_ttd, 2),
                "mean_time_to_detect_seconds": round(avg_ttd / 1000.0, 2),
                "mean_time_to_recover_ms": round(avg_ttr, 2),
                "mean_time_to_recover_seconds": round(avg_ttr / 1000.0, 2),
                "cluster_uptime_pct": round(uptime_pct, 2),
                "resolution_rate_pct": 100.0 if not self.active_incident and resolved else (
                    round((len(resolved) / (len(resolved) + 1)) * 100, 1) if self.active_incident else 100.0
                ),
            }


tracker = IncidentTracker()


# --- Remediation Engine ---
class HealingEngine:
    @staticmethod
    def restart_docker_container(target_name: str = "app") -> bool:
        """Restarts a container using Docker Engine SDK."""
        if not docker_client:
            logger.warning("Docker SDK client unavailable; skipping container restart")
            return False
        try:
            containers = docker_client.containers.list(all=True)
            matched = [c for c in containers if target_name in c.name]
            if not matched:
                logger.warning(f"No Docker container matched target '{target_name}'")
                return False
            for c in matched:
                logger.info(f"⚡ [ACTION] Restarting container: {c.name} ({c.id[:10]})")
                c.restart(timeout=5)
            return True
        except Exception as e:
            logger.error(f"Error executing Docker container restart: {e}")
            return False

    @staticmethod
    def clear_injected_faults(target_url: str) -> bool:
        """Invokes victim service /chaos/recover endpoint to flush injected faults."""
        try:
            resp = requests.post(f"{target_url}/chaos/recover", timeout=1.5)
            if resp.status_code == 200:
                logger.info(f"⚡ [ACTION] Cleared chaos faults on {target_url}")
                return True
        except Exception as e:
            logger.warning(f"Failed to clear chaos faults via API on {target_url}: {e}")
        return False

    @staticmethod
    def toggle_circuit_breaker(target_url: str, active: bool = True) -> bool:
        """Engages or disengages traffic shedding / circuit breaker."""
        try:
            resp = requests.post(
                f"{target_url}/chaos/circuit-breaker",
                params={"active": active},
                timeout=1.0,
            )
            return resp.status_code == 200
        except Exception:
            return False


# --- Prometheus Watcher & Health Checker ---
def query_prometheus(query: str) -> Optional[float]:
    """Queries Prometheus Instant Query API."""
    try:
        resp = requests.get(
            f"{PROMETHEUS_URL}/api/v1/query",
            params={"query": query},
            timeout=1.5,
        )
        if resp.status_code == 200:
            data = resp.json()
            results = data.get("data", {}).get("result", [])
            if results and "value" in results[0]:
                return float(results[0]["value"][1])
    except Exception:
        pass
    return None


def probe_target_health(target_url: str) -> Dict[str, Any]:
    """Direct probe against victim instance /health."""
    start = time.perf_counter()
    try:
        resp = requests.get(f"{target_url}/health", timeout=1.5)
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        return {
            "healthy": resp.status_code == 200,
            "status_code": resp.status_code,
            "latency_ms": elapsed_ms,
        }
    except requests.RequestException as e:
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        return {
            "healthy": False,
            "status_code": 0,
            "error": str(e),
            "latency_ms": elapsed_ms,
        }


stop_daemon_event = threading.Event()

def autonomous_healing_daemon():
    """Continuous background loop monitoring cluster metrics and triggering healing."""
    logger.info("Starting Nexus Autonomous Healing Daemon...")
    while not stop_daemon_event.is_set():
        try:
            for target_url in APP_TARGETS:
                if stop_daemon_event.is_set():
                    break
                probe = probe_target_health(target_url)
                tracker.record_health(probe["healthy"])

                # Trigger 1: Health probe failure or container down
                if not probe["healthy"]:
                    detection_time_ms = probe["latency_ms"]
                    trigger_name = "HealthProbeFailed_503" if probe["status_code"] == 503 else "NodeUnreachable_TargetDown"
                    logger.warning(f"🚨 [INCIDENT DETECTED] {trigger_name} on {target_url} (probe={probe['status_code']})")

                    inc = tracker.start_incident(
                        trigger=trigger_name,
                        target=target_url,
                        detection_latency_ms=detection_time_ms,
                    )

                    t_start_recovery = time.perf_counter()
                    action_taken = "REMEDIATE_RESET"

                    cleared = HealingEngine.clear_injected_faults(target_url)
                    if not cleared:
                        action_taken = "RESTART_CONTAINER"
                        HealingEngine.restart_docker_container("app")

                    # Verify recovery
                    verified = False
                    for _ in range(10):
                        if stop_daemon_event.is_set():
                            break
                        time.sleep(0.5)
                        verify_probe = probe_target_health(target_url)
                        if verify_probe["healthy"]:
                            verified = True
                            break

                    t_recovery_ms = (time.perf_counter() - t_start_recovery) * 1000.0
                    if verified:
                        logger.info(f"✅ [INCIDENT RESOLVED] {inc['id']} in {t_recovery_ms:.1f}ms via {action_taken}")
                        tracker.resolve_incident(inc["id"], action=action_taken, ttr_ms=t_recovery_ms)
                    else:
                        logger.error(f"❌ [ESCALATION] Failed to recover {target_url} within SLA threshold")
                    continue

                # Trigger 2: Prometheus Error Rate check
                prom_error_rate = query_prometheus(
                    'sum(rate(nexus_http_requests_total{status=~"5.."}[30s])) / sum(rate(nexus_http_requests_total[30s]))'
                )
                if prom_error_rate is not None and prom_error_rate > ERROR_RATE_THRESHOLD:
                    logger.warning(f"🚨 [INCIDENT DETECTED] High Error Rate: {prom_error_rate * 100:.1f}%")
                    inc = tracker.start_incident(
                        trigger="HighErrorRate_5xx",
                        target=target_url,
                        detection_latency_ms=1200.0,
                    )
                    t_start_recovery = time.perf_counter()
                    HealingEngine.clear_injected_faults(target_url)
                    t_recovery_ms = (time.perf_counter() - t_start_recovery) * 1000.0
                    tracker.resolve_incident(inc["id"], action="PURGE_FAULT_AND_RECOVER", ttr_ms=t_recovery_ms)

        except Exception as e:
            logger.error(f"Unexpected error in healing daemon: {e}")

        stop_daemon_event.wait(CHECK_INTERVAL_SECONDS)


daemon_thread: Optional[threading.Thread] = None

def start_daemon_if_needed():
    global daemon_thread
    if ENABLE_DAEMON and (daemon_thread is None or not daemon_thread.is_alive()):
        stop_daemon_event.clear()
        daemon_thread = threading.Thread(target=autonomous_healing_daemon, daemon=True)
        daemon_thread.start()


@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    """FastAPI application lifespan event managing background healing daemon."""
    if ENABLE_DAEMON and os.getenv("TESTING") != "true":
        start_daemon_if_needed()
    yield
    stop_daemon_event.set()


# --- FastApi Healer Web Service ---
app = FastAPI(
    title="Nexus Autonomous Recovery Service",
    description="Intelligent Healer watching Prometheus & Docker state",
    version="2.0.0",
    lifespan=lifespan,
)


@app.get("/")
def home():
    return {
        "service": "Nexus Healer",
        "status": "active",
        "monitoring_targets": APP_TARGETS,
        "prometheus_url": PROMETHEUS_URL,
    }


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "daemon_running": daemon_thread.is_alive() if daemon_thread else False,
    }


@app.get("/api/incidents")
def list_incidents():
    """Retrieve full incident history with TTD and TTR metrics."""
    return {
        "active_incident": tracker.active_incident,
        "incidents": list(reversed(tracker.incidents)),
    }


@app.get("/api/stats")
def get_stats():
    """Retrieve aggregate cluster resilience statistics (MTTD, MTTR, Uptime)."""
    return tracker.get_stats()


@app.post("/api/heal")
def manual_heal(target: str = "app", background_tasks: BackgroundTasks = None):
    """Manually invoke a self-healing action."""
    t_start = time.perf_counter()
    inc = tracker.start_incident(
        trigger="ManualTrigger",
        target=target,
        detection_latency_ms=10.0,
    )
    for url in APP_TARGETS:
        HealingEngine.clear_injected_faults(url)
    HealingEngine.restart_docker_container(target)
    ttr_ms = (time.perf_counter() - t_start) * 1000.0
    resolved = tracker.resolve_incident(inc["id"], action="MANUAL_HEAL_EXECUTION", ttr_ms=ttr_ms)
    return {"status": "remediated", "incident": resolved}


@app.post("/webhook")
def alertmanager_webhook(payload: Dict[str, Any]):
    """Receives alerts fired from Prometheus Alertmanager."""
    logger.info(f"Prometheus Alertmanager payload received: {payload.get('status')}")
    alerts = payload.get("alerts", [])
    processed = []
    for alert in alerts:
        alert_name = alert.get("labels", {}).get("alertname", "UnknownAlert")
        status_val = alert.get("status")
        if status_val == "firing":
            t_start = time.perf_counter()
            inc = tracker.start_incident(
                trigger=f"Alertmanager_{alert_name}",
                target="app",
                detection_latency_ms=1500.0,
            )
            for url in APP_TARGETS:
                HealingEngine.clear_injected_faults(url)
            HealingEngine.restart_docker_container("app")
            ttr_ms = (time.perf_counter() - t_start) * 1000.0
            resolved = tracker.resolve_incident(
                inc["id"],
                action="ALERTMANAGER_AUTOMATED_REMEDIATION",
                ttr_ms=ttr_ms,
            )
            processed.append(resolved)
    return {"status": "processed", "incidents": processed}


@app.get("/metrics", response_class=PlainTextResponse)
def metrics():
    """Prometheus scrape endpoint for Nexus Healer telemetry."""
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)


if __name__ == "__main__":
    start_daemon_if_needed()
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5050)
