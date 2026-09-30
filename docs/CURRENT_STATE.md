# MedNexus AI Current State

Audit date: 2026-09-26

## Post-implementation update

The original audit below is preserved as a baseline. Since that audit, the repository now includes and has locally verified:

- explicit-schema Bronze plus validated Silver, quarantine, DQ audit, patient-360, and leakage-aware readmission Gold processing for the available patients/admissions demo data;
- a patient-disjoint logistic-regression baseline tracked in MLflow with an immutable dataset digest and honest held-out metrics;
- Sentence-Transformer embeddings, a persisted FAISS index, provenance-bearing retrieval, measured retrieval evaluation, and an evidence-only grounded response path;
- a versioned FastAPI service with health/readiness, prediction, patient, timeline, search, RAG, controlled-agent, request-ID, CORS, and Prometheus endpoints;
- a responsive React/TypeScript clinical operations dashboard verified visually against the live local API;
- Alembic migrations, validated Kafka event contracts/idempotency primitives, API/web container definitions, Prometheus scraping, GitHub Actions, security/runbook/design documentation, and measured benchmarks.

Current verified gates: 13 unit/API tests pass, Ruff passes, mypy passes, the frontend production build passes, the production npm audit reports no known vulnerabilities, Compose static validation passes, and Alembic offline SQL generation passes.

Remaining external validation boundary: Docker Desktop's engine did not start on this workstation, so live PostgreSQL/Redis/Kafka/MinIO/MLflow/Grafana container integration and Docker image builds could not be executed locally. Only patients and admissions source data were present; other MIMIC domains cannot be truthfully validated without their permitted files.

## Executive assessment

The repository is an early infrastructure and ingestion scaffold, not yet an end-to-end clinical intelligence platform. It contains 13 meaningful tracked-candidate files and has no commits on `main`; most top-level product directories are empty placeholders. The honest maturity level is **Phase 0 / early Phase 1**.

No production-readiness, healthcare-compliance, model-performance, or end-to-end claims are supported by the current evidence.

## Audit evidence

- `docker compose config --quiet` succeeds and resolves nine services.
- Docker runtime validation is blocked because Docker Desktop's daemon is not running.
- The local `.venv` is broken: its launcher references a removed Python 3.12 installation.
- The repository has no `README.md`, CI workflow, migration runner, API, frontend, ML, RAG, agent, or streaming implementation.
- Local MIMIC demo material is limited to two compressed files:
  - `patients.csv.gz`: 100 data rows, 6 columns, 1,083 compressed bytes.
  - `admissions.csv.gz`: 275 data rows, 16 columns, 11,072 compressed bytes.
- No patient rows or identifiers were printed during the audit.
- `.env` is ignored by Git and is not tracked. Its credentials match the documented development examples and must never be reused outside local development.

## What currently works

| Area | Evidence | Status |
|---|---|---|
| Compose syntax | Nine services resolve and configuration validation exits successfully | Static validation only |
| Package layout | `src/mednexus` uses a setuptools `src` layout | Valid foundation |
| Settings | Pydantic settings load environment-based service configuration | Implemented; hardened in Phase 1 |
| Database bootstrap | PostgreSQL initialization creates logical schemas and three tables | Partial; not a migration system |
| Bronze registry | Six MIMIC hospital datasets are declared | Partial |
| Bronze ingestion | One reusable Spark entry point reads compressed CSV and writes Parquet | Partial |
| Integration probes | PostgreSQL and Redis connectivity tests exist | Not runnable while infrastructure is down |
| Prometheus | Self-scrape configuration exists | Scaffold only |

## Partially implemented or broken

### Runtime and reproducibility

- Docker Desktop is stopped, so service health, image builds, network behavior, database initialization, and Spark execution remain unverified.
- `.venv` is not portable and currently cannot launch. Virtual environments must be recreated, never moved or committed.
- The Spark image previously duplicated a hand-maintained dependency list instead of installing from `pyproject.toml`; Phase 1 centralizes this.
- The Spark smoke script asserts Python 3.12 even though the project supports Python 3.11 and 3.12.

### Ingestion

- CSV schema inference is used; explicit MIMIC schemas are absent.
- Registry fields such as primary keys, format, and partition columns are not used by the writer.
- `overwrite` can replace an existing Bronze dataset and does not provide dataset versioning or replay semantics.
- There is no source checksum, manifest, dataset version, quarantine, schema-drift handling, or structured audit metadata.
- Pipeline audit creation requires PostgreSQL before source validation, coupling file diagnostics to infrastructure availability.
- Exceptions are re-raised, but failure details are not persisted.
- Only `patients` and `admissions` source files are present. The other four configured datasets should fail with an actionable missing-file message.

### Database

- SQL under `database/init` runs only when a new PostgreSQL volume is initialized; editing it does not migrate an existing database.
- Required metadata tables (`dataset_versions`, `model_runs`, `prediction_audit`, and `retrieval_evaluations`) are absent.
- The current DQ result schema cannot represent all required rule metrics and severity.

### Infrastructure and observability

- Kafka, MinIO, Prometheus, Grafana, and Kafka UI use local-development settings; they are not hardened for exposed environments.
- Several third-party images use mutable `latest` tags.
- Prometheus scrapes only itself; no application metrics exist.
- Grafana provisioning and dashboards are absent.
- Redis has no authentication and multiple host ports are exposed. This is acceptable only on a trusted local workstation.

## Missing components

- Silver and Gold transformations, quarantine, DQ framework, and data profiling.
- Readmission cohort, leakage-safe features, training, evaluation, MLflow registration, and serving.
- FastAPI endpoints and operational health/readiness behavior.
- Kafka schemas, producers, consumers, retry/DLQ, and event simulator.
- Embedding, FAISS retrieval, provenance, RAG generation, and evaluations.
- Controlled agent tools and audit trail.
- React/TypeScript application.
- Service metrics, dashboards, structured logging, and correlation propagation.
- Authentication/authorization, rate limiting, threat model, and deployment hardening.
- CI/CD, dependency scanning, Docker build checks, and meaningful test coverage.
- Runbooks, ADRs, data model, security design, and measured benchmarks.

## Duplication and layout findings

- No duplicated business implementation was found because very little product code exists.
- Numerous empty directories imply architecture that has not been implemented; directory names are not evidence of capability.
- No hard-coded Windows filesystem paths were found in source code.
- `PYTHONPATH=/opt/mednexus/src` was used as the primary container import mechanism. Phase 1 installs the package from `pyproject.toml` and removes that implicit import path so packaging is independently verified at image build time.

## Security and data concerns

- No committed `.env` was detected, and no obvious real credential was found in tracked-candidate files.
- Example passwords are present in `.env.example` by design and are now rejected by settings validation for staging/production.
- MIMIC is deidentified but remains controlled clinical data. Raw files must stay ignored, access-controlled, and excluded from logs and artifacts.
- The current Compose stack provides no TLS, secret manager, network segmentation, user authentication, or audit-grade access controls.
- Do not claim HIPAA, FHIR, HL7, or production compliance.

## Test coverage gaps

The original suite contained only two live-service connectivity tests. It had no unit, transformation, failure-mode, API, ML, retrieval, agent, frontend, or end-to-end tests. Phase 1 adds unit tests for settings and registry validation and explicitly marks infrastructure tests as integration tests. Those new tests still require a functioning Python runtime before they can be executed.

## Phase 0 conclusion

The architecture direction is reasonable for a portfolio system, but almost every capability beyond local infrastructure and a first Bronze ingestion script is planned rather than working. Phase 1 must stabilize configuration, packaging, migrations, runtime instructions, and test execution before Bronze is expanded.
