"""Unit and integration tests for Nexus Healer (recovery/healer.py)."""

import pytest
from fastapi.testclient import TestClient
from recovery.healer import app, IncidentTracker, tracker


@pytest.fixture
def healer_client():
    return TestClient(app)


def test_incident_tracker_lifecycle():
    it = IncidentTracker()
    assert it.active_incident is None
    assert len(it.incidents) == 0

    # Start incident
    inc = it.start_incident(
        trigger="TestFaultTrigger",
        target="http://app:8000",
        detection_latency_ms=1450.0,
    )
    assert inc["status"] == "DETECTED"
    assert inc["time_to_detect_ms"] == 1450.0
    assert it.active_incident is not None

    # Resolve incident
    resolved = it.resolve_incident(
        incident_id=inc["id"],
        action="CONTAINER_RESTART",
        ttr_ms=3200.0,
    )
    assert resolved is not None
    assert resolved["status"] == "RESOLVED"
    assert resolved["time_to_recover_ms"] == 3200.0
    assert it.active_incident is None
    assert len(it.incidents) == 1

    # Record health
    it.record_health(True)
    it.record_health(True)
    it.record_health(False)

    stats = it.get_stats()
    assert stats["total_incidents"] == 1
    assert stats["resolved_incidents"] == 1
    assert stats["mean_time_to_detect_ms"] == 1450.0
    assert stats["mean_time_to_recover_ms"] == 3200.0
    assert stats["mean_time_to_recover_seconds"] == 3.2
    assert 60.0 <= stats["cluster_uptime_pct"] <= 70.0


def test_healer_api_home_and_health(healer_client):
    resp = healer_client.get("/")
    assert resp.status_code == 200
    assert resp.json()["service"] == "Nexus Healer"

    health_resp = healer_client.get("/health")
    assert health_resp.status_code == 200
    assert health_resp.json()["status"] == "healthy"


def test_healer_api_stats_and_incidents(healer_client):
    # Retrieve stats
    stats_resp = healer_client.get("/api/stats")
    assert stats_resp.status_code == 200
    data = stats_resp.json()
    assert "mean_time_to_detect_seconds" in data
    assert "mean_time_to_recover_seconds" in data
    assert "cluster_uptime_pct" in data

    # Retrieve incidents
    inc_resp = healer_client.get("/api/incidents")
    assert inc_resp.status_code == 200
    assert "incidents" in inc_resp.json()


def test_healer_alertmanager_webhook(healer_client):
    payload = {
        "status": "firing",
        "alerts": [
            {
                "status": "firing",
                "labels": {
                    "alertname": "NexusInstanceDown",
                    "instance": "app:8000",
                },
                "annotations": {
                    "summary": "Victim container down",
                },
            }
        ],
    }
    resp = healer_client.post("/webhook", json=payload)
    assert resp.status_code == 200
    assert resp.json()["status"] == "processed"
    assert len(resp.json()["incidents"]) == 1
    assert resp.json()["incidents"][0]["trigger"] == "Alertmanager_NexusInstanceDown"


def test_healer_metrics_export(healer_client):
    resp = healer_client.get("/metrics")
    assert resp.status_code == 200
    assert "nexus_healer_incidents_total" in resp.text
    assert "nexus_healer_cluster_uptime_ratio" in resp.text
