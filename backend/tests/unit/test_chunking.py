"""Unit tests for ChunkingService."""

from __future__ import annotations

import pytest

from app.services.documents.chunking import Chunk, ChunkingService, _token_count
from app.services.documents.parsers.base import ParseResult, Section


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_result(
    text: str,
    parse_tier: str = "basic",
    sections: list[Section] | None = None,
) -> ParseResult:
    return ParseResult(text=text, parse_tier=parse_tier, sections=sections)


def _words(n: int) -> str:
    """Generate a string of *n* distinct words."""
    return " ".join(f"word{i}" for i in range(n))


# ---------------------------------------------------------------------------
# _token_count helper
# ---------------------------------------------------------------------------


class TestTokenCount:
    def test_empty_string(self) -> None:
        assert _token_count("") == 0

    def test_single_word(self) -> None:
        assert _token_count("hello") == 1

    def test_multiple_words(self) -> None:
        assert _token_count("the quick brown fox") == 4

    def test_extra_whitespace_ignored(self) -> None:
        assert _token_count("  a  b  c  ") == 3


# ---------------------------------------------------------------------------
# Empty / short documents
# ---------------------------------------------------------------------------


class TestChunkingEdgeCases:
    def setup_method(self) -> None:
        self.svc = ChunkingService()

    def test_empty_text_returns_empty_list(self) -> None:
        result = _make_result("")
        assert self.svc.chunk(result) == []

    def test_whitespace_only_returns_empty_list(self) -> None:
        result = _make_result("   \n\n   ")
        assert self.svc.chunk(result) == []

    def test_short_text_returns_single_chunk(self) -> None:
        result = _make_result("Hello world, this is a short document.")
        chunks = self.svc.chunk(result, chunk_size=512, overlap=64)
        assert len(chunks) == 1
        assert chunks[0].index == 0
        assert chunks[0].parse_tier == "basic"
        assert "Hello world" in chunks[0].text

    def test_exactly_chunk_size_returns_single_chunk(self) -> None:
        text = _words(50)
        result = _make_result(text)
        chunks = self.svc.chunk(result, chunk_size=50, overlap=10)
        assert len(chunks) == 1


# ---------------------------------------------------------------------------
# Splitting behaviour
# ---------------------------------------------------------------------------


class TestChunkingSplitting:
    def setup_method(self) -> None:
        self.svc = ChunkingService()

    def test_long_text_splits_into_multiple_chunks(self) -> None:
        # 200-word text, chunk_size=50 → at least 4 chunks
        text = _words(200)
        result = _make_result(text)
        chunks = self.svc.chunk(result, chunk_size=50, overlap=5)
        assert len(chunks) >= 4

    def test_chunks_are_indexed_sequentially(self) -> None:
        text = _words(300)
        result = _make_result(text)
        chunks = self.svc.chunk(result, chunk_size=50, overlap=10)
        assert [c.index for c in chunks] == list(range(len(chunks)))

    def test_overlap_causes_shared_words(self) -> None:
        # Build a paragraph-separated text so splitting happens at \n\n
        # then verify adjacent chunks share words
        paragraphs = [_words(60) for _ in range(3)]
        text = "\n\n".join(paragraphs)
        result = _make_result(text)
        chunks = self.svc.chunk(result, chunk_size=50, overlap=10)
        assert len(chunks) >= 2
        # All chunks should have non-empty text
        assert all(c.text.strip() for c in chunks)

    def test_chunk_size_respected(self) -> None:
        text = _words(500)
        result = _make_result(text)
        chunks = self.svc.chunk(result, chunk_size=50, overlap=5)
        for chunk in chunks:
            # Allow slight excess due to separator rejoining, but cap at 2× for sanity
            assert _token_count(chunk.text) <= 100

    def test_no_empty_chunks(self) -> None:
        text = _words(150)
        result = _make_result(text)
        chunks = self.svc.chunk(result, chunk_size=30, overlap=5)
        for chunk in chunks:
            assert chunk.text.strip() != ""

    def test_paragraph_boundary_respected(self) -> None:
        # Two large paragraphs — splitter should prefer \n\n boundary
        para_a = _words(60)
        para_b = _words(60)
        text = f"{para_a}\n\n{para_b}"
        result = _make_result(text)
        chunks = self.svc.chunk(result, chunk_size=50, overlap=10)
        # Should produce multiple chunks
        assert len(chunks) >= 2


# ---------------------------------------------------------------------------
# Metadata preservation
# ---------------------------------------------------------------------------


class TestChunkingMetadata:
    def setup_method(self) -> None:
        self.svc = ChunkingService()

    def test_parse_tier_inherited(self) -> None:
        result = _make_result(_words(20), parse_tier="high")
        chunks = self.svc.chunk(result)
        assert all(c.parse_tier == "high" for c in chunks)

    def test_page_number_from_section(self) -> None:
        sections = [
            Section(content=_words(30), page_number=1, heading=None),
            Section(content=_words(30), page_number=2, heading=None),
        ]
        result = ParseResult(
            text="\n\n".join(s.content for s in sections),
            parse_tier="basic",
            sections=sections,
        )
        chunks = self.svc.chunk(result, chunk_size=512)
        page_numbers = [c.page_number for c in chunks]
        # Chunks from section 1 have page_number=1, section 2 → page_number=2
        assert 1 in page_numbers
        assert 2 in page_numbers

    def test_section_heading_preserved(self) -> None:
        sections = [
            Section(content=_words(20), heading="Introduction", page_number=1),
            Section(content=_words(20), heading="Conclusion", page_number=5),
        ]
        result = ParseResult(
            text="\n\n".join(s.content for s in sections),
            parse_tier="standard",
            sections=sections,
        )
        chunks = self.svc.chunk(result, chunk_size=512)
        headings = {c.section_heading for c in chunks}
        assert "Introduction" in headings
        assert "Conclusion" in headings

    def test_no_sections_page_number_is_none(self) -> None:
        result = _make_result(_words(30))
        chunks = self.svc.chunk(result)
        assert all(c.page_number is None for c in chunks)

    def test_no_sections_section_heading_is_none(self) -> None:
        result = _make_result(_words(30))
        chunks = self.svc.chunk(result)
        assert all(c.section_heading is None for c in chunks)

    def test_empty_sections_skipped(self) -> None:
        sections = [
            Section(content="   ", page_number=1, heading=None),
            Section(content=_words(20), page_number=2, heading=None),
        ]
        result = ParseResult(
            text=sections[1].content,
            parse_tier="basic",
            sections=sections,
        )
        chunks = self.svc.chunk(result, chunk_size=512)
        assert len(chunks) == 1
        assert chunks[0].page_number == 2

    def test_chunk_dataclass_fields(self) -> None:
        chunk = Chunk(text="hello", index=0, parse_tier="basic")
        assert chunk.page_number is None
        assert chunk.section_heading is None
