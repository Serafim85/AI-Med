from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import RedFlagSeverity


class RedFlagOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    label: str
    description: str | None
    severity: RedFlagSeverity | None
    acknowledged_at: datetime | None
    doctor_note: str | None


class RedFlagAcknowledgeRequest(BaseModel):
    accepted: bool
    note: str | None = None
