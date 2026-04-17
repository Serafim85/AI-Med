"""Integration tests for Step 5 — protocol summary, confirmation, PDF, close.

The real WeasyPrint renderer is replaced with a lightweight fake so the
suite stays green on CI workers without libpango/libcairo installed.
The fake still returns a valid ``%PDF`` signature so the HTTP contract
(content type + magic bytes) is exercised end-to-end.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest_asyncio
from sqlalchemy import select

from app.main import app
from app.models.appointment_session import AppointmentSession
from app.models.audit_log import AuditLog
from app.models.diagnosis_suggestion import DiagnosisSuggestion
from app.models.enums import (
    AppointmentType,
    PatientSex,
    RedFlagSeverity,
    SessionStatus,
    TreatmentItemKind,
)
from app.models.protocol import Protocol
from app.models.red_flag import RedFlag
from app.models.transcript import Transcript
from app.models.treatment_plan import TreatmentPlan, TreatmentPlanItem
from app.services.pdf import (
    PdfService,
    ProtocolPdfData,
    get_pdf_service,
)


# ---------------------------------------------------------------------------
# Fake PDF service (keeps tests independent of native libs)
# ---------------------------------------------------------------------------


class FakePdfService:
    def __init__(self) -> None:
        self.calls: list[ProtocolPdfData] = []

    def render_protocol_pdf(self, data: ProtocolPdfData) -> bytes:
        self.calls.append(data)
        # Minimal, valid enough for sig checks; not a full spec doc.
        return (
            b"%PDF-1.4\n"
            b"%\xe2\xe3\xcf\xd3\n"
            b"1 0 obj<<>>endobj\n"
            b"trailer<<>>\n"
            b"%%EOF\n"
        )


@pytest_asyncio.fixture
async def fake_pdf():
    svc: PdfService = FakePdfService()
    app.dependency_overrides[get_pdf_service] = lambda: svc
    try:
        yield svc
    finally:
        app.dependency_overrides.pop(get_pdf_service, None)


# ---------------------------------------------------------------------------
# Seeding helpers
# ---------------------------------------------------------------------------


async def _make_session(
    db_session,
    doctor_id,
    *,
    status: SessionStatus = SessionStatus.analyzed,
    patient_full_name: str = "Иванов Иван Иванович",
) -> AppointmentSession:
    sess = AppointmentSession(
        doctor_id=doctor_id,
        patient_full_name=patient_full_name,
        patient_age=35,
        patient_sex=PatientSex.male,
        appointment_type=AppointmentType.primary,
        status=status,
        consent_given_at=datetime.now(tz=timezone.utc),
    )
    db_session.add(sess)
    await db_session.flush()
    return sess


async def _seed_analyzable(
    db_session,
    doctor_id,
    *,
    with_diagnosis: bool = True,
    red_flag_acked: bool = True,
    add_red_flag: bool = True,
    plan_items_confirmed: bool = True,
    add_plan_item: bool = True,
) -> AppointmentSession:
    """Seed a session in ``analyzed`` state that can be confirmed.

    Flip the flags to simulate precondition violations used by the tests
    below (missing diagnosis / unacked flag / unconfirmed plan item).
    """
    sess = await _make_session(db_session, doctor_id)

    db_session.add(
        Transcript(
            session_id=sess.id,
            speaker="doctor",
            text="Что вас беспокоит?",
            started_at_ms=0,
            ended_at_ms=2000,
            confidence=0.9,
            edited_by_user=False,
        )
    )

    protocol = Protocol(
        session_id=sess.id,
        complaints="Головная боль",
        anamnesis="Без хронических заболеваний",
        examination="Без очаговой неврологической симптоматики",
        allergies="нет",
        medications="нет",
        final_diagnosis="Мигрень без ауры" if with_diagnosis else None,
        icd10_code="G43.0" if with_diagnosis else None,
    )
    db_session.add(protocol)

    db_session.add(
        DiagnosisSuggestion(
            session_id=sess.id,
            title="Мигрень без ауры",
            icd10_code="G43.0",
            probability=0.8,
            reasoning="",
            supporting_symptoms="[]",
            contradicting_symptoms="[]",
            is_selected=with_diagnosis,
        )
    )

    if add_red_flag:
        rf = RedFlag(
            session_id=sess.id,
            label="Лихорадка >39",
            description="",
            severity=RedFlagSeverity.high,
            acknowledged_at=datetime.now(tz=timezone.utc)
            if red_flag_acked
            else None,
            doctor_note=None,
        )
        db_session.add(rf)

    plan = TreatmentPlan(session_id=sess.id)
    db_session.add(plan)
    await db_session.flush()
    if add_plan_item:
        db_session.add(
            TreatmentPlanItem(
                plan_id=plan.id,
                kind=TreatmentItemKind.medication,
                title="Парацетамол 500 мг",
                details=None,
                dosage="500 мг",
                duration="по требованию",
                order_index=0,
                is_confirmed=plan_items_confirmed,
            )
        )

    await db_session.commit()
    await db_session.refresh(sess)
    return sess


# ---------------------------------------------------------------------------
# /summary
# ---------------------------------------------------------------------------


async def test_summary_for_analyzed(
    client, auth_headers, fake_pdf, demo_doctor, db_session
):
    sess = await _seed_analyzable(db_session, demo_doctor.id)
    resp = await client.get(
        f"/api/v1/sessions/{sess.id}/summary", headers=auth_headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["session"]["id"] == str(sess.id)
    assert body["doctor"]["full_name"]
    assert body["protocol"]["final_diagnosis"] == "Мигрень без ауры"
    assert body["selected_diagnosis"]["icd10_code"] == "G43.0"
    assert len(body["red_flags"]) == 1
    assert len(body["treatment_plan_items"]) == 1


async def test_summary_draft_409(
    client, auth_headers, fake_pdf, demo_doctor, db_session
):
    sess = await _make_session(
        db_session, demo_doctor.id, status=SessionStatus.draft
    )
    await db_session.commit()
    resp = await client.get(
        f"/api/v1/sessions/{sess.id}/summary", headers=auth_headers
    )
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# /confirm
# ---------------------------------------------------------------------------


async def test_confirm_happy_path(
    client, auth_headers, fake_pdf, demo_doctor, db_session
):
    sess = await _seed_analyzable(db_session, demo_doctor.id)
    resp = await client.post(
        f"/api/v1/sessions/{sess.id}/confirm", headers=auth_headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["session"]["status"] == "confirmed"
    assert body["protocol"]["confirmed_at"] is not None

    current_status = (
        await db_session.execute(
            select(AppointmentSession.status).where(
                AppointmentSession.id == sess.id
            )
        )
    ).scalar_one()
    assert current_status == SessionStatus.confirmed

    actions = [
        r.action
        for r in (await db_session.execute(select(AuditLog))).scalars().all()
    ]
    assert "protocol_confirmed" in actions


async def test_confirm_requires_final_diagnosis(
    client, auth_headers, fake_pdf, demo_doctor, db_session
):
    sess = await _seed_analyzable(
        db_session, demo_doctor.id, with_diagnosis=False
    )
    resp = await client.post(
        f"/api/v1/sessions/{sess.id}/confirm", headers=auth_headers
    )
    assert resp.status_code == 422
    assert "диагноз" in resp.json()["detail"].lower()


async def test_confirm_requires_acknowledged_red_flags(
    client, auth_headers, fake_pdf, demo_doctor, db_session
):
    sess = await _seed_analyzable(
        db_session, demo_doctor.id, red_flag_acked=False
    )
    resp = await client.post(
        f"/api/v1/sessions/{sess.id}/confirm", headers=auth_headers
    )
    assert resp.status_code == 422
    assert "флаг" in resp.json()["detail"].lower()


async def test_confirm_requires_confirmed_plan_items(
    client, auth_headers, fake_pdf, demo_doctor, db_session
):
    sess = await _seed_analyzable(
        db_session, demo_doctor.id, plan_items_confirmed=False
    )
    resp = await client.post(
        f"/api/v1/sessions/{sess.id}/confirm", headers=auth_headers
    )
    assert resp.status_code == 422
    assert "план" in resp.json()["detail"].lower()


async def test_confirm_allows_empty_plan(
    client, auth_headers, fake_pdf, demo_doctor, db_session
):
    sess = await _seed_analyzable(
        db_session, demo_doctor.id, add_plan_item=False
    )
    resp = await client.post(
        f"/api/v1/sessions/{sess.id}/confirm", headers=auth_headers
    )
    assert resp.status_code == 200


async def test_confirm_wrong_status_409(
    client, auth_headers, fake_pdf, demo_doctor, db_session
):
    sess = await _make_session(
        db_session, demo_doctor.id, status=SessionStatus.draft
    )
    await db_session.commit()
    resp = await client.post(
        f"/api/v1/sessions/{sess.id}/confirm", headers=auth_headers
    )
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# /pdf
# ---------------------------------------------------------------------------


async def test_pdf_content_type_and_signature(
    client, auth_headers, fake_pdf, demo_doctor, db_session
):
    sess = await _seed_analyzable(db_session, demo_doctor.id)
    confirm = await client.post(
        f"/api/v1/sessions/{sess.id}/confirm", headers=auth_headers
    )
    assert confirm.status_code == 200

    resp = await client.get(
        f"/api/v1/sessions/{sess.id}/pdf", headers=auth_headers
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/pdf")
    assert resp.headers["content-disposition"].startswith("attachment;")
    assert resp.content.startswith(b"%PDF")

    actions = [
        r.action
        for r in (await db_session.execute(select(AuditLog))).scalars().all()
    ]
    assert "pdf_generated" in actions


async def test_pdf_wrong_status_409(
    client, auth_headers, fake_pdf, demo_doctor, db_session
):
    sess = await _seed_analyzable(db_session, demo_doctor.id)
    # session is still in ``analyzed`` — /pdf must be 409.
    resp = await client.get(
        f"/api/v1/sessions/{sess.id}/pdf", headers=auth_headers
    )
    assert resp.status_code == 409

    # ``draft`` → 409 too.
    draft = await _make_session(
        db_session, demo_doctor.id, status=SessionStatus.draft
    )
    await db_session.commit()
    resp = await client.get(
        f"/api/v1/sessions/{draft.id}/pdf", headers=auth_headers
    )
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# /close
# ---------------------------------------------------------------------------


async def test_close_happy_path(
    client, auth_headers, fake_pdf, demo_doctor, db_session
):
    sess = await _seed_analyzable(db_session, demo_doctor.id)
    await client.post(
        f"/api/v1/sessions/{sess.id}/confirm", headers=auth_headers
    )
    resp = await client.post(
        f"/api/v1/sessions/{sess.id}/close", headers=auth_headers
    )
    assert resp.status_code == 200
    assert resp.json()["session"]["status"] == "closed"

    actions = [
        r.action
        for r in (await db_session.execute(select(AuditLog))).scalars().all()
    ]
    assert "session_closed" in actions


async def test_close_wrong_status_409(
    client, auth_headers, fake_pdf, demo_doctor, db_session
):
    sess = await _seed_analyzable(db_session, demo_doctor.id)
    # still analyzed → 409
    resp = await client.post(
        f"/api/v1/sessions/{sess.id}/close", headers=auth_headers
    )
    assert resp.status_code == 409


async def test_closed_session_blocks_modifications(
    client, auth_headers, fake_pdf, demo_doctor, db_session
):
    sess = await _seed_analyzable(db_session, demo_doctor.id)
    transcript_id = (
        await db_session.execute(
            select(Transcript.id).where(Transcript.session_id == sess.id)
        )
    ).scalar_one()

    await client.post(
        f"/api/v1/sessions/{sess.id}/confirm", headers=auth_headers
    )
    await client.post(
        f"/api/v1/sessions/{sess.id}/close", headers=auth_headers
    )

    # PATCH protocol → 409
    r = await client.patch(
        f"/api/v1/sessions/{sess.id}/protocol",
        headers=auth_headers,
        json={"complaints": "changed"},
    )
    assert r.status_code == 409

    # Add plan item → 409
    r = await client.post(
        f"/api/v1/sessions/{sess.id}/treatment-plan/items",
        headers=auth_headers,
        json={"kind": "non_drug", "title": "Покой"},
    )
    assert r.status_code == 409

    # PATCH transcript → 409
    r = await client.patch(
        f"/api/v1/sessions/{sess.id}/transcripts/{transcript_id}",
        headers=auth_headers,
        json={"text": "new"},
    )
    assert r.status_code == 409

    # But /pdf still works
    r = await client.get(
        f"/api/v1/sessions/{sess.id}/pdf", headers=auth_headers
    )
    assert r.status_code == 200
    assert r.content.startswith(b"%PDF")

    # And /summary
    r = await client.get(
        f"/api/v1/sessions/{sess.id}/summary", headers=auth_headers
    )
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# List filters
# ---------------------------------------------------------------------------


async def test_sessions_filter_by_status_and_query(
    client, auth_headers, fake_pdf, demo_doctor, db_session
):
    # Seed a draft session (default).
    draft = await _make_session(
        db_session,
        demo_doctor.id,
        status=SessionStatus.draft,
        patient_full_name="Смирнов Сергей",
    )
    # Seed an analyzable-session that we confirm.
    confirmed_sess = await _seed_analyzable(db_session, demo_doctor.id)

    resp = await client.post(
        f"/api/v1/sessions/{confirmed_sess.id}/confirm", headers=auth_headers
    )
    assert resp.status_code == 200, resp.text

    await db_session.commit()

    # status=confirmed → only the confirmed one
    resp = await client.get(
        "/api/v1/sessions?status=confirmed", headers=auth_headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == str(confirmed_sess.id)
    assert body["items"][0]["final_diagnosis"] == "Мигрень без ауры"

    # status=draft → only the draft one
    resp = await client.get(
        "/api/v1/sessions?status=draft", headers=auth_headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == str(draft.id)

    # query filter (substring match — ILIKE on Postgres, LOWER on SQLite).
    # NB: SQLite's LOWER is ASCII-only so we pass a case-matching Cyrillic
    # fragment here. In production against Postgres, ILIKE handles the full
    # case-insensitive behaviour.
    resp = await client.get(
        "/api/v1/sessions?query=Смирн", headers=auth_headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == str(draft.id)

    # combo: status + query, mismatch → empty
    resp = await client.get(
        "/api/v1/sessions?status=confirmed&query=Смирн", headers=auth_headers
    )
    assert resp.status_code == 200
    assert resp.json()["total"] == 0

    # all → both
    resp = await client.get("/api/v1/sessions?status=all", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["total"] == 2
