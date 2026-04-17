from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ProtocolOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    complaints: str
    anamnesis: str
    examination: str
    allergies: str
    medications: str
    final_diagnosis: str | None
    icd10_code: str | None
    confirmed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ProtocolPatch(BaseModel):
    complaints: str | None = None
    anamnesis: str | None = None
    examination: str | None = None
    allergies: str | None = None
    medications: str | None = None
    final_diagnosis: str | None = None
    icd10_code: str | None = Field(default=None, max_length=32)


class CustomDiagnosisRequest(BaseModel):
    title: str = Field(min_length=1, max_length=512)
    icd10_code: str | None = Field(default=None, max_length=32)
    reason: str | None = None
