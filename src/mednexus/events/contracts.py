from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class ClinicalEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: UUID = Field(default_factory=uuid4)
    correlation_id: UUID = Field(default_factory=uuid4)
    event_type: Literal["admission.created", "lab.observed", "prediction.requested"]
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    subject_id: int = Field(gt=0)
    hadm_id: int | None = Field(default=None, gt=0)
    schema_version: Literal["1.0"] = "1.0"
    payload: dict[str, Any]


class DeadLetterEvent(BaseModel):
    source_topic: str
    event: ClinicalEvent
    failure_type: str
    failure_message: str
    attempts: int = Field(ge=1, le=10)
    failed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
