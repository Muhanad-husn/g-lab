"""Unit tests for UnstructuredParser (Tier 2), fully mocked."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch  # MagicMock used for stub modules

import pytest

# ---------------------------------------------------------------------------
# Inject stub top-level modules before the module under test is imported so
# it can be loaded without the real third-party package installed.
# ---------------------------------------------------------------------------

_unstructured_stub = MagicMock()
_partition_auto_stub = MagicMock()

if "unstructured" not in sys.modules:
    sys.modules["unstructured"] = _unstructured_stub
if "unstructured.partition" not in sys.modules:
    sys.modules["unstructured.partition"] = MagicMock()
if "unstructured.partition.auto" not in sys.modules:
    _auto_mod = MagicMock()
    _auto_mod.partition = _partition_auto_stub
    sys.modules["unstructured.partition.auto"] = _auto_mod

from app.services.documents.parsers.unstructured_parser import (  # noqa: E402
    ParseError,
    UnstructuredParser,
)

_PATCH_TARGET = "unstructured.partition.auto.partition"


# ---------------------------------------------------------------------------
# Helpers — construct mock unstructured elements
# ---------------------------------------------------------------------------


def _make_element(type_name: str, text: str, page_number: int | None = None) -> Any:
    """Return a minimal element whose ``type().__name__`` equals *type_name*.

    Using a real (non-mock) class ensures ``type(element).__name__`` returns
    the expected string, which is what the parser uses for element dispatch.
    """
    _Metadata = type("Metadata", (), {"page_number": page_number})
    _ElementCls = type(type_name, (), {})
    element = _ElementCls()
    element.text = text
    element.metadata = _Metadata()
    return element


# ---------------------------------------------------------------------------
# PDF parsing tests
# ---------------------------------------------------------------------------


class TestUnstructuredParserPDF:
    _MIME = "application/pdf"

    def test_parse_pdf_title_and_narrative(self) -> None:
        elements = [
            _make_element("Title", "Introduction", page_number=1),
            _make_element("NarrativeText", "This is the intro text.", page_number=1),
            _make_element("Title", "Background", page_number=2),
            _make_element("NarrativeText", "Some background info.", page_number=2),
        ]
        with patch(_PATCH_TARGET, return_value=elements):
            result = UnstructuredParser().parse(Path("doc.pdf"), self._MIME)

        assert result.parse_tier == "standard"
        assert result.sections is not None
        assert len(result.sections) == 2
        assert result.sections[0].heading == "Introduction"
        assert result.sections[0].content == "This is the intro text."
        assert result.sections[0].page_number == 1
        assert result.sections[1].heading == "Background"
        assert result.sections[1].page_number == 2

    def test_parse_pdf_list_items_accumulated_under_heading(self) -> None:
        elements = [
            _make_element("Title", "Key Points", page_number=1),
            _make_element("ListItem", "First point.", page_number=1),
            _make_element("ListItem", "Second point.", page_number=1),
        ]
        with patch(_PATCH_TARGET, return_value=elements):
            result = UnstructuredParser().parse(Path("list.pdf"), self._MIME)

        assert result.sections is not None
        assert len(result.sections) == 1
        section = result.sections[0]
        assert section.heading == "Key Points"
        assert "First point." in section.content
        assert "Second point." in section.content

    def test_parse_pdf_table_included_as_content(self) -> None:
        elements = [
            _make_element("Title", "Data", page_number=3),
            _make_element("Table", "Col A | Col B\n1 | 2", page_number=3),
        ]
        with patch(_PATCH_TARGET, return_value=elements):
            result = UnstructuredParser().parse(Path("table.pdf"), self._MIME)

        assert result.sections is not None
        section = result.sections[0]
        assert "Col A" in section.content

    def test_parse_pdf_no_heading_creates_anonymous_section(self) -> None:
        elements = [
            _make_element("NarrativeText", "Preamble text.", page_number=1),
            _make_element("NarrativeText", "More preamble.", page_number=1),
        ]
        with patch(_PATCH_TARGET, return_value=elements):
            result = UnstructuredParser().parse(Path("nohead.pdf"), self._MIME)

        assert result.sections is not None
        assert len(result.sections) == 1
        assert result.sections[0].heading is None
        assert "Preamble text." in result.sections[0].content

    def test_parse_pdf_skips_footer_and_page_break(self) -> None:
        elements = [
            _make_element("Title", "Section", page_number=1),
            _make_element("NarrativeText", "Body text.", page_number=1),
            _make_element("Footer", "Page 1", page_number=1),
            _make_element("PageBreak", "", page_number=1),
        ]
        with patch(_PATCH_TARGET, return_value=elements):
            result = UnstructuredParser().parse(Path("footer.pdf"), self._MIME)

        assert result.sections is not None
        assert len(result.sections) == 1
        assert "Page 1" not in result.sections[0].content

    def test_parse_pdf_empty_elements_returns_none_sections(self) -> None:
        with patch(_PATCH_TARGET, return_value=[]):
            result = UnstructuredParser().parse(Path("empty.pdf"), self._MIME)

        assert result.sections is None
        assert result.text == ""

    def test_parse_pdf_exception_raises_parse_error(self) -> None:
        with patch(
            _PATCH_TARGET,
            side_effect=Exception("corrupt"),
        ):
            with pytest.raises(ParseError, match="Unstructured failed to parse"):
                UnstructuredParser().parse(Path("bad.pdf"), self._MIME)

    def test_parse_pdf_full_text_joins_sections(self) -> None:
        elements = [
            _make_element("Title", "Sec 1", page_number=1),
            _make_element("NarrativeText", "Alpha.", page_number=1),
            _make_element("Title", "Sec 2", page_number=2),
            _make_element("NarrativeText", "Beta.", page_number=2),
        ]
        with patch(_PATCH_TARGET, return_value=elements):
            result = UnstructuredParser().parse(Path("multi.pdf"), self._MIME)

        assert "Alpha." in result.text
        assert "Beta." in result.text


# ---------------------------------------------------------------------------
# DOCX parsing tests
# ---------------------------------------------------------------------------


class TestUnstructuredParserDOCX:
    _MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    def test_parse_docx_sections_extracted(self) -> None:
        elements = [
            _make_element("Title", "Overview"),
            _make_element("NarrativeText", "Overview body."),
        ]
        with patch(_PATCH_TARGET, return_value=elements):
            result = UnstructuredParser().parse(Path("report.docx"), self._MIME)

        assert result.parse_tier == "standard"
        assert result.sections is not None
        assert result.sections[0].heading == "Overview"

    def test_parse_docx_exception_raises_parse_error(self) -> None:
        with patch(
            _PATCH_TARGET,
            side_effect=RuntimeError("bad docx"),
        ):
            with pytest.raises(ParseError, match="Unstructured failed to parse"):
                UnstructuredParser().parse(Path("broken.docx"), self._MIME)

    def test_parse_msword_mime_accepted(self) -> None:
        elements = [_make_element("NarrativeText", "Legacy doc.")]
        with patch(_PATCH_TARGET, return_value=elements):
            result = UnstructuredParser().parse(Path("old.doc"), "application/msword")

        assert result.parse_tier == "standard"


# ---------------------------------------------------------------------------
# Auto-detection (any MIME type accepted)
# ---------------------------------------------------------------------------


class TestUnstructuredParserAutoDetect:
    def test_text_plain_accepted(self) -> None:
        elements = [_make_element("NarrativeText", "Plain text content.")]
        with patch(_PATCH_TARGET, return_value=elements):
            result = UnstructuredParser().parse(Path("notes.txt"), "text/plain")
        assert result.parse_tier == "standard"

    def test_html_accepted(self) -> None:
        elements = [
            _make_element("Title", "Page Title"),
            _make_element("NarrativeText", "Body content."),
        ]
        with patch(_PATCH_TARGET, return_value=elements):
            result = UnstructuredParser().parse(Path("page.html"), "text/html")
        assert result.parse_tier == "standard"
        assert result.sections is not None
        assert result.sections[0].heading == "Page Title"

    def test_csv_accepted(self) -> None:
        elements = [_make_element("Table", "a,b,c\n1,2,3")]
        with patch(_PATCH_TARGET, return_value=elements):
            result = UnstructuredParser().parse(Path("data.csv"), "text/csv")
        assert result.parse_tier == "standard"
