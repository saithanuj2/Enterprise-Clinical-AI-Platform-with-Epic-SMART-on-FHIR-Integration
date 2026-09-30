# ADR 001: Platform foundations

Accepted 2026-09-26.

- **Spark** is the full-scale batch engine because MIMIC fact tables outgrow single-node memory; Pandas is retained only as a contract-compatible demo/CI profile.
- **PostgreSQL** stores transactional operational metadata, not the clinical lake.
- **Kafka** is reserved for replayable asynchronous admission/lab/prediction events with validated IDs and idempotency.
- **MinIO** provides S3-compatible local artifact storage.
- **MLflow** records dataset identity, parameters, metrics, and model artifacts.
- **FAISS** provides local, inspectable vector search without an external patient-data SaaS dependency.
- **FastAPI/Python** keeps feature, model, retrieval, and API types in one ecosystem. No Node or Go service is added without a measured need.

Alternatives considered: pure PostgreSQL analytics (poor lake-scale fit), Kafka for batch files (unnecessary complexity), hosted vector databases (data/governance dependency), and premature polyglot microservices (operational cost without measured benefit).
