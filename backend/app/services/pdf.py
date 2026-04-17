"""PDF rendering service (Step 5).

Produces the final appointment protocol PDF from a Jinja2 HTML template
via WeasyPrint. Lazily imports WeasyPrint and the Jinja environment so
that tests / dev environments without the system libraries installed
can still import the service module.

The ``PdfService`` protocol exists so tests can override the FastAPI
dependency with a lightweight fake returning a valid ``%PDF`` byte
string (useful because WeasyPrint depends on native libs — ``pango``,
``cairo``, ``gdk-pixbuf``, …).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"


# ---------------------------------------------------------------------------
# DTOs
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class ProtocolPdfPatient:
    full_name: str
    age: int
    sex: str  # russian label


@dataclass(slots=True)
class ProtocolPdfDoctor:
    full_name: str


@dataclass(slots=True)
class ProtocolPdfRedFlag:
    label: str
    description: str | None
    severity: str  # russian label
    accepted: bool  # True = принято, False = отклонено
    note: str | None


@dataclass(slots=True)
class ProtocolPdfTreatmentItem:
    title: str
    details: str | None
    dosage: str | None
    duration: str | None
    is_confirmed: bool


@dataclass(slots=True)
class ProtocolPdfTreatmentGroup:
    kind_label: str  # russian label (медикаменты, обследования, …)
    items: list[ProtocolPdfTreatmentItem]


@dataclass(slots=True)
class ProtocolPdfData:
    session_id: str
    appointment_type: str  # russian label
    appointment_date: str  # pre-formatted dd.mm.yyyy HH:MM
    patient: ProtocolPdfPatient
    doctor: ProtocolPdfDoctor
    complaints: str
    anamnesis: str
    examination: str
    allergies: str
    medications: str
    final_diagnosis: str | None
    icd10_code: str | None
    red_flags: list[ProtocolPdfRedFlag] = field(default_factory=list)
    treatment_groups: list[ProtocolPdfTreatmentGroup] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class PdfService(Protocol):
    def render_protocol_pdf(self, data: ProtocolPdfData) -> bytes: ...


# ---------------------------------------------------------------------------
# WeasyPrint implementation
# ---------------------------------------------------------------------------


class WeasyPrintPdfService:
    """Renders ``protocol.html`` via Jinja2 + WeasyPrint into PDF bytes."""

    def __init__(self, templates_dir: Path = TEMPLATES_DIR) -> None:
        self._templates_dir = templates_dir
        self._env = None

    def _ensure_env(self):
        if self._env is not None:
            return self._env
        try:
            from jinja2 import Environment, FileSystemLoader, select_autoescape
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "jinja2 is not installed — `pip install jinja2>=3.1`"
            ) from exc
        self._env = Environment(
            loader=FileSystemLoader(str(self._templates_dir)),
            autoescape=select_autoescape(["html", "xml"]),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        return self._env

    def render_protocol_pdf(self, data: ProtocolPdfData) -> bytes:
        env = self._ensure_env()
        template = env.get_template("protocol.html")
        html_str = template.render(data=data)

        try:
            from weasyprint import HTML  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "weasyprint is not installed or its system dependencies are "
                "missing (libpango, libcairo, libgdk-pixbuf)"
            ) from exc

        try:
            pdf_bytes = HTML(
                string=html_str,
                base_url=str(self._templates_dir),
            ).write_pdf()
        except Exception as exc:
            logger.exception("WeasyPrint failed: %s", exc)
            raise RuntimeError(f"Не удалось сформировать PDF: {exc}") from exc
        return pdf_bytes or b""


# ---------------------------------------------------------------------------
# FastAPI DI
# ---------------------------------------------------------------------------


_default_pdf: PdfService | None = None


def get_pdf_service() -> PdfService:
    """FastAPI dependency returning a singleton PDF service.

    Tests override this via ``app.dependency_overrides[get_pdf_service]``.
    """
    global _default_pdf
    if _default_pdf is None:
        _default_pdf = WeasyPrintPdfService()
    return _default_pdf
