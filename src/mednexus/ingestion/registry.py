"""Validated loading for metadata-driven ingestion definitions."""

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator


class DatasetConfig(BaseModel):
    """A validated source-to-bronze dataset definition."""

    model_config = ConfigDict(extra="forbid")

    source_file: str
    source_module: str
    format: Literal["csv"]
    bronze_path: str
    primary_keys: list[str] = Field(min_length=1)
    required_columns: list[str] = Field(min_length=1)
    partition_columns: list[str] = Field(default_factory=list)

    @field_validator("source_file", "source_module", "bronze_path")
    @classmethod
    def require_safe_relative_path(cls, value: str) -> str:
        path = Path(value)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("paths must be relative and may not traverse parent directories")
        return value


def load_registry(registry_path: Path) -> dict[str, DatasetConfig]:
    """Load and validate a registry, raising an actionable error for invalid YAML."""

    if not registry_path.is_file():
        raise FileNotFoundError(f"Dataset registry not found: {registry_path}")

    with registry_path.open("r", encoding="utf-8") as file:
        document = yaml.safe_load(file)

    if not isinstance(document, dict) or not isinstance(document.get("datasets"), dict):
        raise TypeError("Dataset registry must contain a 'datasets' mapping")

    return {
        name: DatasetConfig.model_validate(config)
        for name, config in document["datasets"].items()
    }
