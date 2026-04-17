from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import TreatmentItemKind


class TreatmentPlanItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    plan_id: uuid.UUID
    kind: TreatmentItemKind
    title: str
    details: str | None
    dosage: str | None
    duration: str | None
    order_index: int
    is_confirmed: bool
    conflict: bool = False


class TreatmentPlanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    items: list[TreatmentPlanItemOut] = Field(default_factory=list)


class TreatmentPlanItemCreate(BaseModel):
    kind: TreatmentItemKind
    title: str = Field(min_length=1, max_length=512)
    details: str | None = None
    dosage: str | None = Field(default=None, max_length=255)
    duration: str | None = Field(default=None, max_length=255)
    order_index: int | None = Field(default=None, ge=0)


class TreatmentPlanItemPatch(BaseModel):
    kind: TreatmentItemKind | None = None
    title: str | None = Field(default=None, min_length=1, max_length=512)
    details: str | None = None
    dosage: str | None = Field(default=None, max_length=255)
    duration: str | None = Field(default=None, max_length=255)
    order_index: int | None = Field(default=None, ge=0)
    is_confirmed: bool | None = None


class TreatmentPlanReorderRequest(BaseModel):
    ordered_ids: list[uuid.UUID]
