"""Unit tests for DoclingParser (Tier 1), fully mocked."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Inject stub top-level modules before the module under test is imported so
# it can be loaded without the real docling package installed.
# ---------------------------------------------------------------------------

if "docling" not in sys.modules:
    sys.modules["docling"] = MagicMock()
if "docling.document_converter" not in sys.modules:
    _conv_mod = MagicMock()
    sys.modules["docling.document_converter"] = _conv_mod

from app.services.documents.parsers.docling_parser import (  # noqa: E402
    DoclingParser,
    ParseError,
)


# ---------------------------------------------------------------------------
# Helpers — construct mock docling items and documents
# ---------------------------------------------------------------------------


def _prov(page_no: int | None = None) -> Any:
    """Return a minimal provenance stub."""
    p = MagicMock()
    p.page_no = page_no
    return p


def _item(label: str, text: str, page_no: int | None = None) -> Any:
    """Return a mock docling item with the given label and text."""
    obj = MagicMock()
    obj.label = label
    obj.text = text
    obj.prov = [_prov(page_no)] if page_no is not None else []
    obj.data = None
    return obj


def _doc(items: list[tuple[Any, int]]) -> Any:
    """Return a mock DoclingDocument whose iterate_items yields *items*."""
    doc = MagicMock()
    doc.iterate_items.return_value = items
    return doc


def _convert_result(doc: Any) -> Any:
    result = MagicMock()
    result.document = doc
    return result


# ---------------------------------------------------------------------------
# Tests — section extraction
# ---------------------------------------------------------------------------


class TestDoclingParserSections:
    _MIME = "application/pdf"

    def test_heading_and_text_produces_one_section(self) -> None:
        items = [
            (_item("section_header", "Introduction", page_no=1), 0),
            (_item("text", "Body of the introduction.", page_no=1), 1),
        ]
        doc = _doc(items)
        with patch(
            "docling.document_converter.DocumentConverter"
        ) as mock_cls:
            mock_cls.return_value.convert.return_value = _convert_result(doc)
            result = DoclingParser().parse(Path("doc.pdf"), self._MIME)

        assert result.parse_tier == "high"
        assert result.sections is not None
        assert len(result.sections) == 1
        assert result.sections[0].heading == "Introduction"
        assert result.sections[0].content == "Body of the introduction."
        assert result.sections[0].page_number == 1

    def test_multiple_headings_produce_multiple_sections(self) -> None:
        items = [
            (_item("section_header", "Chapter 1", page_no=1), 0),
            (_item("text", "Chapter 1 content.", page_no=1), 1),
            (_item("section_header", "Chapter 2", page_no=2), 0),
            (_item("text", "Chapter 2 content.", page_no=2), 1),
        ]
        doc = _doc(items)
        with patch("docling.document_converter.DocumentConverter") as mock_cls:
            mock_cls.return_value.convert.return_value = _convert_result(doc)
            result = DoclingParser().parse(Path("doc.pdf"), self._MIME)

        assert result.sections is not None
        assert len(result.sections) == 2
        assert result.sections[0].heading == "Chapter 1"
        assert result.sections[1].heading == "Chapter 2"
        assert result.sections[1].page_number == 2

    def test_title_label_acts_as_heading(self) -> None:
        items = [
            (_item("title", "Report Title", page_no=1), 0),
            (_item("text", "Executive summary.", page_no=1), 1),
        ]
        doc = _doc(items)
        with patch("docling.document_converter.DocumentConverter") as mock_cls:
            mock_cls.return_value.convert.return_value = _convert_result(doc)
            result = DoclingParser().parse(Path("doc.pdf"), self._MIME)

        assert result.sections is not None
        assert result.sections[0].heading == "Report Title"

    def test_list_items_accumulated_under_heading(self) -> None:
        items = [
            (_item("section_header", "Key Points", page_no=1), 0),
            (_item("list_item", "Point one.", page_no=1), 1),
            (_item("list_item", "Point two.", page_no=1), 1),
        ]
        doc = _doc(items)
        with patch("docling.document_converter.DocumentConverter") as mock_cls:
            mock_cls.return_value.convert.return_value = _convert_result(doc)
            result = DoclingParser().parse(Path("doc.pdf"), self._MIME)

        assert result.sections is not None
        assert len(result.sections) == 1
        assert "Point one." in result.sections[0].content
        assert "Point two." in result.sections[0].content

    def test_content_before_heading_creates_anonymous_section(self) -> None:
        items = [
            (_item("text", "Preamble before any heading.", page_no=1), 0),
        ]
        doc = _doc(items)
        with patch("docling.document_converter.DocumentConverter") as mock_cls:
            mock_cls.return_value.convert.return_value = _convert_result(doc)
            result = DoclingParser().parse(Path("doc.pdf"), self._MIME)

        assert result.sections is not None
        assert len(result.sections) == 1
        assert result.sections[0].heading is None
        assert "Preamble" in result.sections[0].content

    def test_skip_labels_excluded(self) -> None:
        items = [
            (_item("section_header", "Section", page_no=1), 0),
            (_item("text", "Real content.", page_no=1), 1),
            (_item("page_footer", "Page 1 of 10", page_no=1), 0),
            (_item("page_header", "CONFIDENTIAL", page_no=1), 0),
            (_item("picture", "image-data", page_no=1), 0),
        ]
        doc = _doc(items)
        with patch("docling.document_converter.DocumentConverter") as mock_cls:
            mock_cls.return_value.convert.return_value = _convert_result(doc)
            result = DoclingParser().parse(Path("doc.pdf"), self._MIME)

        assert result.sections is not None
        assert len(result.sections) == 1
        section_text = result.sections[0].content
        assert "Page 1 of 10" not in section_text
        assert "CONFIDENTIAL" not in section_text

    def test_empty_document_returns_none_sections(self) -> None:
        doc = _doc([])
        with patch("docling.document_converter.DocumentConverter") as mock_cls:
            mock_cls.return_value.convert.return_value = _convert_result(doc)
            result = DoclingParser().parse(Path("empty.pdf"), self._MIME)

        assert result.sections is None
        assert result.text == ""

    def test_full_text_joins_all_sections(self) -> None:
        items = [
            (_item("section_header", "A", page_no=1), 0),
            (_item("text", "Alpha content.", page_no=1), 1),
            (_item("section_header", "B", page_no=2), 0),
            (_item("text", "Beta content.", page_no=2), 1),
        ]
        doc = _doc(items)
        with patch("docling.document_converter.DocumentConverter") as mock_cls:
            mock_cls.return_value.convert.return_value = _convert_result(doc)
            result = DoclingParser().parse(Path("doc.pdf"), self._MIME)

        assert "Alpha content." in result.text
        assert "Beta content." in result.text

    def test_table_with_data_export_used_as_content(self) -> None:
        table_item = MagicMock()
        table_item.label = "table"
        table_item.text = ""  # tables may have empty .text
        table_item.prov = [_prov(3)]
        table_item.data = MagicMock()
        table_item.data.export_to_markdown.return_value = "| A | B |\n| 1 | 2 |"

        items = [
            (_item("section_header", "Data", page_no=3), 0),
            (table_item, 1),
        ]
        doc = _doc(items)
        with patch("docling.document_converter.DocumentConverter") as mock_cls:
            mock_cls.return_value.convert.return_value = _convert_result(doc)
            result = DoclingParser().parse(Path("doc.pdf"), self._MIME)

        assert result.sections is not None
        assert "| A | B |" in result.sections[0].content

    def test_docx_mime_type_accepted(self) -> None:
        items = [(_item("text", "DOCX content.", page_no=None), 0)]
        doc = _doc(items)
        with patch("docling.document_converter.DocumentConverter") as mock_cls:
            mock_cls.return_value.convert.return_value = _convert_result(doc)
            result = DoclingParser().parse(
                Path("doc.docx"),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        assert result.parse_tier == "high"


# ---------------------------------------------------------------------------
# Tests — error handling
# ---------------------------------------------------------------------------


class TestDoclingParserErrors:
    _MIME = "application/pdf"

    def test_docling_import_error_raises_parse_error(self) -> None:
        with patch.dict(sys.modules, {"docling.document_converter": None}):
            with pytest.raises(ParseError, match="docling is not installed"):
                DoclingParser().parse(Path("doc.pdf"), self._MIME)

    def test_converter_exception_raises_parse_error(self) -> None:
        with patch("docling.document_converter.DocumentConverter") as mock_cls:
            mock_cls.return_value.convert.side_effect = RuntimeError("corrupt file")
            with pytest.raises(ParseError, match="Docling failed to parse"):
                DoclingParser().parse(Path("bad.pdf"), self._MIME)
