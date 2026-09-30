from importlib import import_module
from types import SimpleNamespace

import numpy as np
from fastapi.testclient import TestClient

from mednexus.api.app import app

api_module = import_module("mednexus.api.app")
client = TestClient(app)


def test_health_and_ready(monkeypatch, tmp_path):
    for relative_path in (
        "artifacts/models/readmission/model.joblib",
        "artifacts/retrieval/clinical.faiss",
    ):
        path = tmp_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    (tmp_path / "data/gold/patient_360").mkdir(parents=True)
    monkeypatch.setattr(api_module, "PROJECT_ROOT", tmp_path)

    assert client.get("/api/v1/health").json() == {"status": "ok"}
    assert client.get("/api/v1/ready").status_code == 200


def test_prediction_contract(monkeypatch):
    class FakeModel:
        def predict_proba(self, frame):
            assert list(frame.columns) == api_module.MODEL_FEATURES
            return np.array([[0.27, 0.73]])

    monkeypatch.setattr(
        api_module,
        "model_bundle",
        lambda: (FakeModel(), {"threshold": 0.5, "run_id": "unit-test-run"}),
    )
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


def test_search_returns_provenance(monkeypatch):
    result = SimpleNamespace(
        document_id="admission-1",
        text="Emergency hospital admission.",
        score=0.91,
        metadata={"source": "silver.admissions", "subject_id": 1},
    )
    monkeypatch.setattr(
        api_module,
        "retriever",
        lambda: SimpleNamespace(search=lambda query, limit, subject_id: [result]),
    )
    response = client.post("/api/v1/search", json={"query": "emergency admission", "limit": 3})

    assert response.status_code == 200
    assert response.json()["results"]
    assert response.json()["results"][0]["metadata"]["source"] == "silver.admissions"


def test_operational_artifacts_are_exposed_through_versioned_endpoints(monkeypatch):
    artifacts = {
        "data/audit/latest_pipeline_report.json": {"status": "SUCCESS"},
        "artifacts/models/readmission/metadata.json": {"metrics": {"pr_auc": 0.82}},
        "artifacts/retrieval/evaluation.json": {"mrr": 0.9},
        "artifacts/retrieval/metadata.json": {"documents": 12},
        "data/audit/latest_dq_results.json": [{"check": "required_fields", "status": "PASS"}],
    }
    monkeypatch.setattr(api_module, "json_artifact", artifacts.__getitem__)
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
