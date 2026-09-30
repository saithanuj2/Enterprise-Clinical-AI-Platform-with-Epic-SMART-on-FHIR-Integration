"""Pandas execution profile for local/CI validation of the Medallion contracts."""

from __future__ import annotations

import json
import shutil
import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pandas as pd

from mednexus.data.pipeline import DatasetProfile, PipelineReport, sha256_file, validate_sources
from mednexus.ingestion.registry import load_registry


def _replace_parquet_dataset(frame: pd.DataFrame, target: Path, data_root: Path) -> None:
    resolved_target = target.resolve()
    resolved_data = data_root.resolve()
    if resolved_data not in resolved_target.parents:
        raise ValueError(f"Refusing to replace output outside data root: {target}")
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    frame.to_parquet(target / "part-00000.parquet", index=False)


def _profile(
    dataset: str,
    layer: str,
    frame: pd.DataFrame,
    keys: list[str],
    source_bytes: int | None = None,
) -> DatasetProfile:
    return DatasetProfile(
        dataset=dataset,
        layer=layer,
        rows=len(frame),
        columns=len(frame.columns),
        duplicate_rows=int(frame.duplicated(keys).sum()) if keys and len(frame) else 0,
        source_bytes=source_bytes,
    )


def _dq(dataset: str, frame: pd.DataFrame, keys: list[str], run_id: str) -> list[dict[str, object]]:
    checked = len(frame)
    null_failures = int(frame[keys].isna().any(axis=1).sum())
    duplicate_failures = int(frame.duplicated(keys).sum())
    now = datetime.now(UTC).isoformat()
    results: list[dict[str, object]] = []
    for rule, failures in (("NOT_NULL", null_failures), ("UNIQUE", duplicate_failures)):
        results.append(
            {
                "run_id": run_id,
                "dataset": dataset,
                "rule": f"{rule}({','.join(keys)})",
                "status": "PASS" if failures == 0 else "FAIL",
                "severity": "CRITICAL",
                "records_checked": checked,
                "records_failed": failures,
                "failure_percentage": (100.0 * failures / checked) if checked else 0.0,
                "execution_timestamp": now,
            }
        )
    return results


