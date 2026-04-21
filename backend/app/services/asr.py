"""Speech-to-text service abstraction.

Provides a minimal ``ASRService`` protocol plus an OpenAI Whisper
implementation. The FastAPI dependency ``get_asr_service`` can be
overridden in tests via ``app.dependency_overrides``.

We deliberately do **not** persist any audio bytes to disk or in the
database — only recognized text ends up in ``transcripts`` (see Step-3
constraint in ``plan/step-3.md``).
"""
from __future__ import annotations

import io
import logging
import re
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Known Whisper hallucinations on silent / near-silent audio. The model was
# trained on YouTube with burned-in subtitles, so it's prone to spitting out
# channel credits when there is no speech. Matching is case-insensitive and
# anchored to the whole trimmed string, so we don't accidentally drop real
# dialogue that happens to contain these words.
_HALLUCINATION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^субтитры.*$", re.IGNORECASE | re.DOTALL),
    re.compile(r"^редактор\s+субтитров.*$", re.IGNORECASE | re.DOTALL),
    re.compile(r"^корректор\s+субтитров.*$", re.IGNORECASE | re.DOTALL),
    re.compile(r"^продолжение\s+следует.*$", re.IGNORECASE | re.DOTALL),
    re.compile(r"^спасибо\s+за\s+просмотр.*$", re.IGNORECASE | re.DOTALL),
    re.compile(r"^ставьте\s+лайк.*$", re.IGNORECASE | re.DOTALL),
    re.compile(r"^подпишитесь\s+на\s+канал.*$", re.IGNORECASE | re.DOTALL),
    re.compile(r"^dimatorzok.*$", re.IGNORECASE | re.DOTALL),
    re.compile(r"^[\.\,\!\?\s…]+$"),
)


def _looks_like_hallucination(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return True
    # Single-word "субтитры" / "спасибо" etc. on their own are almost always
    # hallucinations in an appointment context.
    if len(stripped.split()) <= 1 and len(stripped) < 15:
        low = stripped.lower().strip(" .,!?…")
        if low in {"субтитры", "спасибо", "продолжение", "dimatorzok", "хм", "эм"}:
            return True
    return any(p.match(stripped) for p in _HALLUCINATION_PATTERNS)


@dataclass(slots=True)
class ASRResult:
    text: str
    confidence: float | None = None


@runtime_checkable
class ASRService(Protocol):
    async def transcribe_chunk(
        self,
        audio_bytes: bytes,
        mime: str,
        language: str = "ru",
    ) -> ASRResult: ...


def _mime_to_extension(mime: str | None) -> str:
    """Map a MIME type to a filename extension Whisper accepts."""
    if not mime:
        return "webm"
    mime = mime.lower()
    if "webm" in mime:
        return "webm"
    if "ogg" in mime or "opus" in mime:
        return "ogg"
    if "wav" in mime:
        return "wav"
    if "mp3" in mime or "mpeg" in mime:
        return "mp3"
    if "m4a" in mime or "mp4" in mime:
        return "m4a"
    if "flac" in mime:
        return "flac"
    return "webm"


class OpenAIWhisperASR:
    """Whisper-compatible ASR client.

    Works with any server that implements the OpenAI
    ``audio.transcriptions`` endpoint: OpenAI, ``faster-whisper-server``,
    Groq, Yandex's OpenAI-compatible proxy, etc.

    The client is created lazily on the first call so that the app can
    boot without any API key when tests override the service.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
    ) -> None:
        settings = get_settings()
        self._api_key = api_key if api_key is not None else settings.resolved_asr_api_key
        self._model = model or settings.ASR_MODEL
        self._base_url = base_url or settings.ASR_BASE_URL
        self._client = None

    def _ensure_client(self):
        if self._client is not None:
            return self._client
        # Local ASR servers (faster-whisper-server) accept any key; the
        # OpenAI SDK rejects an empty string, so substitute a placeholder.
        api_key = self._api_key or "not-needed"
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - import guard
            raise RuntimeError(
                "openai package is required for OpenAIWhisperASR; install `openai>=1`"
            ) from exc
        self._client = OpenAI(api_key=api_key, base_url=self._base_url)
        return self._client

    async def transcribe_chunk(
        self,
        audio_bytes: bytes,
        mime: str,
        language: str = "ru",
    ) -> ASRResult:
        client = self._ensure_client()
        extension = _mime_to_extension(mime)
        filename = f"chunk.{extension}"

        import anyio

        # faster-whisper-server / faster-whisper accept a Silero VAD pass
        # that skips silent frames entirely. This dramatically reduces the
        # YouTube-subtitles hallucination problem on quiet audio. OpenAI's
        # cloud Whisper ignores unknown fields, so passing them is safe.
        extra_body = {
            "vad_filter": "true",
            "no_speech_threshold": "0.6",
            "temperature": "0",
        }

        def _call() -> ASRResult:
            buffer = io.BytesIO(audio_bytes)
            buffer.name = filename
            # ``verbose_json`` is supported by OpenAI and faster-whisper-server.
            # Some servers may fall back to plain ``json`` — we read ``text``
            # defensively below either way.
            response = client.audio.transcriptions.create(
                model=self._model,
                file=(filename, buffer, mime or f"audio/{extension}"),
                language=language,
                response_format="verbose_json",
                extra_body=extra_body,
            )
            text = getattr(response, "text", "") or ""
            confidence: float | None = None
            segments = getattr(response, "segments", None) or []
            if segments:
                log_probs = [
                    getattr(s, "avg_logprob", None)
                    if not isinstance(s, dict)
                    else s.get("avg_logprob")
                    for s in segments
                ]
                log_probs = [lp for lp in log_probs if isinstance(lp, (int, float))]
                if log_probs:
                    import math

                    avg = sum(log_probs) / len(log_probs)
                    confidence = max(0.0, min(1.0, math.exp(avg)))

            cleaned = text.strip()
            if _looks_like_hallucination(cleaned):
                logger.info("Dropped likely Whisper hallucination: %r", cleaned)
                cleaned = ""
            return ASRResult(text=cleaned, confidence=confidence)

        try:
            return await anyio.to_thread.run_sync(_call)
        except RuntimeError:
            raise
        except Exception as exc:
            logger.exception("ASR transcription failed: %s", exc)
            raise RuntimeError(f"ASR failed: {exc}") from exc


_default_asr: ASRService | None = None


def get_asr_service() -> ASRService:
    """FastAPI dependency returning a singleton ASR service.

    Tests can override this via ``app.dependency_overrides[get_asr_service] = ...``.
    """
    global _default_asr
    if _default_asr is None:
        _default_asr = OpenAIWhisperASR()
    return _default_asr
