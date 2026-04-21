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
    "Ты — ИИ-ассистент врача. Твоя задача — по расшифровке амбулаторного "
    "приёма подготовить ЧЕРНОВИК структурированного протокола, топ "
    "диагнозов и плана лечения.\n"
    "\n"
    "ВАЖНО ПРО ОТКАЗЫ: это черновик, врач обязательно проверит и "
    "отредактирует каждое поле перед финализацией. Твоя задача — "
    "максимально полно ИЗВЛЕЧЬ информацию, которая уже прозвучала, "
    "и предложить уверенные гипотезы. НЕЛЬЗЯ возвращать "
    "«Недостаточно данных», если пациент упомянул хотя бы один "
    "конкретный симптом (кашель, одышка, боль, температура и т.п.). "
    "Даже если говорил только пациент (монолог без реплик врача), "
    "ты ОБЯЗАН извлечь из его слов жалобы и анамнез. Пустой ответ "
    "допустим ТОЛЬКО если вся расшифровка короче ~8 слов ИЛИ в ней "
    "нет ни одного описания симптома/ощущения.\n"
    "\n"
    "ЖЁСТКИЕ ТЕХНИЧЕСКИЕ ПРАВИЛА:\n"
    "1. Отвечай СТРОГО в виде JSON-объекта по предоставленной схеме. "
    "Никакого текста вне JSON, никаких markdown-блоков.\n"
    "2. Все поля — на русском языке.\n"
    "3. Не выдумывай конкретные дозировки/препараты/анализы, которых "
    "не подразумевает клиническая картина. Но обобщённые клинические "
    "выводы (например, «характерно для бронхиальной астмы») делать "
    "МОЖНО и НУЖНО — ты для этого и нужен.\n"
    "\n"
    "КАК ЗАПОЛНЯТЬ ПОЛЯ protocol:\n"
    "- `complaints` — перечисли конкретные жалобы пациента (симптомы, "
    "их длительность, локализация, триггеры, характер). Это поле "
    "практически всегда должно быть заполнено, если в диалоге есть "
    "хотя бы одно упоминание симптома. При необходимости переформулируй "
    "в клиническом стиле: «у меня отдышка рядом с животными» → "
    "«эпизоды одышки при контакте с животными».\n"
    "- `anamnesis` — история настоящего заболевания (когда началось, "
    "как развивалось, что провоцирует/облегчает), сопутствующие и "
    "перенесённые заболевания. Если пациент назвал триггер (например, "
    "«когда рядом с животными»), это часть anamnesis.\n"
    "- `examination` — то, что ВРАЧ СООБЩИЛ ВСЛУХ о физикальном "
    "осмотре (осмотрел, пальпировал, выслушал — что увидел). Если "
    "осмотр в записи не озвучивался — оставь \"\".\n"
    "- `allergies` — если пациент явно подтвердил отсутствие аллергий, "
    "напиши «Аллергологический анамнез не отягощён». Если упомянул "
    "конкретные — перечисли. Если не спрашивали — оставь \"\".\n"
    "- `medications` — препараты, которые пациент принимает сейчас "
    "или недавно. Если не упоминалось — \"\".\n"
    "\n"
    "DIAGNOSIS_SUGGESTIONS:\n"
    "- До 3 вариантов, отсортированных по убыванию probability "
    "(число в [0, 1]). Если симптомы образуют классическую картину "
    "(например, одышка + свистящее дыхание + кашель + триггер — "
    "аллерген/физическая нагрузка → бронхиальная астма) — смело "
    "ставь probability 0.7–0.85 у лидера.\n"
    "- `icd10_code` — строка МКБ-10 (например, «J45.0» для "
    "аллергической астмы, «J06.9» для ОРВИ) или null, если не уверен.\n"
    "- `supporting_symptoms` / `contradicting_symptoms` — КОНКРЕТНЫЕ "
    "фразы/симптомы из расшифровки.\n"
    "- `reasoning` — 1–2 предложения клинического обоснования.\n"
    "\n"
    "TREATMENT_PLAN (черновик назначений — врач утвердит):\n"
    "- kind ∈ {medication, investigation, non_drug, follow_up}.\n"
    "- Добавь осмысленные обследования для подтверждения диагноза "
    "(например, спирометрия / пикфлоуметрия при подозрении на астму; "
    "мазок из зева при фарингите; ОАК + СРБ при лихорадке).\n"
    "- Для распространённых состояний предложи хотя бы один препарат "
    "с предполагаемой дозировкой и длительностью (например, "
    "парацетамол 500 мг до 4 раз в сутки при T >38 °C; сальбутамол "
    "100 мкг по потребности при приступе одышки).\n"
    "- Немедикаментозные рекомендации — режим, элиминация триггера, "
    "питьё. Контрольный визит — через сколько дней прийти повторно.\n"
    "- `dosage` / `duration` могут быть null, если неприменимо.\n"
    "\n"
    "RED_FLAGS (опционально):\n"
    "- Тревожные симптомы с severity ∈ {low, medium, high}: одышка в "
    "покое, кровохарканье, T >39 °C более 3 суток, ригидность "
    "затылочных мышц, острая боль в груди и т.п.\n"
    "- Если таких симптомов нет — верни пустой массив [].\n"
    "\n"
    "ЕДИНСТВЕННЫЙ СЛУЧАЙ ПУСТОГО ОТВЕТА:\n"
    "Вся расшифровка короче ~8 слов ИЛИ не содержит ни одного "
    "описания симптома/жалобы/ощущения. Только тогда `complaints` = "
    "«Недостаточно данных для анализа», остальные строки — \"\", "
    "массивы — []."
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
    """OpenAI-compatible ``chat.completions`` client for structured analysis.

    Works with any server that implements the OpenAI Chat Completions API:
    OpenAI itself, LM Studio, Ollama (``/v1``), DeepSeek, Groq, etc.

    JSON enforcement strategy is configurable via ``json_mode``:
    * ``"json_schema"`` — Structured Outputs (strict schema). Supported by
      OpenAI ``gpt-4o``/``gpt-4o-mini``.
    * ``"json_object"`` — loose JSON mode (the server guarantees valid JSON
      but not the shape). Supported by LM Studio, Ollama and most others.
      We inline a textual schema description into the system prompt and
      rely on :func:`parse_llm_response` for validation.

    The underlying client is created lazily so the app can boot (and tests
    can run) without any LLM credentials configured.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        json_mode: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 2000,
    ) -> None:
        settings = get_settings()
        self._api_key = api_key if api_key is not None else settings.resolved_llm_api_key
        self._model = model or settings.LLM_MODEL
        self._base_url = base_url or settings.LLM_BASE_URL
        self._json_mode = json_mode or settings.LLM_JSON_MODE
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._client = None

    def _ensure_client(self):
        if self._client is not None:
            return self._client
        # Local servers (LM Studio, Ollama) typically do not require a key,
        # but the OpenAI SDK still wants a non-empty string. Use a dummy
        # when the user hasn't set one.
        api_key = self._api_key or "not-needed"
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "openai package is required for OpenAIStructuredLLM; install `openai>=1.40`"
            ) from exc
        self._client = OpenAI(api_key=api_key, base_url=self._base_url)
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

    def _build_system_prompt(self) -> str:
        if self._json_mode == "json_schema":
            return SYSTEM_PROMPT
        # Loose JSON mode: inject the schema textually so the model knows
        # the expected shape. Validation happens locally after the call.
        schema_text = json.dumps(_RESPONSE_JSON_SCHEMA["schema"], ensure_ascii=False, indent=2)
        return (
            SYSTEM_PROMPT
            + "\n\nВерни ответ строго в виде JSON-объекта, соответствующего "
            "следующей JSON-схеме (additionalProperties:false). Не добавляй "
            "лишних полей и не оборачивай ответ в markdown-блоки.\n"
            f"Схема:\n{schema_text}"
        )

    def _response_format(self) -> dict[str, Any]:
        if self._json_mode == "json_schema":
            return {"type": "json_schema", "json_schema": _RESPONSE_JSON_SCHEMA}
        return {"type": "json_object"}

    async def analyze_dialogue(
        self,
        patient: PatientContext,
        transcript: list[TranscriptTurn],
    ) -> LLMAnalysisResult:
        client = self._ensure_client()
        user_prompt = self._build_user_prompt(patient, transcript)
        system_prompt = self._build_system_prompt()
        response_format = self._response_format()

        import anyio

        def _call() -> dict[str, Any]:
            response = client.chat.completions.create(
                model=self._model,
                temperature=self._temperature,
                max_tokens=self._max_tokens,
                response_format=response_format,
                messages=[
                    {"role": "system", "content": system_prompt},
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
            logger.exception("LLM call failed: %s", exc)
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
