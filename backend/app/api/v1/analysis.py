"""AI analysis endpoints (Step 4).

Implements:

* ``POST /sessions/{id}/analyze`` — full re-analysis pipeline: collect
  transcripts → call :class:`LLMService` → wipe any previous
  ``protocols`` / ``diagnosis_suggestions`` / ``red_flags`` /
  ``treatment_plans`` for the session → persist fresh rows → flip
  session status to ``analyzed``.
* ``GET  /sessions/{id}/analysis`` — full analysis card including the
  per-item ``conflict`` flag (allergy / current-medication heuristic).
* ``PATCH /sessions/{id}/protocol`` — free-form protocol edits.
* ``POST  /sessions/{id}/diagnosis-suggestions/{sid}/select`` — select
  one of the LLM-proposed diagnoses.
* ``POST  /sessions/{id}/protocol/custom-diagnosis`` — doctor types own
  diagnosis, suggestions are deselected.
* ``POST  /sessions/{id}/red-flags/{rid}/acknowledge`` — accept / reject
  a red flag; rejection requires a note.
* Treatment plan items: POST / PATCH / DELETE + ``POST /reorder``.

Conflict detection (medication items) is simple substring matching
between ``title`` and comma/semicolon/newline-separated items from
``protocol.allergies`` and ``protocol.medications``. The ``conflict``
flag is **not** persisted — it is computed on read.

Access control: a session not owned by the current user → HTTP 404
(we never leak existence). Edits forbidden in terminal statuses
(``confirmed``/``closed``) → HTTP 409.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.sessions import _audit, _get_own_session, _load_transcripts
from app.core.security import get_current_user
from app.db.session import get_db
from app.models.appointment_session import AppointmentSession
from app.models.diagnosis_suggestion import DiagnosisSuggestion
from app.models.enums import SessionStatus
from app.models.protocol import Protocol
from app.models.red_flag import RedFlag
from app.models.treatment_plan import TreatmentPlan, TreatmentPlanItem
from app.models.user import User
from app.schemas.analysis import AnalysisOut
from app.schemas.diagnosis import DiagnosisSuggestionOut
from app.schemas.protocol import (
    CustomDiagnosisRequest,
    ProtocolOut,
    ProtocolPatch,
)
from app.schemas.red_flag import RedFlagAcknowledgeRequest, RedFlagOut
from app.schemas.session import SessionOut
from app.schemas.treatment_plan import (
    TreatmentPlanItemCreate,
    TreatmentPlanItemOut,
    TreatmentPlanItemPatch,
    TreatmentPlanOut,
    TreatmentPlanReorderRequest,
)
from app.services.llm import (
    LLMService,
    PatientContext,
    TranscriptTurn,
    get_llm_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["analysis"], prefix="/sessions")


# ---------------------------------------------------------------------------
# Serialization helpers (list<->text in Text columns)
# ---------------------------------------------------------------------------


def _dump_str_list(items: list[str]) -> str:
    """Serialize a list of strings for a Text column (JSON)."""
    return json.dumps(items, ensure_ascii=False)


def _load_str_list(raw: str | None) -> list[str]:
    """Parse the stored JSON array; fall back to empty list on any issue."""
    if not raw:
        return []
    try:
        value = json.loads(raw)
        if isinstance(value, list) and all(isinstance(x, str) for x in value):
            return value
    except json.JSONDecodeError:
        pass
    return []


def _suggestion_out(s: DiagnosisSuggestion) -> DiagnosisSuggestionOut:
    return DiagnosisSuggestionOut(
        id=s.id,
        session_id=s.session_id,
        title=s.title,
        icd10_code=s.icd10_code,
        probability=s.probability,
        reasoning=s.reasoning,
        supporting_symptoms=_load_str_list(s.supporting_symptoms),
        contradicting_symptoms=_load_str_list(s.contradicting_symptoms),
        is_selected=s.is_selected,
    )


# ---------------------------------------------------------------------------
# Conflict detection
# ---------------------------------------------------------------------------


def _tokenize_drug_list(raw: str | None) -> list[str]:
    """Split allergies/medications free text into lowercased tokens.

    Separators: comma, semicolon, newline. Whitespace is trimmed.
    Empty tokens are dropped.
    """
    if not raw:
        return []
    chunk = raw.replace(";", ",").replace("\n", ",")
    return [
        part.strip().lower()
        for part in chunk.split(",")
        if part and part.strip()
    ]


def _has_conflict(
    item_title: str,
    allergies_tokens: list[str],
    medication_tokens: list[str],
) -> bool:
    title = (item_title or "").lower()
    if not title:
        return False
    for token in allergies_tokens:
        if token and token in title:
            return True
    for token in medication_tokens:
        if token and (token in title or title in token):
            return True
    return False


def _plan_item_out(
    item: TreatmentPlanItem,
    *,
    allergies: list[str],
    medications: list[str],
) -> TreatmentPlanItemOut:
    conflict = False
    if item.kind.value == "medication":
        conflict = _has_conflict(item.title, allergies, medications)
    return TreatmentPlanItemOut(
        id=item.id,
        plan_id=item.plan_id,
        kind=item.kind,
        title=item.title,
        details=item.details,
        dosage=item.dosage,
        duration=item.duration,
        order_index=item.order_index,
        is_confirmed=item.is_confirmed,
        conflict=conflict,
    )


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


async def _get_protocol(db: AsyncSession, session_id: uuid.UUID) -> Protocol | None:
    res = await db.execute(select(Protocol).where(Protocol.session_id == session_id))
    return res.scalar_one_or_none()


async def _get_plan(
    db: AsyncSession, session_id: uuid.UUID
) -> TreatmentPlan | None:
    res = await db.execute(
        select(TreatmentPlan).where(TreatmentPlan.session_id == session_id)
    )
    return res.scalar_one_or_none()


async def _get_plan_items(
    db: AsyncSession, plan_id: uuid.UUID
) -> list[TreatmentPlanItem]:
    res = await db.execute(
        select(TreatmentPlanItem)
        .where(TreatmentPlanItem.plan_id == plan_id)
        .order_by(TreatmentPlanItem.order_index.asc(), TreatmentPlanItem.created_at.asc())
    )
    return list(res.scalars().all())


async def _get_suggestions(
    db: AsyncSession, session_id: uuid.UUID
) -> list[DiagnosisSuggestion]:
    res = await db.execute(
        select(DiagnosisSuggestion)
        .where(DiagnosisSuggestion.session_id == session_id)
        .order_by(DiagnosisSuggestion.probability.desc().nullslast())
    )
    return list(res.scalars().all())


async def _get_red_flags(
    db: AsyncSession, session_id: uuid.UUID
) -> list[RedFlag]:
    res = await db.execute(
        select(RedFlag)
        .where(RedFlag.session_id == session_id)
        .order_by(RedFlag.created_at.asc())
    )
    return list(res.scalars().all())


async def _build_analysis_out(
    db: AsyncSession, sess: AppointmentSession
) -> AnalysisOut:
    protocol = await _get_protocol(db, sess.id)
    suggestions = await _get_suggestions(db, sess.id)
    red_flags = await _get_red_flags(db, sess.id)
    plan = await _get_plan(db, sess.id)

    allergies_tokens = _tokenize_drug_list(protocol.allergies if protocol else "")
    medication_tokens = _tokenize_drug_list(protocol.medications if protocol else "")

    plan_out: TreatmentPlanOut | None = None
    if plan is not None:
        items = await _get_plan_items(db, plan.id)
        plan_out = TreatmentPlanOut(
            id=plan.id,
            session_id=plan.session_id,
            items=[
                _plan_item_out(i, allergies=allergies_tokens, medications=medication_tokens)
                for i in items
            ],
        )

    return AnalysisOut(
        session=SessionOut.model_validate(sess),
        protocol=ProtocolOut.model_validate(protocol) if protocol else None,
        diagnosis_suggestions=[_suggestion_out(s) for s in suggestions],
        red_flags=[RedFlagOut.model_validate(r) for r in red_flags],
        treatment_plan=plan_out,
    )


# ---------------------------------------------------------------------------
# Helpers: status gating
# ---------------------------------------------------------------------------


def _ensure_editable(sess: AppointmentSession) -> None:
    """Edits to analysis artefacts are forbidden once the doctor has
    confirmed the protocol (``confirmed``/``closed``).
    """
    if sess.status in (SessionStatus.confirmed, SessionStatus.closed):
        raise HTTPException(
            status_code=409,
            detail="Нельзя редактировать подтверждённую сессию",
        )


async def _ensure_plan(db: AsyncSession, session_id: uuid.UUID) -> TreatmentPlan:
    plan = await _get_plan(db, session_id)
    if plan is None:
        plan = TreatmentPlan(session_id=session_id)
        db.add(plan)
        await db.flush()
    return plan


# ---------------------------------------------------------------------------
# POST /sessions/{id}/analyze
# ---------------------------------------------------------------------------


@router.post("/{session_id}/analyze", response_model=AnalysisOut)
async def analyze_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    llm: LLMService = Depends(get_llm_service),
) -> AnalysisOut:
    sess = await _get_own_session(session_id, db, user)
    if sess.status not in (SessionStatus.draft, SessionStatus.analyzed):
        raise HTTPException(
            status_code=409,
            detail=(
                "Анализ доступен только в статусах «Черновик» или "
                "«Обработан». Остановите запись или снимите подтверждение."
            ),
        )

    transcripts = await _load_transcripts(db, sess.id)
    # Order by started_at_ms (nulls last), then created_at — matches spec 6.3.
    transcripts.sort(
        key=lambda t: (
            t.started_at_ms if t.started_at_ms is not None else 10**18,
            t.created_at,
        )
    )
    if not transcripts:
        raise HTTPException(
            status_code=400,
            detail="Нет реплик для анализа: сначала расшифруйте приём",
        )

    patient = PatientContext(
        age=sess.patient_age,
        sex=sess.patient_sex.value,
        appointment_type=sess.appointment_type.value,
    )
    turns = [TranscriptTurn(speaker=t.speaker.value, text=t.text) for t in transcripts]

    try:
        result = await llm.analyze_dialogue(patient, turns)
    except RuntimeError as exc:
        # Misconfigured OPENAI_API_KEY or transient network failure.
        logger.warning("LLM unavailable: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        # Schema validation failure.
        logger.warning("LLM returned invalid payload: %s", exc)
        raise HTTPException(
            status_code=502,
            detail=f"LLM вернул некорректный ответ: {exc}",
        ) from exc

    # Wipe previous analysis artefacts (re-analysis is supported).
    await db.execute(
        delete(DiagnosisSuggestion).where(DiagnosisSuggestion.session_id == sess.id)
    )
    await db.execute(delete(RedFlag).where(RedFlag.session_id == sess.id))

    existing_plan = await _get_plan(db, sess.id)
    if existing_plan is not None:
        await db.execute(
            delete(TreatmentPlanItem).where(
                TreatmentPlanItem.plan_id == existing_plan.id
            )
        )
        await db.delete(existing_plan)
        await db.flush()

    # Upsert protocol.
    protocol = await _get_protocol(db, sess.id)
    if protocol is None:
        protocol = Protocol(session_id=sess.id)
        db.add(protocol)
    protocol.complaints = result.protocol.complaints
    protocol.anamnesis = result.protocol.anamnesis
    protocol.examination = result.protocol.examination
    protocol.allergies = result.protocol.allergies
    protocol.medications = result.protocol.medications
    # Re-analysis clears any previously chosen final diagnosis.
    protocol.final_diagnosis = None
    protocol.icd10_code = None

    for rf in result.red_flags:
        from app.models.enums import RedFlagSeverity

        db.add(
            RedFlag(
                session_id=sess.id,
                label=rf.label,
                description=rf.description,
                severity=RedFlagSeverity(rf.severity),
            )
        )

    for suggestion in result.diagnosis_suggestions:
        db.add(
            DiagnosisSuggestion(
                session_id=sess.id,
                title=suggestion.title,
                icd10_code=suggestion.icd10_code,
                probability=suggestion.probability,
                reasoning=suggestion.reasoning,
                supporting_symptoms=_dump_str_list(suggestion.supporting_symptoms),
                contradicting_symptoms=_dump_str_list(suggestion.contradicting_symptoms),
                is_selected=False,
            )
        )

    plan = TreatmentPlan(session_id=sess.id)
    db.add(plan)
    await db.flush()
    for idx, item in enumerate(result.treatment_plan):
        from app.models.enums import TreatmentItemKind

        db.add(
            TreatmentPlanItem(
                plan_id=plan.id,
                kind=TreatmentItemKind(item.kind),
                title=item.title,
                details=item.details or None,
                dosage=item.dosage,
                duration=item.duration,
                order_index=idx,
                is_confirmed=False,
            )
        )

    sess.status = SessionStatus.analyzed
    _audit(
        db,
        user_id=user.id,
        session_id=sess.id,
        action="analysis_completed",
        payload={
            "transcripts_count": len(transcripts),
            "suggestions_count": len(result.diagnosis_suggestions),
            "red_flags_count": len(result.red_flags),
            "plan_items_count": len(result.treatment_plan),
        },
    )

    await db.commit()
    await db.refresh(sess)
    return await _build_analysis_out(db, sess)


# ---------------------------------------------------------------------------
# GET /sessions/{id}/analysis
# ---------------------------------------------------------------------------


@router.get("/{session_id}/analysis", response_model=AnalysisOut)
async def get_analysis(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AnalysisOut:
    sess = await _get_own_session(session_id, db, user)
    if sess.status in (SessionStatus.draft, SessionStatus.recording):
        raise HTTPException(
            status_code=409,
            detail="Анализ ещё не выполнен",
        )
    return await _build_analysis_out(db, sess)


# ---------------------------------------------------------------------------
# PATCH /sessions/{id}/protocol
# ---------------------------------------------------------------------------


@router.patch("/{session_id}/protocol", response_model=ProtocolOut)
async def patch_protocol(
    session_id: uuid.UUID,
    payload: ProtocolPatch,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ProtocolOut:
    sess = await _get_own_session(session_id, db, user)
    _ensure_editable(sess)

    protocol = await _get_protocol(db, sess.id)
    if protocol is None:
        raise HTTPException(
            status_code=409,
            detail="Протокол ещё не сформирован — сначала выполните анализ",
        )

    data = payload.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=400, detail="Нет данных для обновления")

    changed_fields: list[str] = []
    for key, value in data.items():
        if getattr(protocol, key) != value:
            setattr(protocol, key, value)
            changed_fields.append(key)

    _audit(
        db,
        user_id=user.id,
        session_id=sess.id,
        action="protocol_updated",
        payload={"fields": changed_fields},
    )
    await db.commit()
    await db.refresh(protocol)
    return ProtocolOut.model_validate(protocol)


# ---------------------------------------------------------------------------
# POST /sessions/{id}/diagnosis-suggestions/{sid}/select
# ---------------------------------------------------------------------------


@router.post(
    "/{session_id}/diagnosis-suggestions/{suggestion_id}/select",
    response_model=ProtocolOut,
)
async def select_diagnosis(
    session_id: uuid.UUID,
    suggestion_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ProtocolOut:
    sess = await _get_own_session(session_id, db, user)
    _ensure_editable(sess)

    res = await db.execute(
        select(DiagnosisSuggestion).where(
            DiagnosisSuggestion.id == suggestion_id,
            DiagnosisSuggestion.session_id == sess.id,
        )
    )
    suggestion = res.scalar_one_or_none()
    if suggestion is None:
        raise HTTPException(status_code=404, detail="Предложение диагноза не найдено")

    protocol = await _get_protocol(db, sess.id)
    if protocol is None:
        raise HTTPException(
            status_code=409,
            detail="Протокол ещё не сформирован — сначала выполните анализ",
        )

    await db.execute(
        update(DiagnosisSuggestion)
        .where(DiagnosisSuggestion.session_id == sess.id)
        .values(is_selected=False)
    )
    suggestion.is_selected = True
    protocol.final_diagnosis = suggestion.title
    protocol.icd10_code = suggestion.icd10_code

    _audit(
        db,
        user_id=user.id,
        session_id=sess.id,
        action="diagnosis_selected",
        payload={"suggestion_id": str(suggestion.id), "title": suggestion.title},
    )
    await db.commit()
    await db.refresh(protocol)
    return ProtocolOut.model_validate(protocol)


# ---------------------------------------------------------------------------
# POST /sessions/{id}/protocol/custom-diagnosis
# ---------------------------------------------------------------------------


@router.post("/{session_id}/protocol/custom-diagnosis", response_model=ProtocolOut)
async def set_custom_diagnosis(
    session_id: uuid.UUID,
    payload: CustomDiagnosisRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ProtocolOut:
    sess = await _get_own_session(session_id, db, user)
    _ensure_editable(sess)

    protocol = await _get_protocol(db, sess.id)
    if protocol is None:
        raise HTTPException(
            status_code=409,
            detail="Протокол ещё не сформирован — сначала выполните анализ",
        )

    await db.execute(
        update(DiagnosisSuggestion)
        .where(DiagnosisSuggestion.session_id == sess.id)
        .values(is_selected=False)
    )
    protocol.final_diagnosis = payload.title.strip()
    protocol.icd10_code = (payload.icd10_code or "").strip() or None

    _audit(
        db,
        user_id=user.id,
        session_id=sess.id,
        action="custom_diagnosis_entered",
        payload={
            "title": protocol.final_diagnosis,
            "icd10_code": protocol.icd10_code,
            "reason": payload.reason,
        },
    )
    await db.commit()
    await db.refresh(protocol)
    return ProtocolOut.model_validate(protocol)


# ---------------------------------------------------------------------------
# POST /sessions/{id}/red-flags/{rid}/acknowledge
# ---------------------------------------------------------------------------


@router.post(
    "/{session_id}/red-flags/{red_flag_id}/acknowledge",
    response_model=RedFlagOut,
)
async def acknowledge_red_flag(
    session_id: uuid.UUID,
    red_flag_id: uuid.UUID,
    payload: RedFlagAcknowledgeRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RedFlagOut:
    sess = await _get_own_session(session_id, db, user)
    _ensure_editable(sess)

    if payload.accepted is False and not (payload.note and payload.note.strip()):
        raise HTTPException(
            status_code=422,
            detail="Для отклонения требуется комментарий",
        )

    res = await db.execute(
        select(RedFlag).where(
            RedFlag.id == red_flag_id,
            RedFlag.session_id == sess.id,
        )
    )
    flag = res.scalar_one_or_none()
    if flag is None:
        raise HTTPException(status_code=404, detail="Красный флаг не найден")

    flag.acknowledged_at = datetime.now(tz=timezone.utc)
    flag.doctor_note = payload.note

    _audit(
        db,
        user_id=user.id,
        session_id=sess.id,
        action="red_flag_acknowledged" if payload.accepted else "red_flag_dismissed",
        payload={"red_flag_id": str(flag.id), "note": payload.note},
    )
    await db.commit()
    await db.refresh(flag)
    return RedFlagOut.model_validate(flag)


# ---------------------------------------------------------------------------
# Treatment plan CRUD
# ---------------------------------------------------------------------------


async def _plan_allergies_medications(
    db: AsyncSession, session_id: uuid.UUID
) -> tuple[list[str], list[str]]:
    proto = await _get_protocol(db, session_id)
    return (
        _tokenize_drug_list(proto.allergies if proto else ""),
        _tokenize_drug_list(proto.medications if proto else ""),
    )


@router.post(
    "/{session_id}/treatment-plan/items",
    response_model=TreatmentPlanItemOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_plan_item(
    session_id: uuid.UUID,
    payload: TreatmentPlanItemCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TreatmentPlanItemOut:
    sess = await _get_own_session(session_id, db, user)
    _ensure_editable(sess)
    plan = await _ensure_plan(db, sess.id)

    order_index = payload.order_index
    if order_index is None:
        max_res = await db.execute(
            select(func.max(TreatmentPlanItem.order_index)).where(
                TreatmentPlanItem.plan_id == plan.id
            )
        )
        current_max = max_res.scalar()
        order_index = (current_max + 1) if current_max is not None else 0

    from app.models.enums import TreatmentItemKind

    item = TreatmentPlanItem(
        plan_id=plan.id,
        kind=TreatmentItemKind(payload.kind.value),
        title=payload.title.strip(),
        details=payload.details,
        dosage=payload.dosage,
        duration=payload.duration,
        order_index=order_index,
        is_confirmed=False,
    )
    db.add(item)
    await db.flush()
    _audit(
        db,
        user_id=user.id,
        session_id=sess.id,
        action="plan_item_added",
        payload={"item_id": str(item.id), "kind": item.kind.value, "title": item.title},
    )
    await db.commit()
    await db.refresh(item)

    allergies, meds = await _plan_allergies_medications(db, sess.id)
    return _plan_item_out(item, allergies=allergies, medications=meds)


@router.patch(
    "/{session_id}/treatment-plan/items/{item_id}",
    response_model=TreatmentPlanItemOut,
)
async def patch_plan_item(
    session_id: uuid.UUID,
    item_id: uuid.UUID,
    payload: TreatmentPlanItemPatch,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TreatmentPlanItemOut:
    sess = await _get_own_session(session_id, db, user)
    _ensure_editable(sess)
    plan = await _get_plan(db, sess.id)
    if plan is None:
        raise HTTPException(status_code=404, detail="План лечения не найден")

    res = await db.execute(
        select(TreatmentPlanItem).where(
            TreatmentPlanItem.id == item_id,
            TreatmentPlanItem.plan_id == plan.id,
        )
    )
    item = res.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Пункт плана не найден")

    data: dict[str, Any] = payload.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=400, detail="Нет данных для обновления")

    changed: list[str] = []
    for field_name, value in data.items():
        if field_name == "title" and isinstance(value, str):
            value = value.strip()
        setattr(item, field_name, value)
        changed.append(field_name)

    _audit(
        db,
        user_id=user.id,
        session_id=sess.id,
        action="plan_item_updated",
        payload={"item_id": str(item.id), "fields": changed},
    )
    await db.commit()
    await db.refresh(item)

    allergies, meds = await _plan_allergies_medications(db, sess.id)
    return _plan_item_out(item, allergies=allergies, medications=meds)


@router.delete(
    "/{session_id}/treatment-plan/items/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_plan_item(
    session_id: uuid.UUID,
    item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    sess = await _get_own_session(session_id, db, user)
    _ensure_editable(sess)
    plan = await _get_plan(db, sess.id)
    if plan is None:
        raise HTTPException(status_code=404, detail="План лечения не найден")

    res = await db.execute(
        select(TreatmentPlanItem).where(
            TreatmentPlanItem.id == item_id,
            TreatmentPlanItem.plan_id == plan.id,
        )
    )
    item = res.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Пункт плана не найден")

    await db.delete(item)
    _audit(
        db,
        user_id=user.id,
        session_id=sess.id,
        action="plan_item_deleted",
        payload={"item_id": str(item_id)},
    )
    await db.commit()
    return None


@router.post(
    "/{session_id}/treatment-plan/reorder",
    response_model=TreatmentPlanOut,
)
async def reorder_plan_items(
    session_id: uuid.UUID,
    payload: TreatmentPlanReorderRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TreatmentPlanOut:
    """Bulk-update ``order_index`` on the given plan items.

    Behaviour: any item listed in ``ordered_ids`` gets its
    ``order_index`` set to its position in the array (0-based). Items
    belonging to the plan but missing from ``ordered_ids`` are pushed
    to the end, keeping their relative order among themselves.

    Ids from a different plan (or missing entirely) are ignored.
    """
    sess = await _get_own_session(session_id, db, user)
    _ensure_editable(sess)
    plan = await _get_plan(db, sess.id)
    if plan is None:
        raise HTTPException(status_code=404, detail="План лечения не найден")

    items = await _get_plan_items(db, plan.id)
    by_id = {i.id: i for i in items}
    present_ids: list[uuid.UUID] = []
    for idx, raw_id in enumerate(payload.ordered_ids):
        item = by_id.get(raw_id)
        if item is None:
            continue
        item.order_index = idx
        present_ids.append(raw_id)

    # Untouched items go after.
    offset = len(present_ids)
    for item in items:
        if item.id in present_ids:
            continue
        item.order_index = offset
        offset += 1

    _audit(
        db,
        user_id=user.id,
        session_id=sess.id,
        action="plan_items_reordered",
        payload={"ordered_ids": [str(i) for i in present_ids]},
    )
    await db.commit()

    allergies, meds = await _plan_allergies_medications(db, sess.id)
    refreshed = await _get_plan_items(db, plan.id)
    return TreatmentPlanOut(
        id=plan.id,
        session_id=plan.session_id,
        items=[
            _plan_item_out(i, allergies=allergies, medications=meds) for i in refreshed
        ],
    )
