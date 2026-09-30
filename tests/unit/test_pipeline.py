from pathlib import Path

import pytest

from mednexus.data.pipeline import SourceValidationError, validate_sources
from mednexus.ingestion.registry import DatasetConfig


def dataset_config(source_file: str) -> DatasetConfig:
    return DatasetConfig(
        source_file=source_file,
        source_module="hosp",
        format="csv",
        bronze_path="data/bronze/test",
        primary_keys=["subject_id"],
        required_columns=["subject_id"],
    )


def test_validate_sources_reports_all_missing_files(tmp_path: Path):
    registry = {
        "patients": dataset_config("patients.csv.gz"),
        "admissions": dataset_config("admissions.csv.gz"),
    }

    with pytest.raises(SourceValidationError) as error:
        validate_sources(tmp_path, registry, ("patients", "admissions"))

    message = str(error.value)
    assert "patients" in message
    assert "admissions" in message


def test_validate_sources_accepts_nonempty_file(tmp_path: Path):
    source = tmp_path / "data" / "raw" / "hosp" / "patients.csv.gz"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"not-empty")

    result = validate_sources(
        tmp_path,
        {"patients": dataset_config("patients.csv.gz")},
        ("patients",),
    )

    assert result["patients"] == source
