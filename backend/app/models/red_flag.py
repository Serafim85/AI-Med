from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

from ._mixins import CreatedAtMixin, UuidPkMixin
from .enums import RedFlagSeverity


class RedFlag(UuidPkMixin, CreatedAtMixin, Base):
    __tablename__ = "red_flags"

    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("appointment_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    severity: Mapped[RedFlagSeverity | None] = mapped_column(
        Enum(RedFlagSeverity, name="red_flag_severity", native_enum=True),
        nullable=True,
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    doctor_note: Mapped[str | None] = mapped_column(Text, nullable=True)
