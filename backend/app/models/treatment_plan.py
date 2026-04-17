from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Enum, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

from ._mixins import TimestampsMixin, UuidPkMixin
from .enums import TreatmentItemKind


class TreatmentPlan(UuidPkMixin, TimestampsMixin, Base):
    __tablename__ = "treatment_plans"

    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("appointment_sessions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )


class TreatmentPlanItem(UuidPkMixin, TimestampsMixin, Base):
    __tablename__ = "treatment_plan_items"

    plan_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("treatment_plans.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    kind: Mapped[TreatmentItemKind] = mapped_column(
        Enum(TreatmentItemKind, name="treatment_item_kind", native_enum=True),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    dosage: Mapped[str | None] = mapped_column(String(255), nullable=True)
    duration: Mapped[str | None] = mapped_column(String(255), nullable=True)
    order_index: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    is_confirmed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
