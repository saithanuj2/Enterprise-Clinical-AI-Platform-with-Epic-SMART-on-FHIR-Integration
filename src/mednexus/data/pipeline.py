"""Executable Bronze, Silver, Gold, and data-quality pipeline for the MIMIC demo."""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from pyspark.sql import DataFrame, SparkSession, Window
from pyspark.sql import functions as F

from mednexus.data.schemas import SCHEMAS
from mednexus.ingestion.registry import DatasetConfig, load_registry


class SourceValidationError(RuntimeError):
    """Raised when configured source data cannot be processed safely."""


@dataclass(frozen=True)
class DatasetProfile:
    dataset: str
    layer: str
    rows: int
    columns: int
    duplicate_rows: int
    source_bytes: int | None = None


@dataclass(frozen=True)
class PipelineReport:
    run_id: str
    status: str
    started_at: str
    completed_at: str
    duration_seconds: float
    profiles: list[DatasetProfile]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_sources(
    project_root: Path,
    registry: dict[str, DatasetConfig],
    datasets: tuple[str, ...],
) -> dict[str, Path]:
    """Resolve configured sources before Spark or metadata infrastructure is started."""

    resolved: dict[str, Path] = {}
    errors: list[str] = []
    for dataset in datasets:
        if dataset not in registry:
            errors.append(f"unknown dataset '{dataset}'")
            continue
        config = registry[dataset]
        source = project_root / "data" / "raw" / config.source_module / config.source_file
        if not source.is_file():
            errors.append(f"{dataset}: expected {source}")
        elif source.stat().st_size == 0:
            errors.append(f"{dataset}: source is empty: {source}")
        else:
            resolved[dataset] = source
    if errors:
        raise SourceValidationError("Source validation failed:\n- " + "\n- ".join(errors))
    return resolved


def build_spark(project_root: Path) -> SparkSession:
    # Some Windows JDK installers persist JAVA_HOME with literal quotes. Spark's
    # batch launcher treats the embedded space as syntax unless they are removed.
    java_home = os.environ.get("JAVA_HOME")
    if java_home:
        os.environ["JAVA_HOME"] = java_home.strip().strip('"')
    warehouse = project_root / "work" / "spark-warehouse"
    warehouse.mkdir(parents=True, exist_ok=True)
    return (
        SparkSession.builder.master("local[2]")
        .appName("MedNexus-Demo-Medallion")
        .config("spark.sql.shuffle.partitions", "4")
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.sql.warehouse.dir", str(warehouse))
        .getOrCreate()
    )


def read_bronze_source(
    spark: SparkSession,
    dataset: str,
    source: Path,
    run_id: str,
) -> DataFrame:
    schema = SCHEMAS.get(dataset)
    if schema is None:
        raise SourceValidationError(f"No explicit schema is registered for '{dataset}'")
    checksum = sha256_file(source)
    return (
        spark.read.option("header", True)
        .option("mode", "FAILFAST")
        .schema(schema)
        .csv(str(source))
        .withColumn("_ingested_at", F.current_timestamp())
        .withColumn("_source_file", F.lit(source.name))
        .withColumn("_source_sha256", F.lit(checksum))
        .withColumn("_pipeline_run_id", F.lit(run_id))
    )


def _with_reason(frame: DataFrame, reason: str) -> DataFrame:
    return frame.withColumn("_rejection_reason", F.lit(reason))


def silver_patients(bronze: DataFrame) -> tuple[DataFrame, DataFrame]:
    invalid_condition = (
        F.col("subject_id").isNull()
        | (~F.col("gender").isin("M", "F"))
        | (~F.col("anchor_age").between(0, 120))
        | F.col("anchor_year").isNull()
    )
    invalid = bronze.filter(invalid_condition)
    valid = bronze.filter(~invalid_condition)
    window = Window.partitionBy("subject_id").orderBy(F.col("_ingested_at").desc())
    ranked = valid.withColumn("_row_number", F.row_number().over(window))
    duplicates = ranked.filter(F.col("_row_number") > 1).drop("_row_number")
    clean = ranked.filter(F.col("_row_number") == 1).drop("_row_number")
    quarantine = _with_reason(invalid, "INVALID_PATIENT_DOMAIN").unionByName(
        _with_reason(duplicates, "DUPLICATE_SUBJECT_ID"), allowMissingColumns=True
    )
    return clean, quarantine


