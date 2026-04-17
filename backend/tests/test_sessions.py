"""Integration tests for Step 3 — session lifecycle & transcripts.

Covers:
* POST /sessions — create
* GET /sessions/{id} — 404 for someone else's session
* POST /sessions/{id}/consent — granted + denied
* POST /sessions/{id}/start-recording — requires consent
* POST /sessions/{id}/transcripts — uploads chunk, saves ASR result
* PATCH / DELETE transcripts
* DELETE /sessions/{id}/audio

ASR is substituted via ``app.dependency_overrides`` with a fake that
returns deterministic text and confidence.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pytest_asyncio
from sqlalchemy import select

from app.core.security import hash_password
from app.main import app
from app.models.audit_log import AuditLog
from app.models.transcript import Transcript
from app.models.user import User
from app.services.asr import ASRResult, get_asr_service


@dataclass
class FakeASR:
    calls: list[dict] = field(default_factory=list)
    text: str = "Здравствуйте, на что жалуетесь?"
    confidence: float | None = 0.87

    async def transcribe_chunk(
        self, audio_bytes: bytes, mime: str, language: str = "ru"
    ) -> ASRResult:
        self.calls.append(
            {"size": len(audio_bytes), "mime": mime, "language": language}
        )
        return ASRResult(text=self.text, confidence=self.confidence)


@pytest_asyncio.fixture
async def fake_asr():
    asr = FakeASR()
    app.dependency_overrides[get_asr_service] = lambda: asr
    try:
        yield asr
    finally:
        app.dependency_overrides.pop(get_asr_service, None)


@pytest_asyncio.fixture
async def other_doctor(db_session) -> User:
    user = User(
        email="other@clinic.local",
        password_hash=hash_password("otherpass1"),
        full_name="Другой Врач",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


SESSION_PAYLOAD = {
    "patient_full_name": "Иванов Иван Иванович",
    "patient_age": 35,
    "patient_sex": "male",
    "appointment_type": "primary",
}


async def _create_session(client, headers, payload=None) -> dict:
    resp = await client.post(
        "/api/v1/sessions", headers=headers, json=payload or SESSION_PAYLOAD
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_create_session_and_list(client, auth_headers):
    created = await _create_session(client, auth_headers)
    assert created["status"] == "draft"
    assert created["patient_full_name"] == SESSION_PAYLOAD["patient_full_name"]
    assert created["consent_given_at"] is None

    resp = await client.get("/api/v1/sessions", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == created["id"]


async def test_foreign_session_returns_404(client, auth_headers, other_doctor, db_session):
    from app.models.appointment_session import AppointmentSession
    from app.models.enums import AppointmentType, PatientSex, SessionStatus

    foreign = AppointmentSession(
        doctor_id=other_doctor.id,
        patient_full_name="Чужой пациент",
        patient_age=50,
        patient_sex=PatientSex.female,
        appointment_type=AppointmentType.primary,
        status=SessionStatus.draft,
    )
    db_session.add(foreign)
    await db_session.commit()
    await db_session.refresh(foreign)

    resp = await client.get(f"/api/v1/sessions/{foreign.id}", headers=auth_headers)
    assert resp.status_code == 404


async def test_consent_granted_and_denied(client, auth_headers, db_session):
    created = await _create_session(client, auth_headers)
    sid = created["id"]

    resp = await client.post(
        f"/api/v1/sessions/{sid}/consent",
        headers=auth_headers,
        json={"granted": True},
    )
    assert resp.status_code == 200
    assert resp.json()["consent_given_at"] is not None

    # second session: test denial path
    created2 = await _create_session(client, auth_headers)
    resp = await client.post(
        f"/api/v1/sessions/{created2['id']}/consent",
        headers=auth_headers,
        json={"granted": False},
    )
    assert resp.status_code == 400

    rows = (await db_session.execute(select(AuditLog))).scalars().all()
    actions = {r.action for r in rows}
    assert "consent_granted" in actions
    assert "consent_denied" in actions


async def test_start_recording_requires_consent(client, auth_headers):
    created = await _create_session(client, auth_headers)
    sid = created["id"]

    resp = await client.post(
        f"/api/v1/sessions/{sid}/start-recording", headers=auth_headers
    )
    assert resp.status_code == 400

    await client.post(
        f"/api/v1/sessions/{sid}/consent",
        headers=auth_headers,
        json={"granted": True},
    )
    resp = await client.post(
        f"/api/v1/sessions/{sid}/start-recording", headers=auth_headers
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "recording"


async def _prepare_recording(client, auth_headers) -> str:
    created = await _create_session(client, auth_headers)
    sid = created["id"]
    await client.post(
        f"/api/v1/sessions/{sid}/consent",
        headers=auth_headers,
        json={"granted": True},
    )
    await client.post(
        f"/api/v1/sessions/{sid}/start-recording", headers=auth_headers
    )
    return sid


async def test_upload_transcript_chunk(client, auth_headers, fake_asr, db_session):
    sid = await _prepare_recording(client, auth_headers)

    files = {"audio": ("chunk.webm", b"\x00\x01binary-chunk\x02", "audio/webm")}
    data = {"speaker": "doctor", "started_at_ms": "0", "ended_at_ms": "5000"}

    resp = await client.post(
        f"/api/v1/sessions/{sid}/transcripts",
        headers=auth_headers,
        files=files,
        data=data,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["text"] == fake_asr.text
    assert body["speaker"] == "doctor"
    assert body["started_at_ms"] == 0
    assert body["ended_at_ms"] == 5000
    assert body["edited_by_user"] is False
    assert body["confidence"] == fake_asr.confidence

    # Actually saved in DB
    rows = (await db_session.execute(select(Transcript))).scalars().all()
    assert len(rows) == 1
    assert rows[0].text == fake_asr.text

    # ASR was called with audio bytes
    assert len(fake_asr.calls) == 1
    assert fake_asr.calls[0]["size"] > 0


async def test_upload_without_recording_status_rejected(client, auth_headers, fake_asr):
    created = await _create_session(client, auth_headers)
    sid = created["id"]
    # no consent, no start-recording
    files = {"audio": ("chunk.webm", b"abc", "audio/webm")}
    data = {"speaker": "patient", "started_at_ms": "0", "ended_at_ms": "100"}
    resp = await client.post(
        f"/api/v1/sessions/{sid}/transcripts",
        headers=auth_headers,
        files=files,
        data=data,
    )
    assert resp.status_code == 400


async def test_patch_and_delete_transcript(client, auth_headers, fake_asr, db_session):
    sid = await _prepare_recording(client, auth_headers)
    resp = await client.post(
        f"/api/v1/sessions/{sid}/transcripts",
        headers=auth_headers,
        files={"audio": ("chunk.webm", b"bytes", "audio/webm")},
        data={"speaker": "patient", "started_at_ms": "0", "ended_at_ms": "5000"},
    )
    tid = resp.json()["id"]

    resp = await client.patch(
        f"/api/v1/sessions/{sid}/transcripts/{tid}",
        headers=auth_headers,
        json={"text": "Исправленный текст", "speaker": "doctor"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["text"] == "Исправленный текст"
    assert body["speaker"] == "doctor"
    assert body["edited_by_user"] is True

    resp = await client.delete(
        f"/api/v1/sessions/{sid}/transcripts/{tid}", headers=auth_headers
    )
    assert resp.status_code == 204

    rows = (await db_session.execute(select(Transcript))).scalars().all()
    assert rows == []


async def test_stop_and_delete_audio(client, auth_headers, fake_asr, db_session):
    sid = await _prepare_recording(client, auth_headers)
    await client.post(
        f"/api/v1/sessions/{sid}/transcripts",
        headers=auth_headers,
        files={"audio": ("chunk.webm", b"bytes", "audio/webm")},
        data={"speaker": "patient", "started_at_ms": "0", "ended_at_ms": "5000"},
    )

    resp = await client.post(
        f"/api/v1/sessions/{sid}/stop-recording", headers=auth_headers
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "draft"

    # transcript still exists after stop
    rows = (await db_session.execute(select(Transcript))).scalars().all()
    assert len(rows) == 1

    # delete audio nukes all transcripts
    resp = await client.delete(
        f"/api/v1/sessions/{sid}/audio", headers=auth_headers
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "draft"

    rows = (await db_session.execute(select(Transcript))).scalars().all()
    assert rows == []

    actions = [
        r.action
        for r in (await db_session.execute(select(AuditLog))).scalars().all()
    ]
    assert "recording_stopped" in actions
    assert "audio_deleted" in actions


async def test_session_detail_includes_transcripts(
    client, auth_headers, fake_asr, db_session
):
    sid = await _prepare_recording(client, auth_headers)
    await client.post(
        f"/api/v1/sessions/{sid}/transcripts",
        headers=auth_headers,
        files={"audio": ("chunk.webm", b"abc", "audio/webm")},
        data={"speaker": "doctor", "started_at_ms": "0", "ended_at_ms": "5000"},
    )
    resp = await client.get(f"/api/v1/sessions/{sid}", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "recording"
    assert len(body["transcripts"]) == 1
    assert body["transcripts"][0]["speaker"] == "doctor"


async def test_patch_session_patient_data(client, auth_headers):
    created = await _create_session(client, auth_headers)
    sid = created["id"]
    resp = await client.patch(
        f"/api/v1/sessions/{sid}",
        headers=auth_headers,
        json={"patient_full_name": "Петров Пётр Петрович", "patient_age": 40},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["patient_full_name"] == "Петров Пётр Петрович"
    assert body["patient_age"] == 40
