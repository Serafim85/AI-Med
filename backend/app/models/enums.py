"""Enumerations used in ORM models. Names match the Postgres type names."""
from __future__ import annotations

import enum


class PatientSex(str, enum.Enum):
    male = "male"
    female = "female"
    other = "other"


class AppointmentType(str, enum.Enum):
    primary = "primary"
    follow_up = "follow_up"


class SessionStatus(str, enum.Enum):
    draft = "draft"
    recording = "recording"
    analyzed = "analyzed"
    confirmed = "confirmed"
    closed = "closed"


class Speaker(str, enum.Enum):
    doctor = "doctor"
    patient = "patient"
    unknown = "unknown"


class RedFlagSeverity(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"


class TreatmentItemKind(str, enum.Enum):
    medication = "medication"
    investigation = "investigation"
    non_drug = "non_drug"
    follow_up = "follow_up"
