"""Integration tests for Step 4 — AI-powered analysis endpoints.

The real OpenAI client is never called: we override the FastAPI
dependency ``get_llm_service`` with a deterministic fake that returns
a canned :class:`LLMAnalysisResult`. All flows (analyze / re-analyze /
edit protocol / select diagnosis / custom diagnosis / red flags /
treatment plan CRUD + reorder / conflict detection) go through HTTP.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pytest_asyncio
from sqlalchemy import select

from app.main import app
from app.models.appointment_session import AppointmentSession
from app.models.audit_log import AuditLog
from app.models.diagnosis_suggestion import DiagnosisSuggestion
from app.models.enums import (
    AppointmentType,
    PatientSex,
    SessionStatus,
    Speaker,
)
from app.models.protocol import Protocol
from app.models.red_flag import RedFlag
from app.models.transcript import Transcript
from app.models.treatment_plan import TreatmentPlan, TreatmentPlanItem
from app.services.llm import (
    LLMAnalysisResult,
    LLMDiagnosisSuggestion,
    LLMProtocolPart,
    LLMRedFlag,
    LLMTreatmentItem,
    PatientContext,
    TranscriptTurn,
    get_llm_service,
)


# ---------------------------------------------------------------------------
# Fake LLM
# ---------------------------------------------------------------------------


@dataclass
class FakeLLM:
    result: LLMAnalysisResult
    calls: list[dict] = field(default_factory=list)

    async def analyze_dialogue(
        self, patient: PatientContext, transcript: list[TranscriptTurn]
    ) -> LLMAnalysisResult:
        self.calls.append(
            {"patient": patient, "transcript": [t.text for t in transcript]}
        )
        return self.result


def _default_result(
    *,
    allergies: str = "",
    medications: str = "",
    plan_medication_title: str = "Парацетамол 500 мг",
) -> LLMAnalysisResult:
    return LLMAnalysisResult(
        protocol=LLMProtocolPart(
            complaints="Головная боль в течение 3 дней",
            anamnesis="Без хронических заболеваний",
            examination="Без очаговой неврологической симптоматики",
            allergies=allergies,
            medications=medications,
        ),
        red_flags=[
            LLMRedFlag(
                label="Лихорадка выше 39",
                description="Выяснить характер лихорадки",
                severity="high",
            )
        ],
        diagnosis_suggestions=[
            LLMDiagnosisSuggestion(
                title="Мигрень без ауры",
                icd10_code="G43.0",
                probability=0.7,
                reasoning="Характер боли и длительность",
                supporting_symptoms=["пульсирующая боль", "светобоязнь"],
                contradicting_symptoms=["нет тошноты"],
            ),
            LLMDiagnosisSuggestion(
                title="Головная боль напряжения",
                icd10_code="G44.2",
                probability=0.25,
                reasoning="Двусторонний характер",
                supporting_symptoms=["стресс"],
                contradicting_symptoms=["есть пульсация"],
            ),
            LLMDiagnosisSuggestion(
                title="Синусит",
                icd10_code="J32",
                probability=0.05,
                reasoning="Маловероятно",
                supporting_symptoms=[],
                contradicting_symptoms=["нет заложенности"],
            ),
        ],
        treatment_plan=[
            LLMTreatmentItem(
                kind="medication",
                title=plan_medication_title,
                details="При головной боли",
                dosage="500 мг",
                duration="по требованию",
            ),
            LLMTreatmentItem(
                kind="investigation",
                title="Общий анализ крови",
                details="",
                dosage=None,
                duration=None,
            ),
        ],
    )


@pytest_asyncio.fixture
async def fake_llm():
    llm = FakeLLM(result=_default_result())
    app.dependency_overrides[get_llm_service] = lambda: llm
    try:
        yield llm
    finally:
        app.dependency_overrides.pop(get_llm_service, None)


# ---------------------------------------------------------------------------
# Helpers: seed a session ready for analysis
# ---------------------------------------------------------------------------


async def _seed_session_with_transcripts(
    db_session,
    doctor_id,
    *,
    status: SessionStatus = SessionStatus.draft,
) -> AppointmentSession:
    sess = AppointmentSession(
        doctor_id=doctor_id,
        patient_full_name="Иванов Иван",
        patient_age=35,
        patient_sex=PatientSex.male,
        appointment_type=AppointmentType.primary,
        status=status,
    )
    db_session.add(sess)
    await db_session.flush()
    db_session.add_all(
        [
            Transcript(
                session_id=sess.id,
                speaker=Speaker.doctor,
                text="Что вас беспокоит?",
                started_at_ms=0,
                ended_at_ms=2000,
                confidence=0.9,
                edited_by_user=False,
            ),
            Transcript(
                session_id=sess.id,
                speaker=Speaker.patient,
                text="Болит голова третий день, пульсирует, свет раздражает",
                started_at_ms=2000,
                ended_at_ms=7000,
                confidence=0.9,
                edited_by_user=False,
            ),
        ]
    )
    await db_session.commit()
    await db_session.refresh(sess)
    return sess


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_analyze_creates_all_entities(
    client, auth_headers, fake_llm, demo_doctor, db_session
):
    sess = await _seed_session_with_transcripts(db_session, demo_doctor.id)

    resp = await client.post(
        f"/api/v1/sessions/{sess.id}/analyze", headers=auth_headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["session"]["status"] == "analyzed"
    assert body["protocol"]["complaints"].startswith("Головная")
    assert len(body["diagnosis_suggestions"]) == 3
    # Sorted by probability desc.
    probs = [s["probability"] for s in body["diagnosis_suggestions"]]
    assert probs == sorted(probs, reverse=True)
    assert len(body["red_flags"]) == 1
    assert body["treatment_plan"] is not None
    assert len(body["treatment_plan"]["items"]) == 2

    # DB side-effects.
    assert (await db_session.execute(select(Protocol))).scalar_one() is not None
    suggestions = (
        await db_session.execute(select(DiagnosisSuggestion))
    ).scalars().all()
    assert len(suggestions) == 3
    red_flags = (await db_session.execute(select(RedFlag))).scalars().all()
    assert len(red_flags) == 1
    plans = (await db_session.execute(select(TreatmentPlan))).scalars().all()
    assert len(plans) == 1
    items = (
        await db_session.execute(select(TreatmentPlanItem))
    ).scalars().all()
    assert len(items) == 2

    actions = [
        r.action
        for r in (await db_session.execute(select(AuditLog))).scalars().all()
    ]
    assert "analysis_completed" in actions

    assert len(fake_llm.calls) == 1
    assert len(fake_llm.calls[0]["transcript"]) == 2


async def test_analyze_replaces_previous(
    client, auth_headers, fake_llm, demo_doctor, db_session
):
    sess = await _seed_session_with_transcripts(db_session, demo_doctor.id)
    await client.post(f"/api/v1/sessions/{sess.id}/analyze", headers=auth_headers)

    fake_llm.result = _default_result(allergies="пенициллин")
    # Trim the result for the second call — only one diagnosis / one red flag.
    fake_llm.result.diagnosis_suggestions = fake_llm.result.diagnosis_suggestions[:1]
    fake_llm.result.red_flags = []
    fake_llm.result.treatment_plan = fake_llm.result.treatment_plan[:1]

    resp = await client.post(
        f"/api/v1/sessions/{sess.id}/analyze", headers=auth_headers
    )
    assert resp.status_code == 200, resp.text

    suggestions = (
        await db_session.execute(select(DiagnosisSuggestion))
    ).scalars().all()
    assert len(suggestions) == 1
    red_flags = (await db_session.execute(select(RedFlag))).scalars().all()
    assert red_flags == []
    items = (
        await db_session.execute(select(TreatmentPlanItem))
    ).scalars().all()
    assert len(items) == 1


async def test_analyze_without_transcripts_400(
    client, auth_headers, fake_llm, demo_doctor, db_session
):
    sess = AppointmentSession(
        doctor_id=demo_doctor.id,
        patient_full_name="Петров",
        patient_age=40,
        patient_sex=PatientSex.male,
        appointment_type=AppointmentType.primary,
        status=SessionStatus.draft,
    )
    db_session.add(sess)
    await db_session.commit()
    await db_session.refresh(sess)

    resp = await client.post(
        f"/api/v1/sessions/{sess.id}/analyze", headers=auth_headers
    )
    assert resp.status_code == 400


async def test_analyze_wrong_status_409(
    client, auth_headers, fake_llm, demo_doctor, db_session
):
    sess = await _seed_session_with_transcripts(
        db_session, demo_doctor.id, status=SessionStatus.recording
    )
    resp = await client.post(
        f"/api/v1/sessions/{sess.id}/analyze", headers=auth_headers
    )
    assert resp.status_code == 409


async def test_get_analysis_draft_409(
    client, auth_headers, fake_llm, demo_doctor, db_session
):
    sess = await _seed_session_with_transcripts(db_session, demo_doctor.id)
    resp = await client.get(
        f"/api/v1/sessions/{sess.id}/analysis", headers=auth_headers
    )
    assert resp.status_code == 409


async def test_select_diagnosis_updates_protocol(
    client, auth_headers, fake_llm, demo_doctor, db_session
):
    sess = await _seed_session_with_transcripts(db_session, demo_doctor.id)
    resp = await client.post(
        f"/api/v1/sessions/{sess.id}/analyze", headers=auth_headers
    )
    suggestion = resp.json()["diagnosis_suggestions"][0]
    sid = suggestion["id"]

    resp = await client.post(
        f"/api/v1/sessions/{sess.id}/diagnosis-suggestions/{sid}/select",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["final_diagnosis"] == suggestion["title"]
    assert body["icd10_code"] == suggestion["icd10_code"]

    # Verify only one suggestion is marked selected in DB.
    rows = (
        await db_session.execute(select(DiagnosisSuggestion))
    ).scalars().all()
    selected = [r for r in rows if r.is_selected]
    assert len(selected) == 1
    assert str(selected[0].id) == sid


async def test_custom_diagnosis_clears_selection(
    client, auth_headers, fake_llm, demo_doctor, db_session
):
    sess = await _seed_session_with_transcripts(db_session, demo_doctor.id)
    analyze = await client.post(
        f"/api/v1/sessions/{sess.id}/analyze", headers=auth_headers
    )
    sid = analyze.json()["diagnosis_suggestions"][0]["id"]
    await client.post(
        f"/api/v1/sessions/{sess.id}/diagnosis-suggestions/{sid}/select",
        headers=auth_headers,
    )

    resp = await client.post(
        f"/api/v1/sessions/{sess.id}/protocol/custom-diagnosis",
        headers=auth_headers,
        json={"title": "Свой диагноз", "icd10_code": "Z99", "reason": "клинически"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["final_diagnosis"] == "Свой диагноз"
    assert body["icd10_code"] == "Z99"

    rows = (
        await db_session.execute(select(DiagnosisSuggestion))
    ).scalars().all()
    assert all(r.is_selected is False for r in rows)


async def test_red_flag_acknowledge_requires_note_on_reject(
    client, auth_headers, fake_llm, demo_doctor, db_session
):
    sess = await _seed_session_with_transcripts(db_session, demo_doctor.id)
    analyze = await client.post(
        f"/api/v1/sessions/{sess.id}/analyze", headers=auth_headers
    )
    rf_id = analyze.json()["red_flags"][0]["id"]

    # reject without note → 422
    resp = await client.post(
        f"/api/v1/sessions/{sess.id}/red-flags/{rf_id}/acknowledge",
        headers=auth_headers,
        json={"accepted": False},
    )
    assert resp.status_code == 422

    # accept → 200
    resp = await client.post(
        f"/api/v1/sessions/{sess.id}/red-flags/{rf_id}/acknowledge",
        headers=auth_headers,
        json={"accepted": True},
    )
    assert resp.status_code == 200
    assert resp.json()["acknowledged_at"] is not None

    actions = [
        r.action
        for r in (await db_session.execute(select(AuditLog))).scalars().all()
    ]
    assert "red_flag_acknowledged" in actions


async def test_plan_item_crud_and_reorder(
    client, auth_headers, fake_llm, demo_doctor, db_session
):
    sess = await _seed_session_with_transcripts(db_session, demo_doctor.id)
    analyze = await client.post(
        f"/api/v1/sessions/{sess.id}/analyze", headers=auth_headers
    )
    initial_items = analyze.json()["treatment_plan"]["items"]
    assert len(initial_items) == 2
    item_ids = [i["id"] for i in initial_items]

    # Create a new item, no order_index → goes to the end.
    resp = await client.post(
        f"/api/v1/sessions/{sess.id}/treatment-plan/items",
        headers=auth_headers,
        json={
            "kind": "non_drug",
            "title": "Покой 2 дня",
            "details": "Ограничить экран",
        },
    )
    assert resp.status_code == 201, resp.text
    new_id = resp.json()["id"]
    assert resp.json()["order_index"] == 2

    # Patch it — set is_confirmed.
    resp = await client.patch(
        f"/api/v1/sessions/{sess.id}/treatment-plan/items/{new_id}",
        headers=auth_headers,
        json={"is_confirmed": True, "dosage": "—"},
    )
    assert resp.status_code == 200
    assert resp.json()["is_confirmed"] is True

    # Reorder: put the brand-new item first.
    resp = await client.post(
        f"/api/v1/sessions/{sess.id}/treatment-plan/reorder",
        headers=auth_headers,
        json={"ordered_ids": [new_id, item_ids[0], item_ids[1]]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert [i["id"] for i in body["items"]][0] == new_id

    # Delete the original first item.
    resp = await client.delete(
        f"/api/v1/sessions/{sess.id}/treatment-plan/items/{item_ids[0]}",
        headers=auth_headers,
    )
    assert resp.status_code == 204

    # Re-fetch analysis.
    resp = await client.get(
        f"/api/v1/sessions/{sess.id}/analysis", headers=auth_headers
    )
    ids = [i["id"] for i in resp.json()["treatment_plan"]["items"]]
    assert item_ids[0] not in ids

    actions = {
        r.action
        for r in (await db_session.execute(select(AuditLog))).scalars().all()
    }
    assert {
        "plan_item_added",
        "plan_item_updated",
        "plan_items_reordered",
        "plan_item_deleted",
    } <= actions


async def test_protocol_patch_forbidden_on_confirmed(
    client, auth_headers, fake_llm, demo_doctor, db_session
):
    sess = await _seed_session_with_transcripts(db_session, demo_doctor.id)
    await client.post(f"/api/v1/sessions/{sess.id}/analyze", headers=auth_headers)

    # Flip session to confirmed (Step-5 status) directly in DB to test gate.
    sess = (
        await db_session.execute(
            select(AppointmentSession).where(AppointmentSession.id == sess.id)
        )
    ).scalar_one()
    sess.status = SessionStatus.confirmed
    await db_session.commit()

    resp = await client.patch(
        f"/api/v1/sessions/{sess.id}/protocol",
        headers=auth_headers,
        json={"complaints": "новое"},
    )
    assert resp.status_code == 409


async def test_conflict_flag_on_allergy_match(
    client, auth_headers, fake_llm, demo_doctor, db_session
):
    fake_llm.result = _default_result(
        allergies="Парацетамол; арахис",
        medications="Ибупрофен 200 мг",
        plan_medication_title="Парацетамол 500 мг",
    )
    sess = await _seed_session_with_transcripts(db_session, demo_doctor.id)
    resp = await client.post(
        f"/api/v1/sessions/{sess.id}/analyze", headers=auth_headers
    )
    assert resp.status_code == 200
    items = resp.json()["treatment_plan"]["items"]
    med_item = next(i for i in items if i["kind"] == "medication")
    inv_item = next(i for i in items if i["kind"] == "investigation")
    assert med_item["conflict"] is True
    # Non-medication items are never flagged.
    assert inv_item["conflict"] is False


async def test_protocol_patch_happy_path(
    client, auth_headers, fake_llm, demo_doctor, db_session
):
    sess = await _seed_session_with_transcripts(db_session, demo_doctor.id)
    await client.post(f"/api/v1/sessions/{sess.id}/analyze", headers=auth_headers)
    resp = await client.patch(
        f"/api/v1/sessions/{sess.id}/protocol",
        headers=auth_headers,
        json={"complaints": "Уточнено врачом", "allergies": "нет"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["complaints"] == "Уточнено врачом"
    assert body["allergies"] == "нет"

    actions = [
        r.action
        for r in (await db_session.execute(select(AuditLog))).scalars().all()
    ]
    assert "protocol_updated" in actions
