from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import Speaker


class TranscriptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    speaker: Speaker
    text: str
    started_at_ms: int | None
    ended_at_ms: int | None
    confidence: float | None
    edited_by_user: bool
    created_at: datetime


class TranscriptPatch(BaseModel):
    text: str | None = Field(default=None, min_length=0)
    speaker: Speaker | None = None
