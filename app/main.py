"""Nexus Victim Service - FastAPI Application.

Simulates a production microservice with:
- Prometheus metric instrumentation (requests, latency, health)
- Health check endpoints
- Fault injection endpoints for chaos testing (5xx errors, latency spikes, simulated crash)
"""

import os
import time
import random
import asyncio
from typing import Dict, Any
from fastapi import FastAPI, Response, Request, status
from fastapi.responses import JSONResponse, PlainTextResponse
from prometheus_client import (
    Counter,
    Histogram,
    Gauge,
    generate_latest,
    CONTENT_TYPE_LATEST,
)

app = FastAPI(
    title="Nexus Victim Service",
    description="Resilience test service under Chaos Monkey disruption",
    version="2.0.0",
)

INSTANCE_ID = os.getenv("INSTANCE_ID", f"worker-{os.getpid()}")

# --- Prometheus Metrics ---
HTTP_REQUESTS_TOTAL = Counter(
    "nexus_http_requests_total",
    "Total count of HTTP requests processed",
    ["method", "endpoint", "status"],
)

HTTP_REQUEST_DURATION = Histogram(
    "nexus_http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "endpoint"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
)

APP_HEALTH_STATUS = Gauge(
    "nexus_app_health_status",
    "Service health status (1 = healthy, 0 = degraded/failing)",
    ["instance"],
)

INJECTED_FAULT_ACTIVE = Gauge(
    "nexus_injected_fault_active",
    "Injected chaos fault indicator (1 = fault active, 0 = normal)",
    ["fault_type", "instance"],
)

CIRCUIT_BREAKER_ACTIVE = Gauge(
    "nexus_circuit_breaker_active",
    "Circuit breaker active state (1 = throttled, 0 = normal)",
    ["instance"],
)

# Initial gauge states
APP_HEALTH_STATUS.labels(instance=INSTANCE_ID).set(1)
INJECTED_FAULT_ACTIVE.labels(fault_type="500_error", instance=INSTANCE_ID).set(0)
INJECTED_FAULT_ACTIVE.labels(fault_type="latency", instance=INSTANCE_ID).set(0)
CIRCUIT_BREAKER_ACTIVE.labels(instance=INSTANCE_ID).set(0)

# --- Chaos & Fault Injection State ---
fault_state: Dict[str, Any] = {
    "fail_mode": False,       # When True, requests return 500
    "fail_rate": 0.0,         # Probability (0.0 to 1.0)
    "latency_mode": False,    # When True, inject artificial delay
    "latency_seconds": 0.0,   # Added delay
    "circuit_breaker": False, # When True, rate limit / shed load
    "start_time": time.time(),
}


@app.middleware("http")
async def prometheus_metrics_middleware(request: Request, call_next):
    """Middleware to record request duration and status codes for Prometheus."""
    start_time = time.perf_counter()
    endpoint = request.url.path

    # Process fault injection delays if latency mode is active
    if fault_state["latency_mode"] and endpoint not in ["/metrics", "/health", "/chaos/recover", "/chaos/status"]:
        delay = fault_state["latency_seconds"]
        await asyncio.sleep(delay)

    # Process circuit breaker rate limiting if active
    if fault_state["circuit_breaker"] and endpoint == "/api/workload":
        status_code = status.HTTP_429_TOO_MANY_REQUESTS
        HTTP_REQUESTS_TOTAL.labels(method=request.method, endpoint=endpoint, status=str(status_code)).inc()
        duration = time.perf_counter() - start_time
        HTTP_REQUEST_DURATION.labels(method=request.method, endpoint=endpoint).observe(duration)
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={"error": "Circuit breaker open: traffic shed by Nexus Healer", "instance": INSTANCE_ID},
        )

    # Inject simulated 500 error if fail mode is active
    if fault_state["fail_mode"] and endpoint not in ["/metrics", "/health", "/chaos/recover", "/chaos/status"]:
        if random.random() < fault_state["fail_rate"]:
            status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
            duration = time.perf_counter() - start_time
            HTTP_REQUESTS_TOTAL.labels(method=request.method, endpoint=endpoint, status=str(status_code)).inc()
            HTTP_REQUEST_DURATION.labels(method=request.method, endpoint=endpoint).observe(duration)
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"error": "Chaos injected failure", "instance": INSTANCE_ID},
            )

    try:
        response = await call_next(request)
        status_code = response.status_code
    except Exception as exc:
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        duration = time.perf_counter() - start_time
        HTTP_REQUESTS_TOTAL.labels(method=request.method, endpoint=endpoint, status=str(status_code)).inc()
        HTTP_REQUEST_DURATION.labels(method=request.method, endpoint=endpoint).observe(duration)
        raise exc

    duration = time.perf_counter() - start_time
    HTTP_REQUESTS_TOTAL.labels(method=request.method, endpoint=endpoint, status=str(status_code)).inc()
    HTTP_REQUEST_DURATION.labels(method=request.method, endpoint=endpoint).observe(duration)
    return response


