"""
Integration tests for the simple health/status endpoints.
Fastest smoke test — if these fail, the app isn't even starting up.
"""

from __future__ import annotations


async def test_root_returns_running_status(api_client):
    response = await api_client.get("/")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "running"
    assert "Microbiome" in body["message"]


async def test_metrics_endpoint_ok(api_client):
    response = await api_client.get("/metrics")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "message": "Metrics endpoint"}
