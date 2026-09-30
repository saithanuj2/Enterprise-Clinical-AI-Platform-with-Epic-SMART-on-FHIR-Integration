"""FastAPI application for the verified MedNexus demo vertical slice."""

from __future__ import annotations

import json
import os
import time
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any
from uuid import uuid4

import httpx
import pandas as pd
from fastapi import Cookie, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from pydantic import BaseModel, Field
from redis.asyncio import Redis

from mednexus.config import get_settings
from mednexus.integrations.epic import (
    EncryptedRedisStateStore,
    EpicSmartIntegration,
    SmartIntegrationError,
)
from mednexus.ml.readmission import MODEL_FEATURES, load_model
from mednexus.retrieval.index import ClinicalRetriever, grounded_answer

PROJECT_ROOT = Path(__file__).resolve().parents[3]
REQUESTS = Counter("mednexus_http_requests_total", "HTTP requests", ["method", "path", "status"])
LATENCY = Histogram("mednexus_http_request_seconds", "HTTP request latency", ["path"])
PREDICTIONS = Counter("mednexus_predictions_total", "Readmission predictions")


class ReadmissionRequest(BaseModel):
    age_at_admission: float = Field(ge=0, le=120)
    length_of_stay_days: float = Field(ge=0, le=365)
    prior_admissions: int = Field(ge=0, le=1000)
    gender: str = Field(min_length=1, max_length=20)
    admission_type: str = Field(min_length=1, max_length=100)
    insurance: str = Field(min_length=1, max_length=100)


class SearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=1000)
    limit: int = Field(default=5, ge=1, le=20)
    subject_id: int | None = None


class AgentRequest(BaseModel):
    question: str = Field(min_length=2, max_length=2000)
    subject_id: int | None = None


@lru_cache
def model_bundle() -> tuple[Any, dict[str, Any]]:
    return load_model(PROJECT_ROOT)


@lru_cache
def retriever() -> ClinicalRetriever:
    encoder = "lexical" if os.name == "nt" else "transformer"
    return ClinicalRetriever(PROJECT_ROOT, encoder=encoder)


def records(path: Path, subject_id: int) -> list[dict[str, Any]]:
    frame = pd.read_parquet(path, filters=[("subject_id", "=", subject_id)])
    raw_records = frame.replace({pd.NA: None}).to_dict(orient="records")
    return [{str(key): value for key, value in item.items()} for item in raw_records]


def json_artifact(relative_path: str) -> Any:
    """Read a generated JSON artifact without exposing arbitrary filesystem paths."""
    path = PROJECT_ROOT / relative_path
    if not path.is_file():
        raise HTTPException(status_code=503, detail=f"artifact unavailable: {relative_path}")
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


@lru_cache
def epic_integration() -> EpicSmartIntegration:
    settings = get_settings()
    if not settings.epic_smart_enabled:
        raise RuntimeError("Epic SMART integration is disabled")
    if not settings.epic_client_id or not settings.epic_state_encryption_key:
        raise RuntimeError("Epic SMART integration is incomplete")
    redis = Redis.from_url(settings.redis_url, decode_responses=False)
    store = EncryptedRedisStateStore(
        redis,
        settings.epic_state_encryption_key.get_secret_value(),
    )
    return EpicSmartIntegration(
        fhir_base_url=settings.epic_fhir_base_url,
        client_id=settings.epic_client_id,
        redirect_uri=settings.epic_redirect_uri,
        scopes=settings.epic_smart_scopes,
        store=store,
        session_ttl_seconds=settings.epic_session_ttl_seconds,
    )