# --- Application Endpoints ---

@app.get("/")
def home():
    """Root endpoint verifying service liveness."""
    return {
        "service": "Nexus Victim Service",
        "instance": INSTANCE_ID,
        "status": "online",
        "uptime_seconds": round(time.time() - fault_state["start_time"], 2),
    }


@app.get("/health")
def health(response: Response):
    """Health check probe used by Docker, Prometheus, and Nexus Healer."""
    if fault_state["fail_mode"] and fault_state["fail_rate"] >= 0.8:
        APP_HEALTH_STATUS.labels(instance=INSTANCE_ID).set(0)
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "unhealthy", "instance": INSTANCE_ID, "reason": "chaos_failure_active"}

    APP_HEALTH_STATUS.labels(instance=INSTANCE_ID).set(1)
    return {"status": "healthy", "instance": INSTANCE_ID, "uptime": round(time.time() - fault_state["start_time"], 2)}


@app.get("/api/workload")
async def workload():
    """Simulates a lightweight production workload with minor natural jitter (10-30ms)."""
    natural_delay = random.uniform(0.010, 0.030)
    await asyncio.sleep(natural_delay)
    return {
        "status": "success",
        "processed_by": INSTANCE_ID,
        "natural_latency_ms": round(natural_delay * 1000, 2),
        "timestamp": time.time(),
    }


@app.get("/metrics", response_class=PlainTextResponse)
def metrics():
    """Prometheus scrape endpoint."""
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)


# --- Chaos Injection Control Endpoints ---

@app.post("/chaos/fail")
def chaos_fail(rate: float = 1.0):
    """Inject HTTP 500 error bursts into this instance."""
    fault_state["fail_mode"] = True
    fault_state["fail_rate"] = max(0.0, min(1.0, rate))
    INJECTED_FAULT_ACTIVE.labels(fault_type="500_error", instance=INSTANCE_ID).set(1)
    APP_HEALTH_STATUS.labels(instance=INSTANCE_ID).set(0 if rate >= 0.8 else 1)
    return {"message": "500 fault injected", "fail_rate": fault_state["fail_rate"], "instance": INSTANCE_ID}


@app.post("/chaos/slow")
def chaos_slow(delay: float = 1.5):
    """Inject artificial response latency to simulate resource exhaustion or slow upstream."""
    fault_state["latency_mode"] = True
    fault_state["latency_seconds"] = max(0.1, delay)
    INJECTED_FAULT_ACTIVE.labels(fault_type="latency", instance=INSTANCE_ID).set(1)
    return {"message": "Latency fault injected", "delay_seconds": fault_state["latency_seconds"], "instance": INSTANCE_ID}


@app.post("/chaos/recover")
def chaos_recover():
    """Remediate / clear all injected faults (called by Nexus Healer)."""
    fault_state["fail_mode"] = False
    fault_state["fail_rate"] = 0.0
    fault_state["latency_mode"] = False
    fault_state["latency_seconds"] = 0.0
    fault_state["circuit_breaker"] = False
    INJECTED_FAULT_ACTIVE.labels(fault_type="500_error", instance=INSTANCE_ID).set(0)
    INJECTED_FAULT_ACTIVE.labels(fault_type="latency", instance=INSTANCE_ID).set(0)
    CIRCUIT_BREAKER_ACTIVE.labels(instance=INSTANCE_ID).set(0)
    APP_HEALTH_STATUS.labels(instance=INSTANCE_ID).set(1)
    return {"message": "Faults cleared: instance restored to healthy baseline", "instance": INSTANCE_ID}


@app.post("/chaos/circuit-breaker")
def toggle_circuit_breaker(active: bool = True):
    """Enable or disable traffic shedding / circuit breaker."""
    fault_state["circuit_breaker"] = active
    CIRCUIT_BREAKER_ACTIVE.labels(instance=INSTANCE_ID).set(1 if active else 0)
    return {"circuit_breaker_active": active, "instance": INSTANCE_ID}


@app.get("/chaos/status")
def chaos_status():
    """Inspect current fault injection state."""
    return {
        "instance": INSTANCE_ID,
        "fault_state": fault_state,
        "is_healthy": not (fault_state["fail_mode"] and fault_state["fail_rate"] >= 0.8),
    }


@app.post("/chaos/crash")
def chaos_crash():
    """Simulate an abrupt hard crash."""
    os._exit(1)
