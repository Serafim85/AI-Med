"""LLM analysis service (Step 4).

Takes the transcript of an appointment plus short patient context and
produces a structured analysis: SOAP-ish protocol, red flags, top-3
diagnosis suggestions (with ICD-10, probability, reasoning, supporting
and contradicting symptoms), and an initial treatment plan.

The public entry point is the :class:`LLMService` protocol. Production
uses :class:`OpenAIStructuredLLM`, but tests override the FastAPI
dependency ``get_llm_service`` with a deterministic fake (see
``tests/test_analysis.py``).

We enforce the schema twice:

* by asking OpenAI for ``response_format={"type": "json_schema", ...}``
  (Structured Outputs — the model cannot deviate from the schema);
* by validating / clamping locally (probabilities, list length,
  descending order) because even with Structured Outputs we want a
  strict guarantee before persisting to Postgres.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, runtime_checkable

from app.core.config import get_settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# DTOs
# ---------------------------------------------------------------------------


Severity = Literal["low", "medium", "high"]
TreatmentKind = Literal["medication", "investigation", "non_drug", "follow_up"]


@dataclass(slots=True)
class PatientContext:
    age: int
    sex: str  # "male" | "female" | "other"
    appointment_type: str  # "primary" | "follow_up"


@dataclass(slots=True)
class TranscriptTurn:
    speaker: str  # "doctor" | "patient" | "unknown"
    text: str


@dataclass(slots=True)
class LLMProtocolPart:
    complaints: str = ""
    anamnesis: str = ""
    examination: str = ""
    allergies: str = ""
    medications: str = ""


@dataclass(slots=True)
class LLMRedFlag:
    label: str
    description: str
    severity: Severity


@dataclass(slots=True)
class LLMDiagnosisSuggestion:
    title: str
    icd10_code: str | None
    probability: float
    reasoning: str
    supporting_symptoms: list[str] = field(default_factory=list)
    contradicting_symptoms: list[str] = field(default_factory=list)


@dataclass(slots=True)
class LLMTreatmentItem:
    kind: TreatmentKind
    title: str
    details: str = ""
    dosage: str | None = None
    duration: str | None = None


@dataclass(slots=True)
class LLMAnalysisResult:
    protocol: LLMProtocolPart
    red_flags: list[LLMRedFlag] = field(default_factory=list)
    diagnosis_suggestions: list[LLMDiagnosisSuggestion] = field(default_factory=list)
    treatment_plan: list[LLMTreatmentItem] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class LLMService(Protocol):
    async def analyze_dialogue(
        self,
        patient: PatientContext,
        transcript: list[TranscriptTurn],
    ) -> LLMAnalysisResult: ...


# ---------------------------------------------------------------------------
# JSON schema for Structured Outputs
# ---------------------------------------------------------------------------


_RESPONSE_JSON_SCHEMA: dict[str, Any] = {
    "name": "AppointmentAnalysis",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "protocol",
            "red_flags",
            "diagnosis_suggestions",
            "treatment_plan",
        ],
        "properties": {
            "protocol": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "complaints",
                    "anamnesis",
                    "examination",
                    "allergies",
                    "medications",
                ],
                "properties": {
                    "complaints": {"type": "string"},
                    "anamnesis": {"type": "string"},
                    "examination": {"type": "string"},
                    "allergies": {"type": "string"},
                    "medications": {"type": "string"},
                },
            },
            "red_flags": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["label", "description", "severity"],
                    "properties": {
                        "label": {"type": "string"},
                        "description": {"type": "string"},
                        "severity": {
                            "type": "string",
                            "enum": ["low", "medium", "high"],
                        },
                    },
                },
            },
            "diagnosis_suggestions": {
                "type": "array",
                "maxItems": 3,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "title",
                        "icd10_code",
                        "probability",
                        "reasoning",
                        "supporting_symptoms",
                        "contradicting_symptoms",
                    ],
                    "properties": {
                        "title": {"type": "string"},
                        "icd10_code": {"type": ["string", "null"]},
                        "probability": {
                            "type": "number",
                            "minimum": 0,
                            "maximum": 1,
                        },
                        "reasoning": {"type": "string"},
                        "supporting_symptoms": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "contradicting_symptoms": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                },
            },
            "treatment_plan": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["kind", "title", "details", "dosage", "duration"],
                    "properties": {
                        "kind": {
                            "type": "string",
                            "enum": [
                                "medication",
                                "investigation",
                                "non_drug",
                                "follow_up",
                            ],
                        },
                        "title": {"type": "string"},
                        "details": {"type": "string"},
                        "dosage": {"type": ["string", "null"]},
                        "duration": {"type": ["string", "null"]},
                    },
                },
            },
        },
    },
}


SYSTEM_PROMPT = (
    "Ты — ИИ-ассистент врача. Ты помогаешь врачу структурировать информацию "
    "с амбулаторного приёма и получать черновик протокола.\n"
    "ВАЖНО: твои предложения носят исключительно справочный характер. "
    "Финальная ответственность за диагноз и назначения — на враче. "
    "Никогда не выдумывай жалобы, анамнез, препараты или обследования, "
    "которых нет в диалоге. Если данных мало или они противоречивы — честно "
    "пиши об этом в соответствующем поле (например, в `complaints` "
    "укажи «Недостаточно данных для анализа»).\n"
    "Отвечай СТРОГО в соответствии с JSON-схемой. Никакого текста вне "
    "JSON. Все поля — на русском языке. Если расшифровка содержит меньше "
    "30 слов, то верни пустые `diagnosis_suggestions`, `treatment_plan`, "
    "`red_flags`, и в `complaints` укажи «Недостаточно данных для анализа».\n"
    "Для `diagnosis_suggestions` возвращай не более 3 вариантов, "
    "отсортированных по убыванию probability (вероятности в [0, 1]). "
    "`icd10_code` — строка кода МКБ-10 или null, если уверенности нет.\n"
    "Для `treatment_plan` используй kind ∈ {medication, investigation, "
    "non_drug, follow_up}. В `dosage` и `duration` допускается null, "
    "если не применимо."
)


# ---------------------------------------------------------------------------
# Parsing & validation helpers
# ---------------------------------------------------------------------------


def _as_str(value: Any) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError(f"expected string, got {type(value).__name__}")
    return value


def _as_opt_str(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"expected string or null, got {type(value).__name__}")
    return value or None


def _as_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("expected list of strings")
    out: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError("expected list of strings")
        out.append(item)
    return out


def parse_llm_response(raw: dict[str, Any]) -> LLMAnalysisResult:
    """Turn the JSON object returned by the LLM into a validated DTO.

    Raises :class:`ValueError` on anything unexpected. The caller
    (API endpoint) translates that into HTTP 502 for the client.
    """
    if not isinstance(raw, dict):
        raise ValueError("LLM response must be a JSON object")

    protocol_raw = raw.get("protocol") or {}
    if not isinstance(protocol_raw, dict):
        raise ValueError("protocol must be an object")

    protocol = LLMProtocolPart(
        complaints=_as_str(protocol_raw.get("complaints", "")),
        anamnesis=_as_str(protocol_raw.get("anamnesis", "")),
        examination=_as_str(protocol_raw.get("examination", "")),
        allergies=_as_str(protocol_raw.get("allergies", "")),
        medications=_as_str(protocol_raw.get("medications", "")),
    )

    red_flags_raw = raw.get("red_flags") or []
    if not isinstance(red_flags_raw, list):
        raise ValueError("red_flags must be a list")
    red_flags: list[LLMRedFlag] = []
    for item in red_flags_raw:
        if not isinstance(item, dict):
            raise ValueError("red_flag must be an object")
        severity = item.get("severity")
        if severity not in ("low", "medium", "high"):
            raise ValueError(f"invalid severity: {severity!r}")
        red_flags.append(
            LLMRedFlag(
                label=_as_str(item.get("label", "")),
                description=_as_str(item.get("description", "")),
                severity=severity,  # type: ignore[arg-type]
            )
        )

    diagnoses_raw = raw.get("diagnosis_suggestions") or []
    if not isinstance(diagnoses_raw, list):
        raise ValueError("diagnosis_suggestions must be a list")
    diagnoses: list[LLMDiagnosisSuggestion] = []
    for item in diagnoses_raw:
        if not isinstance(item, dict):
            raise ValueError("diagnosis_suggestion must be an object")
        probability = item.get("probability")
        if not isinstance(probability, (int, float)):
            raise ValueError("probability must be a number")
        probability = float(probability)
        if not (0.0 <= probability <= 1.0):
            raise ValueError(f"probability out of range: {probability}")
        diagnoses.append(
            LLMDiagnosisSuggestion(
                title=_as_str(item.get("title", "")),
                icd10_code=_as_opt_str(item.get("icd10_code")),
                probability=probability,
                reasoning=_as_str(item.get("reasoning", "")),
                supporting_symptoms=_as_str_list(item.get("supporting_symptoms", [])),
                contradicting_symptoms=_as_str_list(
                    item.get("contradicting_symptoms", [])
                ),
            )
        )
    if len(diagnoses) > 3:
        raise ValueError("diagnosis_suggestions must not contain more than 3 items")
    diagnoses.sort(key=lambda d: d.probability, reverse=True)

    plan_raw = raw.get("treatment_plan") or []
    if not isinstance(plan_raw, list):
        raise ValueError("treatment_plan must be a list")
    plan: list[LLMTreatmentItem] = []
    for item in plan_raw:
        if not isinstance(item, dict):
            raise ValueError("treatment item must be an object")
        kind = item.get("kind")
        if kind not in ("medication", "investigation", "non_drug", "follow_up"):
            raise ValueError(f"invalid treatment kind: {kind!r}")
        plan.append(
            LLMTreatmentItem(
                kind=kind,  # type: ignore[arg-type]
                title=_as_str(item.get("title", "")),
                details=_as_str(item.get("details", "")),
                dosage=_as_opt_str(item.get("dosage")),
                duration=_as_opt_str(item.get("duration")),
            )
        )

    return LLMAnalysisResult(
        protocol=protocol,
        red_flags=red_flags,
        diagnosis_suggestions=diagnoses,
        treatment_plan=plan,
    )


# ---------------------------------------------------------------------------
# OpenAI implementation
# ---------------------------------------------------------------------------


class OpenAIStructuredLLM:
    """OpenAI ``chat.completions`` with Structured Outputs (JSON schema).

    The client is created lazily on the first call so the app can boot
    (and tests can run) without ``OPENAI_API_KEY`` in the environment.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gpt-4o-mini",
        temperature: float = 0.2,
        max_tokens: int = 2000,
    ) -> None:
        self._api_key = api_key or get_settings().OPENAI_API_KEY
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._client = None

    def _ensure_client(self):
        if self._client is not None:
            return self._client
        if not self._api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured")
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "openai package is required for OpenAIStructuredLLM; install `openai>=1.40`"
            ) from exc
        self._client = OpenAI(api_key=self._api_key)
        return self._client

    def _build_user_prompt(
        self,
        patient: PatientContext,
        transcript: list[TranscriptTurn],
    ) -> str:
        speaker_labels = {
            "doctor": "Врач",
            "patient": "Пациент",
            "unknown": "Неизвестно",
        }
        dialogue = "\n".join(
            f"{speaker_labels.get(t.speaker, t.speaker)}: {t.text}".strip()
            for t in transcript
            if (t.text or "").strip()
        )
        sex_labels = {"male": "мужской", "female": "женский", "other": "другой"}
        appt_labels = {"primary": "первичный", "follow_up": "повторный"}
        return (
            "Контекст пациента:\n"
            f"- возраст: {patient.age}\n"
            f"- пол: {sex_labels.get(patient.sex, patient.sex)}\n"
            f"- тип приёма: {appt_labels.get(patient.appointment_type, patient.appointment_type)}\n"
            "\nРасшифровка диалога приёма:\n"
            f"{dialogue}\n"
        )

    async def analyze_dialogue(
        self,
        patient: PatientContext,
        transcript: list[TranscriptTurn],
    ) -> LLMAnalysisResult:
        client = self._ensure_client()
        user_prompt = self._build_user_prompt(patient, transcript)

        import anyio

        def _call() -> dict[str, Any]:
            response = client.chat.completions.create(
                model=self._model,
                temperature=self._temperature,
                max_tokens=self._max_tokens,
                response_format={
                    "type": "json_schema",
                    "json_schema": _RESPONSE_JSON_SCHEMA,
                },
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
            )
            content = response.choices[0].message.content or ""
            try:
                return json.loads(content)
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    f"LLM returned non-JSON content: {exc}"
                ) from exc

        try:
            raw = await anyio.to_thread.run_sync(_call)
        except RuntimeError:
            raise
        except Exception as exc:
            logger.exception("OpenAI LLM call failed: %s", exc)
            raise RuntimeError(f"LLM call failed: {exc}") from exc

        return parse_llm_response(raw)


# ---------------------------------------------------------------------------
# FastAPI DI
# ---------------------------------------------------------------------------


_default_llm: LLMService | None = None


def get_llm_service() -> LLMService:
    """FastAPI dependency returning a singleton LLM service.

    Tests override this via ``app.dependency_overrides[get_llm_service]``.
    """
    global _default_llm
    if _default_llm is None:
        _default_llm = OpenAIStructuredLLM()
    return _default_llm