def silver_admissions(bronze: DataFrame) -> tuple[DataFrame, DataFrame]:
    normalized = (
        bronze.withColumn("admittime", F.to_timestamp("admittime"))
        .withColumn("dischtime", F.to_timestamp("dischtime"))
        .withColumn("deathtime", F.to_timestamp("deathtime"))
        .withColumn("edregtime", F.to_timestamp("edregtime"))
        .withColumn("edouttime", F.to_timestamp("edouttime"))
    )
    invalid_condition = (
        F.col("subject_id").isNull()
        | F.col("hadm_id").isNull()
        | F.col("admittime").isNull()
        | F.col("dischtime").isNull()
        | (F.col("dischtime") < F.col("admittime"))
        | (~F.col("hospital_expire_flag").isin(0, 1))
    )
    invalid = normalized.filter(invalid_condition)
    valid = normalized.filter(~invalid_condition)
    window = Window.partitionBy("hadm_id").orderBy(F.col("_ingested_at").desc())
    ranked = valid.withColumn("_row_number", F.row_number().over(window))
    duplicates = ranked.filter(F.col("_row_number") > 1).drop("_row_number")
    clean = ranked.filter(F.col("_row_number") == 1).drop("_row_number")
    quarantine = _with_reason(invalid, "INVALID_ADMISSION_DOMAIN").unionByName(
        _with_reason(duplicates, "DUPLICATE_HADM_ID"), allowMissingColumns=True
    )
    return clean, quarantine


def build_readmission_features(patients: DataFrame, admissions: DataFrame) -> DataFrame:
    chronology = Window.partitionBy("subject_id").orderBy("admittime", "hadm_id")
    history = chronology.rowsBetween(Window.unboundedPreceding, -1)
    enriched = (
        admissions.join(
            patients.select("subject_id", "gender", "anchor_age", "anchor_year"),
            "subject_id",
            "inner",
        )
        .withColumn("next_admittime", F.lead("admittime").over(chronology))
        .withColumn("days_to_next_admission", F.datediff("next_admittime", "dischtime"))
        .withColumn(
            "readmitted_30d",
            F.when(
                F.col("days_to_next_admission").between(0, 30)
                & (F.col("hospital_expire_flag") == 0),
                1,
            ).otherwise(0),
        )
        .withColumn("prior_admissions", F.count("hadm_id").over(history))
        .fillna({"prior_admissions": 0})
        .withColumn("length_of_stay_days", F.datediff("dischtime", "admittime"))
        .withColumn(
            "age_at_admission",
            F.col("anchor_age") + F.year("admittime") - F.col("anchor_year"),
        )
        .withColumn("prediction_cutoff", F.col("dischtime"))
        .filter(F.col("hospital_expire_flag") == 0)
    )
    return enriched.select(
        "subject_id",
        "hadm_id",
        "prediction_cutoff",
        "gender",
        "admission_type",
        "insurance",
        "age_at_admission",
        "length_of_stay_days",
        "prior_admissions",
        "readmitted_30d",
        "days_to_next_admission",
    )


def build_patient_360(patients: DataFrame, admissions: DataFrame) -> DataFrame:
    summary = admissions.groupBy("subject_id").agg(
        F.countDistinct("hadm_id").alias("admission_count"),
        F.min("admittime").alias("first_admission_at"),
        F.max("dischtime").alias("latest_discharge_at"),
        F.sum("hospital_expire_flag").alias("in_hospital_death_count"),
    )
    return patients.select(
        "subject_id", "gender", "anchor_age", "anchor_year", "anchor_year_group", "dod"
    ).join(summary, "subject_id", "left")


def dq_results(dataset: str, frame: DataFrame, keys: tuple[str, ...]) -> list[dict[str, object]]:
    checked = frame.count()
    null_condition = F.lit(False)
    for key in keys:
        null_condition = null_condition | F.col(key).isNull()
    null_failures = frame.filter(null_condition).count()
    duplicate_failures = checked - frame.dropDuplicates(list(keys)).count()
    now = datetime.now(UTC).isoformat()
    return [
        {
            "dataset": dataset,
            "rule": f"NOT_NULL({','.join(keys)})",
            "status": "PASS" if null_failures == 0 else "FAIL",
            "severity": "CRITICAL",
            "records_checked": checked,
            "records_failed": null_failures,
            "failure_percentage": (100.0 * null_failures / checked) if checked else 0.0,
            "execution_timestamp": now,
        },
        {
            "dataset": dataset,
            "rule": f"UNIQUE({','.join(keys)})",
            "status": "PASS" if duplicate_failures == 0 else "FAIL",
            "severity": "CRITICAL",
            "records_checked": checked,
            "records_failed": duplicate_failures,
            "failure_percentage": (100.0 * duplicate_failures / checked) if checked else 0.0,
            "execution_timestamp": now,
        },
    ]


