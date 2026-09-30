# Security Posture

- Secrets are environment-backed and redacted by Pydantic; example credentials are rejected in staging/production.
- Raw/derived data, models, indexes, MLflow runs, virtual environments, and local work files are Git-ignored.
- API inputs have length/range limits, CORS is allowlisted for local development, and request IDs are returned.
- Containers use a non-root API user. The local Compose network is plaintext and is not a production security boundary.
- Logs and metrics must not contain patient content. MIMIC identifiers remain deidentified but controlled.
- No HIPAA, FHIR, HL7, or production-compliance claim is made.

Before external deployment: add identity/RBAC, TLS, rate limiting at the gateway, a secret manager, image/dependency scanning, signed images, network policies, backups, audit retention, and a formal threat model.
