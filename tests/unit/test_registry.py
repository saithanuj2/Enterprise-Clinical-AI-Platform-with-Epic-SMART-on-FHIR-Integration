from pathlib import Path

import pytest
from pydantic import ValidationError

from mednexus.ingestion.registry import load_registry


def write_registry(path: Path, bronze_path: str = "data/bronze/patients") -> None:
    path.write_text(
        f"""datasets:
  patients:
    source_file: patients.csv.gz
    source_module: hosp
    format: csv
    bronze_path: {bronze_path}
    primary_keys: [subject_id]
    required_columns: [subject_id]
    partition_columns: []
""",
        encoding="utf-8",
    )


def test_load_registry_validates_dataset(tmp_path: Path):
    path = tmp_path / "registry.yaml"
    write_registry(path)

    registry = load_registry(path)

    assert registry["patients"].source_file == "patients.csv.gz"


def test_load_registry_rejects_path_traversal(tmp_path: Path):
    path = tmp_path / "registry.yaml"
    write_registry(path, "../outside")

    with pytest.raises(ValidationError, match="may not traverse"):
        load_registry(path)


def test_load_registry_reports_missing_file(tmp_path: Path):
    with pytest.raises(FileNotFoundError, match="Dataset registry not found"):
        load_registry(tmp_path / "missing.yaml")
