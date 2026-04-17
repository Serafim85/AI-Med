from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Enum, Float, ForeignKey, Integer, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

from ._mixins import CreatedAtMixin, UuidPkMixin
from .enums import Speaker


class Transcript(UuidPkMixin, CreatedAtMixin, Base):
    __tablename__ = "transcripts"

    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("appointment_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    speaker: Mapped[Speaker] = mapped_column(
        Enum(Speaker, name="speaker", native_enum=True),
        nullable=False,
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    started_at_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ended_at_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    edited_by_user: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
