"""Tier-1 document parser using the ``docling`` library.

Extracts structural information (headings, text, tables, lists) with
high fidelity via docling's document conversion pipeline.  Returns
``parse_tier="high"``.  If extraction fails for any reason, raises
:class:`ParseError` so the caller can fall through to the Tier-2
:class:`~app.services.documents.parsers.unstructured_parser.UnstructuredParser`.
"""

from __future__ import annotations

import contextlib
from pathlib import Path
from typing import Any

from app.core.logging import get_logger
from app.services.documents.parsers.base import ParseResult, Section

logger: Any = get_logger(__name__)

_SUPPORTED_MIME_TYPES: set[str] = set()  # No restriction — Docling auto-detects format

# Docling item label strings → heading
_HEADING_LABELS = {"section_header", "title"}

# Docling item label strings → content to accumulate
_CONTENT_LABELS = {
    "text",
    "paragraph",
    "list_item",
    "table",
    "caption",
    "code",
    "formula",
    "footnote",
}

# Docling item label strings → skip entirely
_SKIP_LABELS = {"page_header", "page_footer", "picture", "figure"}


class ParseError(Exception):
    """Raised when the parser cannot extract text from a document."""


class DoclingParser:
    """Tier-1 structured document parser backed by the ``docling`` library.

    Supported formats: PDF, DOCX, PPTX, HTML, Markdown, AsciiDoc, CSV,
    images, and others — Docling auto-detects from the file.  Items are
    grouped into
    :class:`~app.services.documents.parsers.base.Section` objects: each
    heading element starts a new section; content elements are accumulated
    under the current section.

    Usage::

        parser = DoclingParser()
        result = parser.parse(Path("report.pdf"), "application/pdf")
        for section in result.sections or []:
            print(section.heading, "→", section.content[:80])
    """

    def parse(self, file_path: Path, mime_type: str) -> ParseResult:
        """Extract structured text from *file_path* using docling.

        Args:
            file_path: Absolute path to the document file.
            mime_type: MIME type of the file (for logging; format is auto-detected).

        Returns:
            :class:`ParseResult` with ``parse_tier="high"``.

        Raises:
            ParseError:   If extraction fails (import error, corrupt file, …).
        """
        try:
            from docling.document_converter import DocumentConverter
        except ImportError as exc:
            raise ParseError(
                "docling is not installed. Cannot parse document."
            ) from exc

        try:
            converter = DocumentConverter()
            result = converter.convert(str(file_path))
            doc = result.document
            sections = self._doc_to_sections(doc)
            full_text = "\n\n".join(s.content for s in sections)
            logger.info(
                "docling_parser_done",
                file=str(file_path),
                sections=len(sections),
                chars=len(full_text),
            )
            return ParseResult(
                text=full_text,
                sections=sections if sections else None,
                parse_tier="high",
            )
        except ParseError:
            raise
        except Exception as exc:
            raise ParseError(f"Docling failed to parse {file_path}: {exc}") from exc

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _doc_to_sections(self, doc: Any) -> list[Section]:
        """Convert docling document items to :class:`Section` objects.

        Each heading item (``section_header``, ``title``) starts a new section.
        Content items are accumulated under the current section heading.
        Items in :data:`_SKIP_LABELS` are ignored.

        If no heading is ever encountered, all content goes into a single
        anonymous section (``heading=None``).
        """
        sections: list[Section] = []
        current_heading: str | None = None
        current_page: int | None = None
        current_parts: list[str] = []

        def _flush() -> None:
            content = "\n".join(current_parts).strip()
            if content:
                sections.append(
                    Section(
                        content=content,
                        heading=current_heading,
                        page_number=current_page,
                    )
                )

        for item, _level in doc.iterate_items():
            label = str(getattr(item, "label", "")).lower()

            if label in _SKIP_LABELS:
                continue

            # Extract text — TextItem/SectionHeaderItem have .text;
            # TableItem may use .data.export_to_markdown().
            text = (getattr(item, "text", None) or "").strip()
            if not text:
                data = getattr(item, "data", None)
                if data is not None:
                    with contextlib.suppress(Exception):
                        text = (data.export_to_markdown() or "").strip()
            if not text:
                continue

            # Extract page number from provenance list
            prov = getattr(item, "prov", [])
            page_no: int | None = None
            if prov:
                page_no = getattr(prov[0], "page_no", None)

            if label in _HEADING_LABELS:
                _flush()
                current_heading = text
                current_page = page_no
                current_parts = []
            else:
                # Unknown labels treated as content
                if not current_parts and current_heading is None:
                    current_page = page_no
                current_parts.append(text)

        _flush()
        return sections
