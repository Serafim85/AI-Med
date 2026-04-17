from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field


class DiagnosisSuggestionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    title: str
    icd10_code: str | None
    probability: float | None
    reasoning: str | None
    supporting_symptoms: list[str] = Field(default_factory=list)
    contradicting_symptoms: list[str] = Field(default_factory=list)
    is_selected: bool
