"""Nexus Chaos Monkey (The Villain).

Injects real-world failures into the Nexus cluster:
1. Container crash / sudden termination (SIGKILL)
2. HTTP 5xx error bursts (software exceptions)
3. High latency injection (thread lock / slow network)
4. Container freeze / unresponsiveness (Docker pause)

Validates whether Nexus Healer autonomously detects and restores cluster health.
"""

import os
import sys
import time
import random
import logging
import argparse
from typing import List
import requests

# Optional Docker SDK import with fallback
try:
    import docker
    docker_client = docker.from_env()
except Exception:
    docker_client = None

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [CHAOS-MONKEY] %(message)s",
)
logger = logging.getLogger("chaos-monkey")

APP_TARGET_URL = os.getenv("APP_TARGET_URL", "http://app:8000")
CHAOS_INTERVAL = float(os.getenv("CHAOS_INTERVAL", "15.0"))
CHAOS_ENABLED = os.getenv("CHAOS_ENABLED", "true").lower() == "true"


def get_target_containers(prefix: str = "app") -> List[Any]:
    """Finds Docker containers matching the victim service prefix."""
    if not docker_client:
        return []
    try:
        return [c for c in docker_client.containers.list() if prefix in c.name]
    except Exception as e:
        logger.warning(f"Could not list Docker containers: {e}")
        return []


def attack_container_kill():
    """Scenario 1: Kills an active container abruptly."""
    containers = get_target_containers("app")
    if containers:
        target = random.choice(containers)
        logger.info(f"💣 [CHAOS ATTACK] Killing container: {target.name} ({target.id[:10]})")
        try:
            target.kill()
        except Exception as e:
            logger.warning(f"Target kill exception: {e}")
    else:
        logger.info("No active containers found to kill; triggering simulated HTTP crash")
        try:
            requests.post(f"{APP_TARGET_URL}/chaos/crash", timeout=1.0)
        except Exception:
            pass


def attack_http_500():
    """Scenario 2: Injects 100% 500 error rate into victim service."""
    logger.info(f"💣 [CHAOS ATTACK] Injecting HTTP 500 error storm on {APP_TARGET_URL}")
    try:
        resp = requests.post(f"{APP_TARGET_URL}/chaos/fail", params={"rate": 1.0}, timeout=3.0)
        logger.info(f"HTTP 500 fault response: {resp.status_code}")
    except Exception as e:
        logger.warning(f"Could not reach {APP_TARGET_URL} to inject 500s: {e}")


def attack_latency_spike():
    """Scenario 3: Injects 2.0s artificial latency into victim service."""
    logger.info(f"💣 [CHAOS ATTACK] Injecting 2.0s latency delay on {APP_TARGET_URL}")
    try:
        resp = requests.post(f"{APP_TARGET_URL}/chaos/slow", params={"delay": 2.0}, timeout=3.0)
        logger.info(f"Latency fault response: {resp.status_code}")
    except Exception as e:
        logger.warning(f"Could not reach {APP_TARGET_URL} to inject latency: {e}")


def attack_pause_container():
    """Scenario 4: Pauses container for 5 seconds to simulate a frozen zombie process."""
    containers = get_target_containers("app")
    if containers:
        target = random.choice(containers)
        logger.info(f"💣 [CHAOS ATTACK] Freezing (pausing) container: {target.name}")
        try:
            target.pause()
            time.sleep(5)
            target.unpause()
            logger.info(f"Unpaused container: {target.name}")
        except Exception as e:
            logger.warning(f"Pause exception: {e}")
    else:
        attack_http_500()


SCENARIOS = [
    attack_container_kill,
    attack_http_500,
    attack_latency_spike,
    attack_pause_container,
]


def run_continuous_chaos(interval: float = 15.0):
    """Runs continuous random disruptions with sleep intervals."""
    logger.info(f"Starting continuous Chaos Monkey with {interval}s interval...")
    while True:
        time.sleep(interval)
        if not CHAOS_ENABLED:
            logger.info("Chaos is currently paused via CHAOS_ENABLED=false")
            continue
        scenario = random.choice(SCENARIOS)
        scenario()


def main():
    parser = argparse.ArgumentParser(description="Nexus Chaos Monkey Failure Injector")
    parser.add_argument("--mode", choices=["continuous", "single", "burst"], default="continuous")
    parser.add_argument("--scenario", choices=["all", "kill", "500", "latency", "pause"], default="all")
    parser.add_argument("--interval", type=float, default=CHAOS_INTERVAL)
    parser.add_argument("--burst-count", type=int, default=3)
    args = parser.parse_args()

    scenario_map = {
        "kill": attack_container_kill,
        "500": attack_http_500,
        "latency": attack_latency_spike,
        "pause": attack_pause_container,
    }

    if args.mode == "single":
        if args.scenario == "all":
            scenario = random.choice(SCENARIOS)
        else:
            scenario = scenario_map[args.scenario]
        scenario()
    elif args.mode == "burst":
        logger.info(f"Executing chaos burst of {args.burst_count} events...")
        for i in range(args.burst_count):
            scenario = random.choice(SCENARIOS) if args.scenario == "all" else scenario_map[args.scenario]
            scenario()
            time.sleep(3)
    else:
        run_continuous_chaos(args.interval)


if __name__ == "__main__":
    main()
