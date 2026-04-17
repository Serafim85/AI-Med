"""Step 5 — finalization endpoints.

* ``GET /sessions/{id}/summary`` — aggregated data for the confirm screen;
* ``POST /sessions/{id}/confirm`` — validate & confirm the protocol;
* ``GET /sessions/{id}/pdf`` — render + stream the protocol PDF;
* ``POST /sessions/{id}/close`` — move a confirmed session to closed.

All endpoints require auth. Non-owned sessions → 404 (never leak existence).
Status gating mirrors the spec in ``plan/step-5.md``:

* ``/summary`` — analyzed/confirmed/closed only, else 409;
* ``/confirm`` — analyzed only (409 otherwise); 422 on precondition
  violations (missing final_diagnosis / pending red_flags / unconfirmed
  plan items);
* ``/pdf`` — confirmed/closed only, else 409;
* ``/close`` — confirmed only, else 409.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.sessions import _audit, _get_own_session
from app.core.security import get_current_user
from app.db.session import get_db
from app.models.appointment_session import AppointmentSession
from app.models.diagnosis_suggestion import DiagnosisSuggestion
from app.models.enums import SessionStatus
from app.models.protocol import Protocol
from app.models.red_flag import RedFlag
from app.models.treatment_plan import TreatmentPlan, TreatmentPlanItem
from app.models.user import User
from app.schemas.finalization import (
    CloseSessionOut,
    ConfirmSessionOut,
    DoctorInfo,
    RedFlagSummary,
    SelectedDiagnosisInfo,
    SessionSummaryBlock,
    SessionSummaryOut,
    TreatmentItemSummary,
)
from app.schemas.protocol import ProtocolOut
from app.schemas.session import SessionOut
from app.services.pdf import (
    PdfService,
    ProtocolPdfData,
    ProtocolPdfDoctor,
    ProtocolPdfPatient,
    ProtocolPdfRedFlag,
    ProtocolPdfTreatmentGroup,
    ProtocolPdfTreatmentItem,
    get_pdf_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["finalization"], prefix="/sessions")


# ---------------------------------------------------------------------------
# Loaders (mirror analysis.py but kept local to avoid import cycles)
# ---------------------------------------------------------------------------


async def _load_protocol(db: AsyncSession, session_id: uuid.UUID) -> Protocol | None:
    return (
        await db.execute(select(Protocol).where(Protocol.session_id == session_id))
    ).scalar_one_or_none()


async def _load_red_flags(
    db: AsyncSession, session_id: uuid.UUID
) -> list[RedFlag]:
    rows = await db.execute(
        select(RedFlag)
        .where(RedFlag.session_id == session_id)
        .order_by(RedFlag.created_at.asc())
    )
    return list(rows.scalars().all())


async def _load_plan_items(
    db: AsyncSession, session_id: uuid.UUID
) -> list[TreatmentPlanItem]:
    plan = (
        await db.execute(
            select(TreatmentPlan).where(TreatmentPlan.session_id == session_id)
        )
    ).scalar_one_or_none()
    if plan is None:
        return []
    rows = await db.execute(
        select(TreatmentPlanItem)
        .where(TreatmentPlanItem.plan_id == plan.id)
        .order_by(
            TreatmentPlanItem.order_index.asc(),
            TreatmentPlanItem.created_at.asc(),
        )
    )
    return list(rows.scalars().all())


async def _load_selected_suggestion(
    db: AsyncSession, session_id: uuid.UUID
) -> DiagnosisSuggestion | None:
    rows = await db.execute(
        select(DiagnosisSuggestion)
        .where(
            DiagnosisSuggestion.session_id == session_id,
            DiagnosisSuggestion.is_selected.is_(True),
        )
    )
    return rows.scalars().first()


# ---------------------------------------------------------------------------
# GET /sessions/{id}/summary
# ---------------------------------------------------------------------------


_SUMMARY_STATUSES = {
    SessionStatus.analyzed,
    SessionStatus.confirmed,
    SessionStatus.closed,
}


@router.get("/{session_id}/summary", response_model=SessionSummaryOut)
async def get_session_summary(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SessionSummaryOut:
    sess = await _get_own_session(session_id, db, user)
    if sess.status not in _SUMMARY_STATUSES:
        raise HTTPException(
            status_code=409,
            detail="Итоговая карточка доступна после выполнения анализа",
        )

    protocol = await _load_protocol(db, sess.id)
    red_flags = await _load_red_flags(db, sess.id)
    plan_items = await _load_plan_items(db, sess.id)
    selected = await _load_selected_suggestion(db, sess.id)

    doctor = (
        await db.execute(select(User).where(User.id == sess.doctor_id))
    ).scalar_one()

    selected_info: SelectedDiagnosisInfo | None = None
    if protocol and protocol.final_diagnosis:
        selected_info = SelectedDiagnosisInfo(
            title=protocol.final_diagnosis,
            icd10_code=protocol.icd10_code,
        )
    elif selected is not None:
        selected_info = SelectedDiagnosisInfo(
            title=selected.title,
            icd10_code=selected.icd10_code,
        )

    return SessionSummaryOut(
        session=SessionSummaryBlock.model_validate(sess),
        doctor=DoctorInfo.model_validate(doctor),
        protocol=ProtocolOut.model_validate(protocol) if protocol else None,
        selected_diagnosis=selected_info,
        red_flags=[RedFlagSummary.model_validate(rf) for rf in red_flags],
        treatment_plan_items=[
            TreatmentItemSummary.model_validate(i) for i in plan_items
        ],
    )


# ---------------------------------------------------------------------------
# POST /sessions/{id}/confirm
# ---------------------------------------------------------------------------


@router.post("/{session_id}/confirm", response_model=ConfirmSessionOut)
async def confirm_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ConfirmSessionOut:
    sess = await _get_own_session(session_id, db, user)

    # 1. Status gate: must be analyzed.
    if sess.status != SessionStatus.analyzed:
        raise HTTPException(
            status_code=409,
            detail=(
                "Подтверждение доступно только для сессии в статусе «Обработан»."
            ),
        )

    # 2. Final diagnosis required.
    protocol = await _load_protocol(db, sess.id)
    if protocol is None or not (protocol.final_diagnosis or "").strip():
        raise HTTPException(
            status_code=422,
            detail="Не выбран финальный диагноз",
        )

    # 3. All red flags must be acknowledged.
    red_flags = await _load_red_flags(db, sess.id)
    unresolved = [rf for rf in red_flags if rf.acknowledged_at is None]
    if unresolved:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Не обработано красных флагов: {len(unresolved)}. "
                "Отметьте каждый как принятый или отклонённый."
            ),
        )

    # 4. Every plan item must be confirmed (an empty plan is allowed).
    plan_items = await _load_plan_items(db, sess.id)
    unconfirmed = [i for i in plan_items if not i.is_confirmed]
    if unconfirmed:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Не подтверждено пунктов плана лечения: {len(unconfirmed)}. "
                "Подтвердите или удалите их перед финализацией."
            ),
        )

    protocol.confirmed_at = datetime.now(tz=timezone.utc)
    sess.status = SessionStatus.confirmed

    _audit(
        db,
        user_id=user.id,
        session_id=sess.id,
        action="protocol_confirmed",
    )

    await db.commit()
    await db.refresh(sess)
    await db.refresh(protocol)

    return ConfirmSessionOut(
        session=SessionOut.model_validate(sess),
        protocol=ProtocolOut.model_validate(protocol),
    )


# ---------------------------------------------------------------------------
# GET /sessions/{id}/pdf
# ---------------------------------------------------------------------------


_PDF_STATUSES = {SessionStatus.confirmed, SessionStatus.closed}

_SEX_LABEL = {"male": "Мужской", "female": "Женский", "other": "Другой"}
_APPT_LABEL = {"primary": "Первичный", "follow_up": "Повторный"}
_KIND_LABEL = {
    "medication": "Медикаменты",
    "investigation": "Обследования",
    "non_drug": "Немедикаментозные рекомендации",
    "follow_up": "Контрольный визит",
}
_KIND_ORDER = ["medication", "investigation", "non_drug", "follow_up"]
_SEVERITY_LABEL = {"low": "Низкая", "medium": "Средняя", "high": "Высокая"}


def _format_dt(dt: datetime | None) -> str:
    if dt is None:
        return "—"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.strftime("%d.%m.%Y %H:%M")


async def _build_pdf_data(
    db: AsyncSession,
    sess: AppointmentSession,
) -> ProtocolPdfData:
    protocol = await _load_protocol(db, sess.id)
    red_flags = await _load_red_flags(db, sess.id)
    plan_items = await _load_plan_items(db, sess.id)
    doctor = (
        await db.execute(select(User).where(User.id == sess.doctor_id))
    ).scalar_one()

    rf_items: list[ProtocolPdfRedFlag] = []
    for rf in red_flags:
        if rf.acknowledged_at is None:
            continue  # Only include processed flags in the final document.
        severity_label = _SEVERITY_LABEL.get(
            rf.severity.value if rf.severity else "", ""
        )
        # "accepted" heuristic: the doctor left no note → принято; note → отклонено.
        accepted = not (rf.doctor_note and rf.doctor_note.strip())
        rf_items.append(
            ProtocolPdfRedFlag(
                label=rf.label,
                description=rf.description,
                severity=severity_label,
                accepted=accepted,
                note=rf.doctor_note,
            )
        )

    grouped: dict[str, list[ProtocolPdfTreatmentItem]] = {}
    for item in plan_items:
        grouped.setdefault(item.kind.value, []).append(
            ProtocolPdfTreatmentItem(
                title=item.title,
                details=item.details,
                dosage=item.dosage,
                duration=item.duration,
                is_confirmed=item.is_confirmed,
            )
        )
    treatment_groups: list[ProtocolPdfTreatmentGroup] = []
    for kind in _KIND_ORDER:
        if grouped.get(kind):
            treatment_groups.append(
                ProtocolPdfTreatmentGroup(
                    kind_label=_KIND_LABEL[kind],
                    items=grouped[kind],
                )
            )

    appointment_date = _format_dt(sess.created_at)

    return ProtocolPdfData(
        session_id=str(sess.id),
        appointment_type=_APPT_LABEL.get(sess.appointment_type.value, sess.appointment_type.value),
        appointment_date=appointment_date,
        patient=ProtocolPdfPatient(
            full_name=sess.patient_full_name,
            age=sess.patient_age,
            sex=_SEX_LABEL.get(sess.patient_sex.value, sess.patient_sex.value),
        ),
        doctor=ProtocolPdfDoctor(full_name=doctor.full_name),
        complaints=(protocol.complaints if protocol else "") or "",
        anamnesis=(protocol.anamnesis if protocol else "") or "",
        examination=(protocol.examination if protocol else "") or "",
        allergies=(protocol.allergies if protocol else "") or "",
        medications=(protocol.medications if protocol else "") or "",
        final_diagnosis=(protocol.final_diagnosis if protocol else None),
        icd10_code=(protocol.icd10_code if protocol else None),
        red_flags=rf_items,
        treatment_groups=treatment_groups,
    )


@router.get("/{session_id}/pdf")
async def download_session_pdf(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    pdf_service: PdfService = Depends(get_pdf_service),
) -> Response:
    sess = await _get_own_session(session_id, db, user)
    if sess.status not in _PDF_STATUSES:
        raise HTTPException(
            status_code=409,
            detail="PDF доступен только после подтверждения протокола",
        )

    data = await _build_pdf_data(db, sess)
    try:
        pdf_bytes = pdf_service.render_protocol_pdf(data)
    except RuntimeError as exc:
        logger.exception("PDF rendering failed: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    _audit(
        db,
        user_id=user.id,
        session_id=sess.id,
        action="pdf_generated",
    )
    await db.commit()

    filename = f"protocol_{sess.id}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# POST /sessions/{id}/close
# ---------------------------------------------------------------------------


@router.post("/{session_id}/close", response_model=CloseSessionOut)
async def close_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CloseSessionOut:
    sess = await _get_own_session(session_id, db, user)
    if sess.status != SessionStatus.confirmed:
        raise HTTPException(
            status_code=409,
            detail="Закрыть можно только подтверждённую сессию",
        )
    sess.status = SessionStatus.closed
    _audit(
        db,
        user_id=user.id,
        session_id=sess.id,
        action="session_closed",
    )
    await db.commit()
    await db.refresh(sess)
    return CloseSessionOut(session=SessionOut.model_validate(sess))
