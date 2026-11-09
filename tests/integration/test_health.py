"""Integration tests for health and readiness endpoints."""

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration


def test_liveness_returns_application_metadata(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "name": "Proposal Research Agent Test",
        "version": "0.0.0-test",
        "environment": "test",
    }


def test_readiness_reports_connected_database(client: TestClient) -> None:
    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["database"] == "connected"


def test_readiness_returns_503_when_database_is_unavailable(client: TestClient) -> None:
    class UnavailableDatabase:
        """Test double used only to exercise the readiness failure path."""

        def check_connection(self) -> bool:
            return False

    client.app.state.database = UnavailableDatabase()  # type: ignore[attr-defined]

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "degraded"
    assert response.json()["database"] == "unavailable"


def test_unknown_route_returns_404(client: TestClient) -> None:
    assert client.get("/does-not-exist").status_code == 404
