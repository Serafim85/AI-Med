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
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from app.core.config import get_settings

logger = logging.getLogger(__name__)


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
    """Whisper-based ASR. Instantiates the OpenAI client lazily.

    Raises ``RuntimeError`` on the first call when ``OPENAI_API_KEY`` is
    empty, so misconfigured environments fail loudly rather than silently
    producing empty transcripts.
    """

    def __init__(self, api_key: str | None = None, model: str = "whisper-1") -> None:
        self._api_key = api_key or get_settings().OPENAI_API_KEY
        self._model = model
        self._client = None

    def _ensure_client(self):
        if self._client is not None:
            return self._client
        if not self._api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured")
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - import guard
            raise RuntimeError(
                "openai package is required for OpenAIWhisperASR; install `openai>=1`"
            ) from exc
        self._client = OpenAI(api_key=self._api_key)
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

        def _call() -> ASRResult:
            buffer = io.BytesIO(audio_bytes)
            buffer.name = filename
            response = client.audio.transcriptions.create(
                model=self._model,
                file=(filename, buffer, mime or f"audio/{extension}"),
                language=language,
                response_format="verbose_json",
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
            return ASRResult(text=text.strip(), confidence=confidence)

        try:
            return await anyio.to_thread.run_sync(_call)
        except RuntimeError:
            raise
        except Exception as exc:
            logger.exception("Whisper transcription failed: %s", exc)
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
