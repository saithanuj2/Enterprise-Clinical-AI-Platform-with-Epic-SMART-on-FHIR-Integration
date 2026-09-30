# Local Runbook

1. Copy `.env.example` to `.env` and change development passwords.
2. Install: `python -m pip install -e ".[dev,spark,ml,api,ai]"`.
3. Run local pipeline: `python pipelines/run_demo_pipeline.py --engine pandas`.
4. Train: `python ml/training/train_readmission.py`.
5. Build retrieval: `python ai/retrieval/build_index.py`.
6. Start API: `uvicorn mednexus.api.app:app --port 8000`.
7. In `apps/web`, run `pnpm install` and `pnpm dev`.
8. Run gates: `ruff check ...`, `mypy src`, `pytest`, `pnpm build`, and `docker compose config --quiet`.

For Docker/Linux, start with `docker compose up -d --build`, inspect `docker compose ps`, apply `alembic upgrade head`, and never use `down -v` without explicit approval. Readiness returning 503 means model, retrieval, or Gold artifacts must be rebuilt. Preserve quarantine and audit JSON when diagnosing pipeline failures.
