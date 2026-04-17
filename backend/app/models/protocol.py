from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

from ._mixins import TimestampsMixin, UuidPkMixin


class Protocol(UuidPkMixin, TimestampsMixin, Base):
    __tablename__ = "protocols"

    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("appointment_sessions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    complaints: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    anamnesis: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    examination: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    allergies: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    medications: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    final_diagnosis: Mapped[str | None] = mapped_column(Text, nullable=True)
    icd10_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
