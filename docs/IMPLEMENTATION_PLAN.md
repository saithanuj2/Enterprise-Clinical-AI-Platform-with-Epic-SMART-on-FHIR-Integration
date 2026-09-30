# MedNexus AI Implementation Plan

## Delivery rules

Each phase starts with file-level inspection and explicit acceptance criteria. A phase is complete only when its code, tests, integration path, failure behavior, and documentation are verified. Unavailable credentials, controlled datasets, or external services are recorded as blockers; results are never fabricated.

## Phase status

| Phase | Scope | Status |
|---|---|---|
| 0 | Repository audit and architecture stabilization | Documented; runtime checks blocked by local Docker/Python state |
| 1 | Infrastructure, configuration, packaging, migrations, test harness | Code complete; Docker runtime gate pending |
| 2-6 | Demo data platform, MLflow baseline, and inference API | Verified locally |
| 7 | Kafka event pipeline | Contracts/idempotency complete; broker integration pending |
| 8-11 | Retrieval, grounded response, controlled agent, React application | Verified locally |
| 12-14 | Hardening, CI, benchmarks, final validation | Implemented locally; Docker/full-data validation pending |

## Phase 1 — infrastructure and configuration stabilization

### Problem

The environment cannot currently be reproduced: the virtual environment is stale, Docker is stopped, container dependencies drift from `pyproject.toml`, settings embedded development secrets, and host/container endpoints were easy to confuse. Database initialization is not a real migration workflow.

### Files in scope

- `pyproject.toml`
- `.env.example`
- `src/mednexus/config.py`
- `src/mednexus/ingestion/registry.py`
- `pipelines/ingestion/ingest_bronze.py`
- `infrastructure/docker/*`
- `docker-compose.yml`
- `database/` migration tooling
- `tests/unit`, `tests/integration`
- root developer commands and `README.md`

### Acceptance criteria

- A clean Python 3.11/3.12 environment installs the package and development dependencies from one declared source.
- Default unit tests require no running infrastructure; integration tests are explicitly selected.
- Settings require secrets, redact them in representations, encode connection URLs correctly, and reject example credentials outside local development.
- Host and Compose-network endpoints are documented and tested.
- Spark imports `mednexus` from an installed package rather than relying solely on `PYTHONPATH`.
- Compose validates; images build; all required local services become healthy.
- A migration tool can upgrade a fresh and an existing database without destroying volumes.
- The Spark smoke test supports every Python version allowed by the project.
- README setup commands work from a clean clone.

### Current Phase 1 progress

- Added missing PyYAML dependency and centralized Spark-image dependency installation through `pyproject.toml`.
- Hardened settings and aligned host defaults with published Compose ports.
- Added validated ingestion-registry models with path traversal protection.
- Separated infrastructure integration tests from the default unit-test selection.
- Added unit coverage for settings and registry validation.

Remaining gates: recreate Python, run lint/type/unit tests, start Docker, validate images/services, introduce migrations, correct the Spark smoke version assertion, and document verified bootstrap commands.

## Phase 2 — MIMIC source validation and Bronze

Acceptance criteria: configured `.csv.gz` sources are preflighted before infrastructure work; explicit schemas and source manifests exist; writes are idempotent/versioned; row counts/checksums/audit details persist; missing and malformed sources have regression tests; both available demo tables ingest successfully.

## Phase 3 — Silver and data quality

Acceptance criteria: normalized types and timestamps, key deduplication, referential checks, ICD normalization, reason-coded quarantine, severity-aware reusable DQ rules, persisted results, and tested critical-stop behavior.

## Phase 4 — Gold clinical datasets

Acceptance criteria: patient 360, admission/readmission, risk, lab trend, diagnosis, and medication features have explicit grains, lineage, cutoff semantics, leakage tests, and demo-data builds.

## Phase 5 — readmission ML and MLflow

Acceptance criteria: documented cohort/label, patient-safe temporal split, interpretable baseline, imbalance/calibration/threshold analysis, reproducible dataset version, MLflow artifacts, and only actually executed metrics.

## Phase 6 — inference API

Acceptance criteria: versioned FastAPI endpoints, typed contracts, health/readiness distinction, model-unavailable behavior, request IDs, timeouts, metrics, audit records, and API/integration tests.

## Phase 7 — Kafka event pipeline

Acceptance criteria: documented event purposes and schemas, IDs/correlation/timestamps, idempotent producer/consumer, bounded retry and DLQ, synthetic deidentified simulator, duplicate-delivery tests, and measured throughput.

## Phase 8 — retrieval

Acceptance criteria: provenance-preserving document generation, deterministic cleaning/chunking, versioned embeddings/FAISS index, filtered retrieval, empty-result behavior, and retrieval unit/integration tests.

## Phase 9 — grounded RAG and evaluation

Acceptance criteria: citations in responses, insufficient-evidence behavior, separated retrieval/generation evaluation sets, Recall@K/MRR/NDCG and groundedness reporting from actual runs, and unsupported-claim tests.

## Phase 10 — controlled agent workflow

Acceptance criteria: schema-bound approved tools, no unrestricted SQL, evidence validator, iteration/retry/time limits, tool audit trail, failure tests, and transparent response metadata.

## Phase 11 — React application

Acceptance criteria: core patient/risk/timeline/search/assistant/operations views, evidence presentation, accessible responsive states, typed API client, component tests, and successful production build.

## Phase 12 — observability and security hardening

Acceptance criteria: useful metrics and dashboards, structured redacted logs, propagated IDs, secrets strategy, CORS/rate limits, least-privilege containers where practical, dependency review, threat model, and no unsupported compliance claims.

## Phase 13 — CI/CD and comprehensive tests

Acceptance criteria: lint, format, types, unit, selected integration, frontend, Docker build, and dependency/security checks run in CI; required checks fail closed.

## Phase 14 — benchmarks, documentation, and final validation

Acceptance criteria: both batch-to-UI and retrieval-to-UI paths execute; event path executes where retained; measured data, ML, API, Kafka, and retrieval results populate `docs/BENCHMARKS.md`; runbook, ADRs, limitations, screenshots, and recovery procedures are current.

## Recommended order and critical path

Finish Phase 1 before adding services. Then implement the demo-data batch path through Phase 6 so there is one defensible vertical slice. Add Kafka only after the batch risk path is correct. Build retrieval and RAG before agent orchestration. Build the UI against stable APIs, then harden, automate, benchmark, and document.
