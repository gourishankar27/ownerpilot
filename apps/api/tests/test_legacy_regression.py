"""Existing public APIs against the disposable representative OwnerPilot schema."""

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "method,path,payload",
    [
        ("GET", "/health", None),
        ("GET", "/api/dashboard", None),
        ("GET", "/api/documents", None),
        ("GET", "/api/import-records", None),
        ("GET", "/api/recurring-obligations", None),
        ("GET", "/api/actions", None),
        ("GET", "/api/reorder-plan", None),
        ("GET", "/api/settings/model-providers", None),
        (
            "POST",
            "/api/investigations",
            {"question": "Why did profit drop this month?"},
        ),
        ("POST", "/api/forecasts/run", {"metric": "sales", "horizon": "30d"}),
        ("POST", "/api/briefings/generate", {"mode": "demo"}),
        (
            "POST",
            "/api/scenarios/run",
            {
                "scenarioType": "supplier_price_increase",
                "horizonDays": 30,
                "percentage": 10,
            },
        ),
        ("POST", "/api/scheduler/run", {}),
    ],
)
def test_legacy_api(database, method, path, payload):
    from api.main import app

    with TestClient(app) as client:
        response = client.request(method, path, json=payload)
    assert response.status_code == 200, response.text
    assert isinstance(response.json(), (dict, list))
