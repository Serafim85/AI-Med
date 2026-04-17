from __future__ import annotations

from pydantic import BaseModel

from app.schemas.diagnosis import DiagnosisSuggestionOut
from app.schemas.protocol import ProtocolOut
from app.schemas.red_flag import RedFlagOut
from app.schemas.session import SessionOut
from app.schemas.treatment_plan import TreatmentPlanOut


class AnalysisOut(BaseModel):
    session: SessionOut
    protocol: ProtocolOut | None
    diagnosis_suggestions: list[DiagnosisSuggestionOut]
    red_flags: list[RedFlagOut]
    treatment_plan: TreatmentPlanOut | None
