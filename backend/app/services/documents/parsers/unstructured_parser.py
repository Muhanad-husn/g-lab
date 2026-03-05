"""Tier-2 document parser using the ``unstructured`` library.

Extracts structural information (headings, narrative text, list items,
tables) and maps them to :class:`Section` objects.  Returns
``parse_tier="standard"``.  If extraction fails for any reason, raises
:class:`ParseError` so the caller can fall through to the Tier-3
:class:`~app.services.documents.parsers.raw_parser.RawParser`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.core.logging import get_logger
from app.services.documents.parsers.base import ParseResult, Section

logger: Any = get_logger(__name__)

_SUPPORTED_MIME_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
}

# Element type names that carry meaningful content and should be included.
_CONTENT_ELEMENT_TYPES = {
    "NarrativeText",
    "ListItem",
    "Table",
    "Text",
    "FigureCaption",
    "Address",
    "EmailAddress",
    "Formula",
    "CodeSnippet",
}

# Element type names that act as section headings.
_HEADING_ELEMENT_TYPES = {"Title", "Header"}

# Element type names to skip entirely.
_SKIP_ELEMENT_TYPES = {"Footer", "PageBreak", "Image"}


class ParseError(Exception):
    """Raised when the parser cannot extract text from a document."""


class UnstructuredParser:
    """Tier-2 structured document parser backed by the ``unstructured`` library.

    Supported formats: PDF, DOCX.  Elements are grouped into
    :class:`~app.services.documents.parsers.base.Section` objects: each
    ``Title``/``Header`` element starts a new section; ``NarrativeText``,
    ``ListItem``, ``Table`` etc. are accumulated under the current section.

    Usage::

        parser = UnstructuredParser()
        result = parser.parse(Path("report.pdf"), "application/pdf")
        for section in result.sections or []:
            print(section.heading, "→", section.content[:80])
    """

    def parse(self, file_path: Path, mime_type: str) -> ParseResult:
        """Extract structured text from *file_path*.

        Args:
            file_path: Absolute path to the document file.
            mime_type: MIME type of the file (used to select the sub-parser).

        Returns:
            :class:`ParseResult` with ``parse_tier="standard"``.

        Raises:
            ValueError:   If *mime_type* is not supported.
            ParseError:   If extraction fails (import error, corrupt file, …).
        """
        if mime_type == "application/pdf":
            return self._parse_pdf(file_path)
        if mime_type in {
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/msword",
        }:
            return self._parse_docx(file_path)
        raise ValueError(
            f"Unsupported MIME type for UnstructuredParser: {mime_type!r}. "
            f"Supported: {sorted(_SUPPORTED_MIME_TYPES)}"
        )

    # ------------------------------------------------------------------
    # Sub-parsers
    # ------------------------------------------------------------------

    def _parse_pdf(self, file_path: Path) -> ParseResult:
        """Partition a PDF with ``unstructured`` and convert to sections."""
        try:
            from unstructured.partition.pdf import partition_pdf  # type: ignore[import]
        except ImportError as exc:
            raise ParseError(
                "unstructured[pdf] is not installed. Cannot parse PDF."
            ) from exc

        try:
            elements = partition_pdf(filename=str(file_path))
            sections = self._elements_to_sections(elements)
            full_text = "\n\n".join(s.content for s in sections)
            logger.info(
                "unstructured_parser_pdf_done",
                file=str(file_path),
                sections=len(sections),
                chars=len(full_text),
            )
            return ParseResult(
                text=full_text,
                sections=sections if sections else None,
                parse_tier="standard",
            )
        except ParseError:
            raise
        except Exception as exc:
            raise ParseError(
                f"Unstructured failed to parse PDF {file_path}: {exc}"
            ) from exc

    def _parse_docx(self, file_path: Path) -> ParseResult:
        """Partition a DOCX with ``unstructured`` and convert to sections."""
        try:
            from unstructured.partition.docx import (
                partition_docx,  # type: ignore[import]
            )
        except ImportError as exc:
            raise ParseError(
                "unstructured[docx] is not installed. Cannot parse DOCX."
            ) from exc

        try:
            elements = partition_docx(filename=str(file_path))
            sections = self._elements_to_sections(elements)
            full_text = "\n\n".join(s.content for s in sections)
            logger.info(
                "unstructured_parser_docx_done",
                file=str(file_path),
                sections=len(sections),
                chars=len(full_text),
            )
            return ParseResult(
                text=full_text,
                sections=sections if sections else None,
                parse_tier="standard",
            )
        except ParseError:
            raise
        except Exception as exc:
            raise ParseError(
                f"Unstructured failed to parse DOCX {file_path}: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Element → Section grouping
    # ------------------------------------------------------------------

    def _elements_to_sections(self, elements: list[Any]) -> list[Section]:
        """Convert a flat list of ``unstructured`` elements to sections.

        Each heading element (``Title``, ``Header``) starts a new section.
        Content elements (``NarrativeText``, ``ListItem``, ``Table``, …) are
        accumulated under the current section.  Elements in
        :data:`_SKIP_ELEMENT_TYPES` are ignored.

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

        for element in elements:
            element_type = type(element).__name__

            if element_type in _SKIP_ELEMENT_TYPES:
                continue

            text = (getattr(element, "text", None) or "").strip()
            if not text:
                continue

            page: int | None = None
            metadata = getattr(element, "metadata", None)
            if metadata is not None:
                page = getattr(metadata, "page_number", None)

            if element_type in _HEADING_ELEMENT_TYPES:
                # Flush the previous section before starting a new one.
                _flush()
                current_heading = text
                current_page = page
                current_parts = []
            elif (
                element_type in _CONTENT_ELEMENT_TYPES
                or element_type not in _SKIP_ELEMENT_TYPES
            ):
                # Unknown element types are treated as content.
                if not current_parts and current_heading is None:
                    # First content before any heading — start anonymous section.
                    current_page = page
                current_parts.append(text)

        _flush()
        return sections
