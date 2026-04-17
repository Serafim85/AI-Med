from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import AppointmentType, PatientSex, SessionStatus
from app.schemas.transcript import TranscriptOut


class SessionCreate(BaseModel):
    patient_full_name: str = Field(min_length=1, max_length=255)
    patient_age: int = Field(ge=0, le=120)
    patient_sex: PatientSex
    appointment_type: AppointmentType


class SessionPatch(BaseModel):
    patient_full_name: str | None = Field(default=None, min_length=1, max_length=255)
    patient_age: int | None = Field(default=None, ge=0, le=120)
    patient_sex: PatientSex | None = None
    appointment_type: AppointmentType | None = None


class ConsentRequest(BaseModel):
    granted: bool


class SessionBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    doctor_id: uuid.UUID
    patient_full_name: str
    patient_age: int
    patient_sex: PatientSex
    appointment_type: AppointmentType
    status: SessionStatus
    consent_given_at: datetime | None
    created_at: datetime
    updated_at: datetime


class SessionOut(SessionBase):
    final_diagnosis: str | None = None


class SessionDetailOut(SessionBase):
    final_diagnosis: str | None = None
    transcripts: list[TranscriptOut] = Field(default_factory=list)


class SessionListOut(BaseModel):
    items: list[SessionOut]
    total: int
    limit: int
    offset: int
