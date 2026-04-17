from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

from ._mixins import TimestampsMixin, UuidPkMixin
from .enums import AppointmentType, PatientSex, SessionStatus


class AppointmentSession(UuidPkMixin, TimestampsMixin, Base):
    __tablename__ = "appointment_sessions"

    doctor_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    patient_full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    patient_age: Mapped[int] = mapped_column(Integer, nullable=False)
    patient_sex: Mapped[PatientSex] = mapped_column(
        Enum(PatientSex, name="patient_sex", native_enum=True),
        nullable=False,
    )
    appointment_type: Mapped[AppointmentType] = mapped_column(
        Enum(AppointmentType, name="appointment_type", native_enum=True),
        nullable=False,
    )
    status: Mapped[SessionStatus] = mapped_column(
        Enum(SessionStatus, name="session_status", native_enum=True),
        nullable=False,
        default=SessionStatus.draft,
        server_default=SessionStatus.draft.value,
    )
    consent_given_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
