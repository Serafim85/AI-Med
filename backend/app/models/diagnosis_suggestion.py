from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Float, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

from ._mixins import CreatedAtMixin, UuidPkMixin


class DiagnosisSuggestion(UuidPkMixin, CreatedAtMixin, Base):
    __tablename__ = "diagnosis_suggestions"

    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("appointment_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    icd10_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    probability: Mapped[float | None] = mapped_column(Float, nullable=True)
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    supporting_symptoms: Mapped[str | None] = mapped_column(Text, nullable=True)
    contradicting_symptoms: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_selected: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
