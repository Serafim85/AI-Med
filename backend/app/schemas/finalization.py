"""Schemas for Step 5 — final protocol summary, confirmation & closing."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import (
    AppointmentType,
    PatientSex,
    RedFlagSeverity,
    SessionStatus,
    TreatmentItemKind,
)
from app.schemas.protocol import ProtocolOut
from app.schemas.session import SessionOut


class DoctorInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str


class SelectedDiagnosisInfo(BaseModel):
    title: str
    icd10_code: str | None = None


class RedFlagSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    label: str
    description: str | None
    severity: RedFlagSeverity | None
    acknowledged_at: datetime | None
    doctor_note: str | None


class TreatmentItemSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: TreatmentItemKind
    title: str
    details: str | None
    dosage: str | None
    duration: str | None
    order_index: int
    is_confirmed: bool


class SessionSummaryBlock(BaseModel):
    """A subset of ``SessionOut`` used inside the summary card."""

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


class SessionSummaryOut(BaseModel):
    session: SessionSummaryBlock
    doctor: DoctorInfo
    protocol: ProtocolOut | None
    selected_diagnosis: SelectedDiagnosisInfo | None
    red_flags: list[RedFlagSummary]
    treatment_plan_items: list[TreatmentItemSummary]


class ConfirmSessionOut(BaseModel):
    session: SessionOut
    protocol: ProtocolOut


class CloseSessionOut(BaseModel):
    session: SessionOut