def _profile(dataset: str, layer: str, frame: DataFrame, keys: list[str]) -> DatasetProfile:
    rows = frame.count()
    duplicates = rows - frame.dropDuplicates(keys).count() if keys and rows else 0
    return DatasetProfile(dataset, layer, rows, len(frame.columns), duplicates)


def run_demo_pipeline(project_root: Path) -> PipelineReport:
    """Run the supported demo pipeline and persist Parquet plus audit JSON artifacts."""

    started = time.perf_counter()
    started_at = datetime.now(UTC).isoformat()
    run_id = str(uuid4())
    registry_path = project_root / "pipelines" / "ingestion" / "dataset_registry.yaml"
    registry = load_registry(registry_path)
    datasets = ("patients", "admissions")
    sources = validate_sources(project_root, registry, datasets)
    spark = build_spark(project_root)
    spark.sparkContext.setLogLevel("WARN")
    profiles: list[DatasetProfile] = []
    quality: list[dict[str, object]] = []
    try:
        bronze: dict[str, DataFrame] = {}
        for dataset in datasets:
            frame = read_bronze_source(spark, dataset, sources[dataset], run_id).cache()
            output = project_root / registry[dataset].bronze_path
            frame.write.mode("overwrite").parquet(str(output))
            bronze[dataset] = frame
            profile = _profile(dataset, "bronze", frame, registry[dataset].primary_keys)
            profiles.append(
                DatasetProfile(**{**asdict(profile), "source_bytes": sources[dataset].stat().st_size})
            )

        silver_patients_frame, patients_quarantine = silver_patients(bronze["patients"])
        silver_admissions_frame, admissions_quarantine = silver_admissions(bronze["admissions"])
        silver_frames = {
            "patients": silver_patients_frame.cache(),
            "admissions": silver_admissions_frame.cache(),
        }
        quarantines = {
            "patients": patients_quarantine,
            "admissions": admissions_quarantine,
        }
        for dataset, frame in silver_frames.items():
            frame.write.mode("overwrite").parquet(str(project_root / "data" / "silver" / dataset))
            quarantines[dataset].write.mode("overwrite").parquet(
                str(project_root / "data" / "quarantine" / dataset)
            )
            profiles.append(_profile(dataset, "silver", frame, registry[dataset].primary_keys))
            quality.extend(dq_results(dataset, frame, tuple(registry[dataset].primary_keys)))

        readmission = build_readmission_features(
            silver_frames["patients"], silver_frames["admissions"]
        ).cache()
        patient_360 = build_patient_360(
            silver_frames["patients"], silver_frames["admissions"]
        ).cache()
        readmission.write.mode("overwrite").parquet(
            str(project_root / "data" / "gold" / "readmission_features")
        )
        patient_360.write.mode("overwrite").parquet(
            str(project_root / "data" / "gold" / "patient_360")
        )
        profiles.append(_profile("readmission_features", "gold", readmission, ["hadm_id"]))
        profiles.append(_profile("patient_360", "gold", patient_360, ["subject_id"]))
    finally:
        spark.stop()

    completed_at = datetime.now(UTC).isoformat()
    report = PipelineReport(
        run_id=run_id,
        status="SUCCESS",
        started_at=started_at,
        completed_at=completed_at,
        duration_seconds=round(time.perf_counter() - started, 3),
        profiles=profiles,
    )
    audit_dir = project_root / "data" / "audit"
    audit_dir.mkdir(parents=True, exist_ok=True)
    (audit_dir / "latest_pipeline_report.json").write_text(
        json.dumps({**asdict(report), "profiles": [asdict(item) for item in profiles]}, indent=2),
        encoding="utf-8",
    )
    (audit_dir / "latest_dq_results.json").write_text(
        json.dumps([{**item, "run_id": run_id} for item in quality], indent=2),
        encoding="utf-8",
    )
    return report