def run_local_demo_pipeline(project_root: Path) -> PipelineReport:
    """Execute the supported demo path without requiring a local Hadoop binary."""

    started = time.perf_counter()
    started_at = datetime.now(UTC).isoformat()
    run_id = str(uuid4())
    data_root = project_root / "data"
    registry = load_registry(project_root / "pipelines" / "ingestion" / "dataset_registry.yaml")
    sources = validate_sources(project_root, registry, ("patients", "admissions"))
    profiles: list[DatasetProfile] = []
    quality: list[dict[str, object]] = []

    patients = pd.read_csv(
        sources["patients"],
        dtype={
            "subject_id": "Int64",
            "gender": "string",
            "anchor_age": "Int64",
            "anchor_year": "Int64",
        },
    )
    admissions = pd.read_csv(
        sources["admissions"],
        dtype={"subject_id": "Int64", "hadm_id": "Int64", "hospital_expire_flag": "Int64"},
    )
    ingested_at = datetime.now(UTC)
    for name, frame in (("patients", patients), ("admissions", admissions)):
        frame["_ingested_at"] = ingested_at
        frame["_source_file"] = sources[name].name
        frame["_source_sha256"] = sha256_file(sources[name])
        frame["_pipeline_run_id"] = run_id
        _replace_parquet_dataset(frame, project_root / registry[name].bronze_path, data_root)
        profiles.append(
            _profile(
                name,
                "bronze",
                frame,
                registry[name].primary_keys,
                sources[name].stat().st_size,
            )
        )

    patient_invalid = (
        patients["subject_id"].isna()
        | ~patients["gender"].isin(["M", "F"])
        | ~patients["anchor_age"].between(0, 120)
        | patients["anchor_year"].isna()
    )
    patients_quarantine = patients.loc[patient_invalid].copy()
    patients_quarantine["_rejection_reason"] = "INVALID_PATIENT_DOMAIN"
    silver_patients = patients.loc[~patient_invalid].drop_duplicates("subject_id", keep="last").copy()

    for column in ["admittime", "dischtime", "deathtime", "edregtime", "edouttime"]:
        admissions[column] = pd.to_datetime(admissions[column], errors="coerce")
    admission_invalid = (
        admissions["subject_id"].isna()
        | admissions["hadm_id"].isna()
        | admissions["admittime"].isna()
        | admissions["dischtime"].isna()
        | (admissions["dischtime"] < admissions["admittime"])
        | ~admissions["hospital_expire_flag"].isin([0, 1])
    )
    admissions_quarantine = admissions.loc[admission_invalid].copy()
    admissions_quarantine["_rejection_reason"] = "INVALID_ADMISSION_DOMAIN"
    silver_admissions = admissions.loc[~admission_invalid].drop_duplicates("hadm_id", keep="last").copy()

    for name, frame, quarantine in (
        ("patients", silver_patients, patients_quarantine),
        ("admissions", silver_admissions, admissions_quarantine),
    ):
        _replace_parquet_dataset(frame, data_root / "silver" / name, data_root)
        _replace_parquet_dataset(quarantine, data_root / "quarantine" / name, data_root)
        profiles.append(_profile(name, "silver", frame, registry[name].primary_keys))
        quality.extend(_dq(name, frame, registry[name].primary_keys, run_id))

    ordered = silver_admissions.sort_values(["subject_id", "admittime", "hadm_id"]).copy()
    ordered["next_admittime"] = ordered.groupby("subject_id")["admittime"].shift(-1)
    ordered["days_to_next_admission"] = (
        ordered["next_admittime"] - ordered["dischtime"]
    ).dt.days
    ordered["prior_admissions"] = ordered.groupby("subject_id").cumcount()
    ordered["length_of_stay_days"] = (ordered["dischtime"] - ordered["admittime"]).dt.days
    features = ordered.merge(
        silver_patients[["subject_id", "gender", "anchor_age", "anchor_year"]],
        on="subject_id",
        how="inner",
        validate="many_to_one",
    )
    features["age_at_admission"] = (
        features["anchor_age"] + features["admittime"].dt.year - features["anchor_year"]
    )
    features["readmitted_30d"] = (
        features["days_to_next_admission"].between(0, 30)
        & features["hospital_expire_flag"].eq(0)
    ).astype("int8")
    features["prediction_cutoff"] = features["dischtime"]
    features = features.loc[
        features["hospital_expire_flag"].eq(0),
        [
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
        ],
    ]

    admission_summary = silver_admissions.groupby("subject_id", as_index=False).agg(
        admission_count=("hadm_id", "nunique"),
        first_admission_at=("admittime", "min"),
        latest_discharge_at=("dischtime", "max"),
        in_hospital_death_count=("hospital_expire_flag", "sum"),
    )
    patient_360 = silver_patients[
        ["subject_id", "gender", "anchor_age", "anchor_year", "anchor_year_group", "dod"]
    ].merge(admission_summary, on="subject_id", how="left", validate="one_to_one")
    _replace_parquet_dataset(features, data_root / "gold" / "readmission_features", data_root)
    _replace_parquet_dataset(patient_360, data_root / "gold" / "patient_360", data_root)
    profiles.append(_profile("readmission_features", "gold", features, ["hadm_id"]))
    profiles.append(_profile("patient_360", "gold", patient_360, ["subject_id"]))

    completed_at = datetime.now(UTC).isoformat()
    report = PipelineReport(
        run_id=run_id,
        status="SUCCESS",
        started_at=started_at,
        completed_at=completed_at,
        duration_seconds=round(time.perf_counter() - started, 3),
        profiles=profiles,
    )
    audit_dir = data_root / "audit"
    audit_dir.mkdir(parents=True, exist_ok=True)
    (audit_dir / "latest_pipeline_report.json").write_text(
        json.dumps({**asdict(report), "engine": "pandas"}, indent=2), encoding="utf-8"
    )
    (audit_dir / "latest_dq_results.json").write_text(
        json.dumps(quality, indent=2), encoding="utf-8"
    )
    return report
