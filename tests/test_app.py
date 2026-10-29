"""Unit and integration tests for Nexus Victim Service (app/main.py)."""

import pytest
from fastapi.testclient import TestClient
from app.main import app, fault_state


@pytest.fixture(autouse=True)
def reset_fault_state():
    """Reset fault state before and after each test."""
    fault_state["fail_mode"] = False
    fault_state["fail_rate"] = 0.0
    fault_state["latency_mode"] = False
    fault_state["latency_seconds"] = 0.0
    fault_state["circuit_breaker"] = False
    yield
    fault_state["fail_mode"] = False
    fault_state["fail_rate"] = 0.0
    fault_state["latency_mode"] = False
    fault_state["latency_seconds"] = 0.0
    fault_state["circuit_breaker"] = False


@pytest.fixture
def client():
    return TestClient(app)


def test_home_endpoint(client):
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "Nexus Victim Service"
    assert data["status"] == "online"
    assert "uptime_seconds" in data


def test_health_endpoint_healthy(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"


def test_workload_endpoint(client):
    response = client.get("/api/workload")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "processed_by" in data


def test_metrics_endpoint(client):
    response = client.get("/metrics")
    assert response.status_code == 200
    text = response.text
    assert "nexus_http_requests_total" in text
    assert "nexus_http_request_duration_seconds" in text
    assert "nexus_app_health_status" in text


def test_chaos_fail_injection_and_recovery(client):
    # Inject 100% failure
    resp = client.post("/chaos/fail?rate=1.0")
    assert resp.status_code == 200
    assert resp.json()["fail_rate"] == 1.0

    # /health should report 503
    health_resp = client.get("/health")
    assert health_resp.status_code == 503
    assert health_resp.json()["status"] == "unhealthy"

    # Workload should return 500
    workload_resp = client.get("/api/workload")
    assert workload_resp.status_code == 500

    # Recover
    rec_resp = client.post("/chaos/recover")
    assert rec_resp.status_code == 200

    # Verify restored health
    health_restored = client.get("/health")
    assert health_restored.status_code == 200
    assert health_restored.json()["status"] == "healthy"


def test_chaos_slow_injection(client):
    resp = client.post("/chaos/slow?delay=0.1")
    assert resp.status_code == 200
    status_resp = client.get("/chaos/status")
    assert status_resp.status_code == 200
    assert status_resp.json()["fault_state"]["latency_mode"] is True


def test_circuit_breaker(client):
    resp = client.post("/chaos/circuit-breaker?active=true")
    assert resp.status_code == 200
    assert resp.json()["circuit_breaker_active"] is True

    # Workload should be rate limited (429)
    workload_resp = client.get("/api/workload")
    assert workload_resp.status_code == 429
    assert "Circuit breaker open" in workload_resp.json()["error"]

    # Disengage circuit breaker
    client.post("/chaos/circuit-breaker?active=false")
    workload_restored = client.get("/api/workload")
    assert workload_restored.status_code == 200
