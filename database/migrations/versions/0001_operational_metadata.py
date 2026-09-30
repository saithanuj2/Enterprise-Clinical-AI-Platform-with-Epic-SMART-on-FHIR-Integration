"""Create MedNexus operational metadata schemas and tables."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_operational_metadata"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    for schema in ("bronze", "silver", "gold", "ml", "audit"):
        op.execute(sa.text(f"CREATE SCHEMA IF NOT EXISTS {schema}"))
    op.create_table(
        "pipeline_runs",
        sa.Column("run_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("pipeline_name", sa.String(200), nullable=False),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("records_processed", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("records_failed", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("metadata", postgresql.JSONB()),
        schema="audit",
    )
    op.create_table(
        "data_quality_results",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dataset", sa.String(200), nullable=False),
        sa.Column("rule", sa.String(300), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("records_checked", sa.BigInteger(), nullable=False),
        sa.Column("records_failed", sa.BigInteger(), nullable=False),
        sa.Column("failure_percentage", sa.Float(), nullable=False),
        sa.Column("execution_timestamp", sa.DateTime(timezone=True), nullable=False),
        schema="audit",
    )
    for name in ("dataset_versions", "model_runs", "prediction_audit", "retrieval_evaluations"):
        op.create_table(
            name,
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("external_id", sa.String(200), nullable=False, unique=True),
            sa.Column("payload", postgresql.JSONB(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            schema="audit" if name in {"dataset_versions", "retrieval_evaluations"} else "ml",
        )


def downgrade() -> None:
    for name, schema in (
        ("retrieval_evaluations", "audit"),
        ("prediction_audit", "ml"),
        ("model_runs", "ml"),
        ("dataset_versions", "audit"),
        ("data_quality_results", "audit"),
        ("pipeline_runs", "audit"),
    ):
        op.drop_table(name, schema=schema)