def create_app() -> FastAPI:
    application = FastAPI(
        title="MedNexus AI",
        version="1.0.0",
        description="Research-only clinical intelligence API over deidentified MIMIC demo data.",
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-Request-ID"],
    )

    @application.middleware("http")
    async def request_context(request: Request, call_next: Any) -> Response:
        request_id = request.headers.get("X-Request-ID", str(uuid4()))
        started = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        REQUESTS.labels(request.method, request.url.path, str(response.status_code)).inc()
        LATENCY.labels(request.url.path).observe(time.perf_counter() - started)
        return response

    @application.get("/api/v1/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.get("/api/v1/ready")
    def ready() -> dict[str, Any]:
        required = [
            PROJECT_ROOT / "artifacts" / "models" / "readmission" / "model.joblib",
            PROJECT_ROOT / "artifacts" / "retrieval" / "clinical.faiss",
            PROJECT_ROOT / "data" / "gold" / "patient_360",
        ]
        missing = [str(path.relative_to(PROJECT_ROOT)) for path in required if not path.exists()]
        if missing:
            raise HTTPException(status_code=503, detail={"missing_artifacts": missing})
        return {"status": "ready", "artifacts": len(required)}

    @application.get("/api/v1/operations/summary")
    def operations_summary() -> dict[str, Any]:
        """Return versioned operational metadata used by the web console."""
        pipeline = json_artifact("data/audit/latest_pipeline_report.json")
        model = json_artifact("artifacts/models/readmission/metadata.json")
        retrieval_evaluation = json_artifact("artifacts/retrieval/evaluation.json")
        retrieval_index = json_artifact("artifacts/retrieval/metadata.json")
        return {
            "pipeline": pipeline,
            "model": model,
            "retrieval": {
                "evaluation": retrieval_evaluation,
                "index": retrieval_index,
            },
        }

    @application.get("/api/v1/data-quality")
    def data_quality() -> list[dict[str, Any]]:
        return json_artifact("data/audit/latest_dq_results.json")

    @application.get("/api/v1/integrations/epic/status")
    def epic_status() -> dict[str, Any]:
        settings = get_settings()
        return {
            "provider": "Epic",
            "standard": "FHIR R4 / SMART App Launch",
            "enabled": settings.epic_smart_enabled,
            "configured": bool(
                settings.epic_client_id and settings.epic_state_encryption_key
            ),
            "fhir_base_url": settings.epic_fhir_base_url,
            "live_phi_allowed": False,
            "compliance_status": "technical foundation; not HIPAA certified",
        }

    @application.get("/api/v1/integrations/epic/launch")
    async def epic_launch(
        iss: str | None = None,
        launch: str | None = None,
    ) -> RedirectResponse:
        settings = get_settings()
        if not settings.epic_smart_enabled:
            raise HTTPException(status_code=503, detail="Epic SMART integration is disabled")
        try:
            authorization_url = await epic_integration().begin(
                issuer=iss or settings.epic_fhir_base_url,
                launch=launch,
            )
        except (SmartIntegrationError, httpx.HTTPError) as exc:
            raise HTTPException(status_code=502, detail="Epic SMART launch failed") from exc
        return RedirectResponse(authorization_url, status_code=302)

    @application.get("/api/v1/integrations/epic/callback")
    async def epic_callback(
        code: str,
        state: str,
    ) -> RedirectResponse:
        settings = get_settings()
        try:
            session_id = await epic_integration().complete(code=code, state=state)
        except (SmartIntegrationError, httpx.HTTPError) as exc:
            raise HTTPException(status_code=401, detail="Epic authorization failed") from exc
        response = RedirectResponse(f"{settings.web_base_url.rstrip('/')}/ehr?connected=true")
        response.set_cookie(
            "mednexus_epic_session",
            session_id,
            max_age=settings.epic_session_ttl_seconds,
            httponly=True,
            secure=settings.environment != "development",
            samesite="lax",
            path="/api/v1/integrations/epic",
        )
        return response

    @application.get("/api/v1/integrations/epic/fhir/{resource_type}/{resource_id}")
    async def epic_fhir_read(
        resource_type: str,
        resource_id: str,
        mednexus_epic_session: Annotated[str | None, Cookie()] = None,
    ) -> dict[str, Any]:
        if mednexus_epic_session is None:
            raise HTTPException(status_code=401, detail="Epic session required")
        try:
            resource = await epic_integration().read_resource(
                mednexus_epic_session,
                resource_type,
                resource_id,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except (SmartIntegrationError, httpx.HTTPError) as exc:
            raise HTTPException(status_code=502, detail="Epic FHIR request failed") from exc
        return resource.model_dump(mode="json")

    @application.post("/api/v1/predict/readmission")
    def predict_readmission(payload: ReadmissionRequest) -> dict[str, Any]:
        model, metadata = model_bundle()
        frame = pd.DataFrame([payload.model_dump()])[MODEL_FEATURES]
        probability = float(model.predict_proba(frame)[0, 1])
        threshold = float(metadata["threshold"])
        PREDICTIONS.inc()
        return {
            "risk_probability": probability,
            "risk_level": "high" if probability >= threshold else "lower",
            "threshold": threshold,
            "model_run_id": metadata["run_id"],
            "disclaimer": "Research decision support only; not a diagnosis.",
        }

    @application.get("/api/v1/patients/{subject_id}")
    def patient(subject_id: int) -> dict[str, Any]:
        items = records(PROJECT_ROOT / "data" / "gold" / "patient_360", subject_id)
        if not items:
            raise HTTPException(status_code=404, detail="patient not found")
        return items[0]

    @application.get("/api/v1/patients/{subject_id}/timeline")
    def timeline(subject_id: int) -> list[dict[str, Any]]:
        items = records(PROJECT_ROOT / "data" / "silver" / "admissions", subject_id)
        return sorted(items, key=lambda item: str(item.get("admittime")))

    @application.post("/api/v1/search")
    def search(payload: SearchRequest) -> dict[str, Any]:
        results = retriever().search(payload.query, payload.limit, payload.subject_id)
        return {"results": [result.__dict__ for result in results]}

    @application.post("/api/v1/rag/query")
    def rag(payload: SearchRequest) -> dict[str, Any]:
        evidence = retriever().search(payload.query, payload.limit, payload.subject_id)
        return grounded_answer(payload.query, evidence)

    @application.post("/api/v1/agent/query")
    def agent(payload: AgentRequest) -> dict[str, Any]:
        tools: list[str] = []
        context: dict[str, Any] = {}
        if payload.subject_id is not None:
            tools.extend(["get_patient_context", "retrieve_clinical_context"])
            patient_items = records(
                PROJECT_ROOT / "data" / "gold" / "patient_360", payload.subject_id
            )
            context["patient"] = patient_items[0] if patient_items else None
        else:
            tools.append("retrieve_clinical_context")
        evidence = retriever().search(payload.question, 5, payload.subject_id)
        response = grounded_answer(payload.question, evidence)
        return {
            **response,
            "tools_executed": tools,
            "context": context,
            "iterations": 1,
            "audit_id": str(uuid4()),
        }

    @application.get("/metrics", include_in_schema=False)
    def metrics() -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @application.get("/api/v1/patients")
    def patient_list(limit: Annotated[int, Query(ge=1, le=100)] = 20) -> list[dict[str, Any]]:
        frame = pd.read_parquet(PROJECT_ROOT / "data" / "gold" / "patient_360").head(limit)
        raw_records = frame.replace({pd.NA: None}).to_dict(orient="records")
        return [{str(key): value for key, value in item.items()} for item in raw_records]

    return application


app = create_app()
