CREATE SCHEMA IF NOT EXISTS bronze;
CREATE SCHEMA IF NOT EXISTS silver;
CREATE SCHEMA IF NOT EXISTS gold;
CREATE SCHEMA IF NOT EXISTS ml;
CREATE SCHEMA IF NOT EXISTS audit;

CREATE TABLE IF NOT EXISTS audit.pipeline_runs (
    run_id UUID PRIMARY KEY,
    pipeline_name VARCHAR(200) NOT NULL,
    status VARCHAR(50) NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    records_processed BIGINT DEFAULT 0,
    records_failed BIGINT DEFAULT 0,
    metadata JSONB
);

CREATE TABLE IF NOT EXISTS audit.data_quality_results (
    id BIGSERIAL PRIMARY KEY,
    run_id UUID,
    dataset_name VARCHAR(200) NOT NULL,
    check_name VARCHAR(200) NOT NULL,
    status VARCHAR(30) NOT NULL,
    observed_value DOUBLE PRECISION,
    threshold_value DOUBLE PRECISION,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS gold.patient_risk_scores (
    id BIGSERIAL PRIMARY KEY,
    patient_id VARCHAR(100) NOT NULL,
    encounter_id VARCHAR(100),
    model_name VARCHAR(100) NOT NULL,
    model_version VARCHAR(50) NOT NULL,
    risk_type VARCHAR(100) NOT NULL,
    risk_probability DOUBLE PRECISION NOT NULL,
    risk_level VARCHAR(30),
    prediction_time TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    explanation JSONB
);

CREATE INDEX IF NOT EXISTS idx_risk_patient
ON gold.patient_risk_scores(patient_id);

CREATE INDEX IF NOT EXISTS idx_risk_prediction_time
ON gold.patient_risk_scores(prediction_time);