from fastapi.testclient import TestClient

from mednexus.api.app import app

client = TestClient(app)


def test_health_and_ready():
    assert client.get("/api/v1/health").json() == {"status": "ok"}
    assert client.get("/api/v1/ready").status_code == 200


def test_prediction_contract():
    response = client.post(
        "/api/v1/predict/readmission",
        json={
            "age_at_admission": 65,
            "length_of_stay_days": 4,
            "prior_admissions": 1,
            "gender": "F",
            "admission_type": "EW EMER.",
            "insurance": "Medicare",
        },
    )

    assert response.status_code == 200
    assert 0 <= response.json()["risk_probability"] <= 1
    assert response.headers["X-Request-ID"]


def test_search_returns_provenance():
    response = client.post("/api/v1/search", json={"query": "emergency admission", "limit": 3})

    assert response.status_code == 200
    assert response.json()["results"]
    assert response.json()["results"][0]["metadata"]["source"] == "silver.admissions"


def test_operational_artifacts_are_exposed_through_versioned_endpoints():
    summary = client.get("/api/v1/operations/summary")
    quality = client.get("/api/v1/data-quality")

    assert summary.status_code == 200
    assert summary.json()["pipeline"]["status"] == "SUCCESS"
    assert "pr_auc" in summary.json()["model"]["metrics"]
    assert quality.status_code == 200
    assert all(result["status"] == "PASS" for result in quality.json())


def test_epic_status_is_safe_when_integration_is_disabled():
    response = client.get("/api/v1/integrations/epic/status")

    assert response.status_code == 200
    assert response.json()["provider"] == "Epic"
    assert response.json()["live_phi_allowed"] is False
    assert "client_id" not in response.json()
