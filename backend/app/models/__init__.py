"""SQLAlchemy ORM models. Importing this package ensures every model is
registered on ``Base.metadata`` so Alembic autogenerate picks them up.
"""
from app.models.appointment_session import AppointmentSession
from app.models.audit_log import AuditLog
from app.models.diagnosis_suggestion import DiagnosisSuggestion
from app.models.enums import (
    AppointmentType,
    PatientSex,
    RedFlagSeverity,
    SessionStatus,
    Speaker,
    TreatmentItemKind,
)
from app.models.protocol import Protocol
from app.models.red_flag import RedFlag
from app.models.transcript import Transcript
from app.models.treatment_plan import TreatmentPlan, TreatmentPlanItem
from app.models.user import User

__all__ = [
    "AppointmentSession",
    "AppointmentType",
    "AuditLog",
    "DiagnosisSuggestion",
    "PatientSex",
    "Protocol",
    "RedFlag",
    "RedFlagSeverity",
    "SessionStatus",
    "Speaker",
    "Transcript",
    "TreatmentItemKind",
    "TreatmentPlan",
    "TreatmentPlanItem",
    "User",
]
