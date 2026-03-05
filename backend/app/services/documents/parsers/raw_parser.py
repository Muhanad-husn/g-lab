"""Tier-3 (basic) document parser using PyPDF2 and python-docx.

Plain-text extraction only — no structural information is preserved.
Used as the final fallback when Tier-1 and Tier-2 parsers fail.
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


class ParseError(Exception):
    """Raised when the parser cannot extract text from a document."""


class RawParser:
    """Tier-3 plain-text document parser.

    Supports PDF (via PyPDF2) and DOCX (via python-docx).
    Returns ``parse_tier="basic"`` with one :class:`Section` per page/paragraph.

    Usage::

        parser = RawParser()
        result = parser.parse(Path("report.pdf"), "application/pdf")
        print(result.text[:200])
    """

    def parse(self, file_path: Path, mime_type: str) -> ParseResult:
        """Extract plain text from *file_path*.

        Args:
            file_path: Absolute path to the document file.
            mime_type: MIME type of the file (used to select the sub-parser).

        Returns:
            :class:`ParseResult` with ``parse_tier="basic"``.

        Raises:
            ValueError:  If *mime_type* is not supported.
            ParseError:  If text extraction fails (corrupt file, etc.).
        """
        if mime_type == "application/pdf":
            return self._parse_pdf(file_path)
        if mime_type in {
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/msword",
        }:
            return self._parse_docx(file_path)
        raise ValueError(
            f"Unsupported MIME type for RawParser: {mime_type!r}. "
            f"Supported: {sorted(_SUPPORTED_MIME_TYPES)}"
        )

    # ------------------------------------------------------------------
    # Sub-parsers
    # ------------------------------------------------------------------

    def _parse_pdf(self, file_path: Path) -> ParseResult:
        """Extract text from a PDF using PyPDF2."""
        try:
            import PyPDF2
        except ImportError as exc:
            raise ParseError("PyPDF2 is not installed. Cannot parse PDF.") from exc

        try:
            sections: list[Section] = []
            with open(file_path, "rb") as fh:
                reader = PyPDF2.PdfReader(fh)
                for page_num, page in enumerate(reader.pages, start=1):
                    page_text = page.extract_text() or ""
                    page_text = page_text.strip()
                    if page_text:
                        sections.append(
                            Section(
                                content=page_text,
                                heading=None,
                                page_number=page_num,
                            )
                        )
            full_text = "\n\n".join(s.content for s in sections)
            logger.info(
                "raw_parser_pdf_done",
                file=str(file_path),
                pages=len(sections),
                chars=len(full_text),
            )
            return ParseResult(
                text=full_text,
                sections=sections if sections else None,
                parse_tier="basic",
            )
        except ParseError:
            raise
        except Exception as exc:
            raise ParseError(f"Failed to parse PDF {file_path}: {exc}") from exc

    def _parse_docx(self, file_path: Path) -> ParseResult:
        """Extract text from a DOCX using python-docx."""
        try:
            import docx
        except ImportError as exc:
            raise ParseError(
                "python-docx is not installed. Cannot parse DOCX."
            ) from exc

        try:
            document = docx.Document(str(file_path))
            sections: list[Section] = []
            for para in document.paragraphs:
                text = para.text.strip()
                if text:
                    sections.append(
                        Section(
                            content=text,
                            heading=None,
                            page_number=None,
                        )
                    )
            full_text = "\n\n".join(s.content for s in sections)
            logger.info(
                "raw_parser_docx_done",
                file=str(file_path),
                paragraphs=len(sections),
                chars=len(full_text),
            )
            return ParseResult(
                text=full_text,
                sections=sections if sections else None,
                parse_tier="basic",
            )
        except ParseError:
            raise
        except Exception as exc:
            raise ParseError(f"Failed to parse DOCX {file_path}: {exc}") from exc
