"""Unit tests for RawParser (mocked PyPDF2 and python-docx)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, mock_open, patch

import pytest

# ---------------------------------------------------------------------------
# Inject stub modules before the module under test is imported so it can
# be loaded without the real third-party packages installed.
# ---------------------------------------------------------------------------
if "PyPDF2" not in sys.modules:
    sys.modules["PyPDF2"] = MagicMock()
if "docx" not in sys.modules:
    sys.modules["docx"] = MagicMock()

from app.services.documents.parsers.base import ParseResult, Section  # noqa: E402
from app.services.documents.parsers.raw_parser import ParseError, RawParser  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_pdf_reader(pages_text: list[str]) -> MagicMock:
    """Return a mock PdfReader whose .pages yields pages with .extract_text()."""
    mock_pages = []
    for text in pages_text:
        page = MagicMock()
        page.extract_text.return_value = text
        mock_pages.append(page)
    reader = MagicMock()
    reader.pages = mock_pages
    return reader


def _make_docx_document(paragraphs_text: list[str]) -> MagicMock:
    """Return a mock Document whose .paragraphs list has .text attributes."""
    mock_paras = []
    for text in paragraphs_text:
        para = MagicMock()
        para.text = text
        mock_paras.append(para)
    doc = MagicMock()
    doc.paragraphs = mock_paras
    return doc


# ---------------------------------------------------------------------------
# PDF tests
# ---------------------------------------------------------------------------


class TestRawParserPDF:
    def test_parse_pdf_single_page(self) -> None:
        reader = _make_pdf_reader(["Hello world. This is a test."])
        with (
            patch("builtins.open", mock_open()),
            patch("PyPDF2.PdfReader", return_value=reader),
        ):
            result = RawParser().parse(Path("doc.pdf"), "application/pdf")

        assert result.parse_tier == "basic"
        assert "Hello world" in result.text
        assert result.sections is not None
        assert len(result.sections) == 1
        assert result.sections[0].page_number == 1
        assert result.sections[0].heading is None

    def test_parse_pdf_multiple_pages(self) -> None:
        reader = _make_pdf_reader(["Page one text.", "Page two text.", "Page three."])
        with (
            patch("builtins.open", mock_open()),
            patch("PyPDF2.PdfReader", return_value=reader),
        ):
            result = RawParser().parse(Path("multi.pdf"), "application/pdf")

        assert result.parse_tier == "basic"
        assert result.sections is not None
        assert len(result.sections) == 3
        page_numbers = [s.page_number for s in result.sections]
        assert page_numbers == [1, 2, 3]
        assert "Page one text." in result.text
        assert "Page three." in result.text

    def test_parse_pdf_skips_empty_pages(self) -> None:
        reader = _make_pdf_reader(["Content here.", "   ", "", "More content."])
        with (
            patch("builtins.open", mock_open()),
            patch("PyPDF2.PdfReader", return_value=reader),
        ):
            result = RawParser().parse(Path("sparse.pdf"), "application/pdf")

        assert result.sections is not None
        # Only non-empty pages become sections
        assert len(result.sections) == 2
        assert result.sections[0].page_number == 1
        assert result.sections[1].page_number == 4

    def test_parse_pdf_all_empty_pages_returns_none_sections(self) -> None:
        reader = _make_pdf_reader(["", "   "])
        with (
            patch("builtins.open", mock_open()),
            patch("PyPDF2.PdfReader", return_value=reader),
        ):
            result = RawParser().parse(Path("empty.pdf"), "application/pdf")

        assert result.sections is None
        assert result.text == ""

    def test_parse_pdf_raises_parse_error_on_corrupt_file(self) -> None:
        with (
            patch("builtins.open", mock_open()),
            patch("PyPDF2.PdfReader", side_effect=Exception("corrupted")),
        ):
            with pytest.raises(ParseError, match="Failed to parse PDF"):
                RawParser().parse(Path("bad.pdf"), "application/pdf")


# ---------------------------------------------------------------------------
# DOCX tests
# ---------------------------------------------------------------------------


class TestRawParserDOCX:
    def test_parse_docx_basic(self) -> None:
        doc = _make_docx_document(["Introduction paragraph.", "Second paragraph."])
        with patch("docx.Document", return_value=doc):
            result = RawParser().parse(
                Path("report.docx"),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )

        assert result.parse_tier == "basic"
        assert "Introduction paragraph." in result.text
        assert result.sections is not None
        assert len(result.sections) == 2
        # DOCX sections have no page numbers
        assert all(s.page_number is None for s in result.sections)

    def test_parse_docx_skips_blank_paragraphs(self) -> None:
        doc = _make_docx_document(["First.", "", "  ", "Last."])
        with patch("docx.Document", return_value=doc):
            result = RawParser().parse(
                Path("doc.docx"),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )

        assert result.sections is not None
        assert len(result.sections) == 2

    def test_parse_docx_raises_parse_error_on_failure(self) -> None:
        with patch("docx.Document", side_effect=Exception("bad file")):
            with pytest.raises(ParseError, match="Failed to parse DOCX"):
                RawParser().parse(
                    Path("broken.docx"),
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )

    def test_parse_msword_mime_type_accepted(self) -> None:
        doc = _make_docx_document(["Some text."])
        with patch("docx.Document", return_value=doc):
            result = RawParser().parse(Path("old.doc"), "application/msword")

        assert result.parse_tier == "basic"


# ---------------------------------------------------------------------------
# Text fallback
# ---------------------------------------------------------------------------


class TestRawParserTextFallback:
    def test_text_plain_uses_text_fallback(self, tmp_path: Path) -> None:
        txt_file = tmp_path / "notes.txt"
        txt_file.write_text("Hello world\nSecond line", encoding="utf-8")
        result = RawParser().parse(txt_file, "text/plain")
        assert result.parse_tier == "basic"
        assert "Hello world" in result.text

    def test_unknown_mime_uses_text_fallback(self, tmp_path: Path) -> None:
        f = tmp_path / "data.csv"
        f.write_text("a,b,c\n1,2,3", encoding="utf-8")
        result = RawParser().parse(f, "text/csv")
        assert result.parse_tier == "basic"
        assert "a,b,c" in result.text

    def test_empty_text_file_raises_parse_error(self, tmp_path: Path) -> None:
        f = tmp_path / "empty.txt"
        f.write_text("", encoding="utf-8")
        from app.services.documents.parsers.raw_parser import ParseError

        with pytest.raises(ParseError, match="empty"):
            RawParser().parse(f, "text/plain")
