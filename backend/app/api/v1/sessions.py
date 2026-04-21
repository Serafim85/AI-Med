"""Appointment session lifecycle endpoints (Step 3).

Scope:
* CRUD of own sessions (list / get / create / patch patient data)
* Consent fixation (granted / denied)
* Recording start / stop / delete
* Per-chunk transcript upload via Whisper ASR, manual edits, deletions

All endpoints require auth. A doctor can only see/modify their own
sessions — otherwise we return 404 (not 403) to avoid leaking existence.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db.session import get_db
from app.models.appointment_session import AppointmentSession
from app.models.audit_log import AuditLog
from app.models.enums import SessionStatus, Speaker
from app.models.transcript import Transcript
from app.models.user import User
from app.schemas.session import (
    ConsentRequest,
    SessionCreate,
    SessionDetailOut,
    SessionListOut,
    SessionOut,
    SessionPatch,
)
from app.schemas.transcript import TranscriptOut, TranscriptPatch
from app.services.asr import ASRService, get_asr_service

router = APIRouter(tags=["sessions"], prefix="/sessions")


async def _get_own_session(
    session_id: uuid.UUID,
    db: AsyncSession,
    user: User,
) -> AppointmentSession:
    stmt = select(AppointmentSession).where(
        AppointmentSession.id == session_id,
        AppointmentSession.doctor_id == user.id,
    )
    result = await db.execute(stmt)
    sess = result.scalar_one_or_none()
    if sess is None:
        raise HTTPException(status_code=404, detail="Сессия не найдена")
    return sess


def _ensure_not_finalized(sess: AppointmentSession) -> None:
    """Mutating session-level actions are forbidden for confirmed/closed."""
    if sess.status in (SessionStatus.confirmed, SessionStatus.closed):
        raise HTTPException(
            status_code=409,
            detail="Сессия уже подтверждена или закрыта — изменения запрещены",
        )


def _ensure_not_closed(sess: AppointmentSession) -> None:
    """Block any modification of a closed session (including transcripts)."""
    if sess.status == SessionStatus.closed:
        raise HTTPException(
            status_code=409,
            detail="Сессия закрыта — изменения запрещены",
        )


async def _load_transcripts(db: AsyncSession, session_id: uuid.UUID) -> list[Transcript]:
    result = await db.execute(
        select(Transcript)
        .where(Transcript.session_id == session_id)
        .order_by(Transcript.created_at.asc())
    )
    return list(result.scalars().all())


def _audit(
    db: AsyncSession,
    *,
    user_id: uuid.UUID | None,
    session_id: uuid.UUID | None,
    action: str,
    payload: dict[str, Any] | None = None,
) -> None:
    db.add(
        AuditLog(
            user_id=user_id,
            session_id=session_id,
            action=action,
            payload_json=payload,
        )
    )


@router.post("", response_model=SessionOut, status_code=status.HTTP_201_CREATED)
async def create_session(
    payload: SessionCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SessionOut:
    sess = AppointmentSession(
        doctor_id=user.id,
        patient_full_name=payload.patient_full_name.strip(),
        patient_age=payload.patient_age,
        patient_sex=payload.patient_sex,
        appointment_type=payload.appointment_type,
        status=SessionStatus.draft,
    )
    db.add(sess)
    await db.flush()
    _audit(
        db,
        user_id=user.id,
        session_id=sess.id,
        action="session_created",
        payload={"appointment_type": payload.appointment_type.value},
    )
    await db.commit()
    await db.refresh(sess)
    return SessionOut.model_validate(sess)


@router.get("", response_model=SessionListOut)
async def list_sessions(
    status: str | None = Query(default=None),
    query: str | None = Query(default=None, max_length=255),
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SessionListOut:
    from app.models.protocol import Protocol

    filters = [AppointmentSession.doctor_id == user.id]

    if status and status != "all":
        try:
            status_enum = SessionStatus(status)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Неизвестный статус сессии: {status}",
            ) from exc
        filters.append(AppointmentSession.status == status_enum)

    if query:
        q = query.strip()
        if q:
            # ILIKE on Postgres; SQLAlchemy translates to LOWER(col) LIKE LOWER(?)
            # on SQLite (which is ASCII-only for LOWER — good enough for MVP).
            filters.append(
                AppointmentSession.patient_full_name.ilike(f"%{q}%")
            )

    total_stmt = select(func.count(AppointmentSession.id)).where(*filters)
    total = (await db.execute(total_stmt)).scalar_one()

    stmt = (
        select(AppointmentSession, Protocol.final_diagnosis)
        .outerjoin(Protocol, Protocol.session_id == AppointmentSession.id)
        .where(*filters)
        .order_by(AppointmentSession.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = (await db.execute(stmt)).all()

    items: list[SessionOut] = []
    for sess, final_diagnosis in rows:
        data = SessionOut.model_validate(sess).model_dump()
        data["final_diagnosis"] = final_diagnosis
        items.append(SessionOut(**data))

    return SessionListOut(
        items=items,
        total=int(total),
        limit=limit,
        offset=offset,
    )


@router.get("/{session_id}", response_model=SessionDetailOut)
async def get_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SessionDetailOut:
    sess = await _get_own_session(session_id, db, user)
    transcripts = await _load_transcripts(db, sess.id)
    base = SessionOut.model_validate(sess).model_dump()
    return SessionDetailOut(
        **base,
        transcripts=[TranscriptOut.model_validate(t) for t in transcripts],
    )


@router.patch("/{session_id}", response_model=SessionOut)
async def patch_session(
    session_id: uuid.UUID,
    payload: SessionPatch,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SessionOut:
    sess = await _get_own_session(session_id, db, user)
    if sess.status not in (SessionStatus.draft, SessionStatus.recording):
        raise HTTPException(
            status_code=400,
            detail="Редактирование данных пациента доступно только в статусах draft/recording",
        )

    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        if field == "patient_full_name" and isinstance(value, str):
            value = value.strip()
        setattr(sess, field, value)

    await db.commit()
    await db.refresh(sess)
    return SessionOut.model_validate(sess)


@router.post("/{session_id}/consent", response_model=SessionOut)
async def set_consent(
    session_id: uuid.UUID,
    payload: ConsentRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SessionOut:
    sess = await _get_own_session(session_id, db, user)
    _ensure_not_finalized(sess)
    if not payload.granted:
        _audit(
            db,
            user_id=user.id,
            session_id=sess.id,
            action="consent_denied",
        )
        await db.commit()
        raise HTTPException(
            status_code=400,
            detail="Пациент отказался от согласия",
        )

    sess.consent_given_at = datetime.now(tz=timezone.utc)
    _audit(
        db,
        user_id=user.id,
        session_id=sess.id,
        action="consent_granted",
    )
    await db.commit()
    await db.refresh(sess)
    return SessionOut.model_validate(sess)


@router.post("/{session_id}/start-recording", response_model=SessionOut)
async def start_recording(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SessionOut:
    sess = await _get_own_session(session_id, db, user)
    if sess.consent_given_at is None:
        raise HTTPException(
            status_code=400,
            detail="Нельзя начать запись без согласия пациента",
        )
    if sess.status not in (SessionStatus.draft, SessionStatus.recording):
        raise HTTPException(
            status_code=400,
            detail="Сессия уже закрыта или обработана",
        )
    sess.status = SessionStatus.recording
    _audit(
        db,
        user_id=user.id,
        session_id=sess.id,
        action="recording_started",
    )
    await db.commit()
    await db.refresh(sess)
    return SessionOut.model_validate(sess)


@router.post("/{session_id}/stop-recording", response_model=SessionOut)
async def stop_recording(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SessionOut:
    sess = await _get_own_session(session_id, db, user)
    _ensure_not_finalized(sess)
    if sess.status != SessionStatus.recording:
        # Idempotent-ish: if it's already draft, still log and return.
        pass
    sess.status = SessionStatus.draft
    _audit(
        db,
        user_id=user.id,
        session_id=sess.id,
        action="recording_stopped",
    )
    await db.commit()
    await db.refresh(sess)
    return SessionOut.model_validate(sess)


@router.delete("/{session_id}/audio", response_model=SessionOut)
async def delete_audio(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SessionOut:
    sess = await _get_own_session(session_id, db, user)
    _ensure_not_finalized(sess)
    await db.execute(delete(Transcript).where(Transcript.session_id == sess.id))
    sess.status = SessionStatus.draft
    _audit(
        db,
        user_id=user.id,
        session_id=sess.id,
        action="audio_deleted",
    )
    await db.commit()
    await db.refresh(sess)
    return SessionOut.model_validate(sess)


# ---------------------------------------------------------------------------
# Transcripts
# ---------------------------------------------------------------------------


@router.post(
    "/{session_id}/transcripts",
    response_model=TranscriptOut | None,
    status_code=status.HTTP_201_CREATED,
    responses={
        204: {"description": "Chunk contained only silence / noise; no transcript stored"},
    },
)
async def upload_transcript_chunk(
    session_id: uuid.UUID,
    audio: UploadFile = File(...),
    speaker: Speaker = Form(...),
    started_at_ms: int = Form(...),
    ended_at_ms: int = Form(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    asr: ASRService = Depends(get_asr_service),
) -> TranscriptOut | Response:
    sess = await _get_own_session(session_id, db, user)
    if sess.status != SessionStatus.recording:
        raise HTTPException(
            status_code=400,
            detail="Загрузка аудио возможна только во время активной записи",
        )
    if started_at_ms < 0 or ended_at_ms < started_at_ms:
        raise HTTPException(status_code=400, detail="Неверные временные метки")

    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Пустой аудио-чанк")

    mime = audio.content_type or "audio/webm"
    try:
        result = await asr.transcribe_chunk(audio_bytes, mime=mime, language="ru")
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    # Explicit: we never persist audio bytes. Drop reference immediately.
    audio_bytes = b""

    # Whisper sometimes returns the empty string for pure silence/noise
    # (our ASR layer also filters out known hallucinations like "Субтитры
    # сделал …"). We don't want to create a ghost transcript row in that
    # case — just tell the client "nothing worth recording".
    if not result.text.strip():
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    transcript = Transcript(
        session_id=sess.id,
        speaker=speaker,
        text=result.text,
        started_at_ms=started_at_ms,
        ended_at_ms=ended_at_ms,
        confidence=result.confidence,
        edited_by_user=False,
    )
    db.add(transcript)
    await db.commit()
    await db.refresh(transcript)
    return TranscriptOut.model_validate(transcript)


@router.patch(
    "/{session_id}/transcripts/{transcript_id}",
    response_model=TranscriptOut,
)
async def patch_transcript(
    session_id: uuid.UUID,
    transcript_id: uuid.UUID,
    payload: TranscriptPatch,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TranscriptOut:
    sess = await _get_own_session(session_id, db, user)
    _ensure_not_closed(sess)
    result = await db.execute(
        select(Transcript).where(
            Transcript.id == transcript_id,
            Transcript.session_id == sess.id,
        )
    )
    transcript = result.scalar_one_or_none()
    if transcript is None:
        raise HTTPException(status_code=404, detail="Реплика не найдена")

    data = payload.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=400, detail="Нет данных для обновления")

    for field, value in data.items():
        setattr(transcript, field, value)
    transcript.edited_by_user = True

    await db.commit()
    await db.refresh(transcript)
    return TranscriptOut.model_validate(transcript)


@router.delete(
    "/{session_id}/transcripts/{transcript_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_transcript(
    session_id: uuid.UUID,
    transcript_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    sess = await _get_own_session(session_id, db, user)
    _ensure_not_closed(sess)
    result = await db.execute(
        select(Transcript).where(
            Transcript.id == transcript_id,
            Transcript.session_id == sess.id,
        )
    )
    transcript = result.scalar_one_or_none()
    if transcript is None:
        raise HTTPException(status_code=404, detail="Реплика не найдена")
    await db.delete(transcript)
    await db.commit()
    return None
