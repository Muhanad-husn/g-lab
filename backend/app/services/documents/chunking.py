"""Text chunking service for document ingestion.

Implements a recursive character splitter that respects semantic boundaries
(paragraph → sentence → word) to produce overlapping chunks of approximately
``chunk_size`` tokens, preserving per-chunk metadata from the source section.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.logging import get_logger
from app.services.documents.parsers.base import ParseResult

logger: Any = get_logger(__name__)

# Ordered list of separators tried during recursive splitting.
# Splitting proceeds from coarsest to finest granularity.
_SEPARATORS = ["\n\n", "\n", ". ", "! ", "? ", " "]


@dataclass
class Chunk:
    """A single text chunk produced by :class:`ChunkingService`.

    Attributes:
        text:            The chunk's text content.
        index:           Zero-based position of this chunk across the whole document.
        page_number:     Source page (None for formats without page breaks, e.g. DOCX).
        section_heading: Heading of the source section, if available.
        parse_tier:      Parse tier inherited from the :class:`ParseResult`.
    """

    text: str
    index: int
    parse_tier: str
    page_number: int | None = None
    section_heading: str | None = None


class ChunkingService:
    """Split :class:`ParseResult` documents into overlapping text chunks.

    Usage::

        svc = ChunkingService()
        chunks = svc.chunk(parse_result, chunk_size=512, overlap=64)
        for chunk in chunks:
            print(chunk.index, chunk.text[:80])
    """

    def chunk(
        self,
        parse_result: ParseResult,
        chunk_size: int = 512,
        overlap: int = 64,
    ) -> list[Chunk]:
        """Split *parse_result* into overlapping chunks.

        Args:
            parse_result: Output of any parser tier.
            chunk_size:   Target maximum chunk size in whitespace-delimited tokens.
            overlap:      Number of tokens to repeat from the previous chunk
                          at the start of the next chunk.

        Returns:
            Ordered list of :class:`Chunk` objects.  Empty documents return ``[]``.
        """
        if not parse_result.text.strip():
            return []

        chunks: list[Chunk] = []
        chunk_index = 0

        if parse_result.sections:
            # Chunk each section independently to preserve metadata
            for section in parse_result.sections:
                if not section.content.strip():
                    continue
                texts = _split_text(section.content, chunk_size, overlap)
                for text in texts:
                    if text.strip():
                        chunks.append(
                            Chunk(
                                text=text,
                                index=chunk_index,
                                parse_tier=parse_result.parse_tier,
                                page_number=section.page_number,
                                section_heading=section.heading,
                            )
                        )
                        chunk_index += 1
        else:
            # No section structure — chunk the full text
            texts = _split_text(parse_result.text, chunk_size, overlap)
            for text in texts:
                if text.strip():
                    chunks.append(
                        Chunk(
                            text=text,
                            index=chunk_index,
                            parse_tier=parse_result.parse_tier,
                        )
                    )
                    chunk_index += 1

        logger.info(
            "chunking_done",
            parse_tier=parse_result.parse_tier,
            chunk_count=len(chunks),
            chunk_size=chunk_size,
            overlap=overlap,
        )
        return chunks


# ---------------------------------------------------------------------------
# Internal splitting helpers
# ---------------------------------------------------------------------------


def _token_count(text: str) -> int:
    """Approximate token count using whitespace splitting."""
    return len(text.split())


def _split_text(
    text: str,
    chunk_size: int,
    overlap: int,
    separators: list[str] | None = None,
) -> list[str]:
    """Recursively split *text* into chunks of at most *chunk_size* tokens.

    Tries separators in order (paragraph → newline → sentence → word).
    Falls back to hard word-boundary split if no separator is found.
    """
    if separators is None:
        separators = _SEPARATORS

    # Base case: text already fits in one chunk
    if _token_count(text) <= chunk_size:
        stripped = text.strip()
        return [stripped] if stripped else []

    # Try each separator in order
    for i, sep in enumerate(separators):
        if sep not in text:
            continue

        pieces = [p for p in text.split(sep) if p]
        if len(pieces) <= 1:
            continue

        remaining_seps = separators[i + 1 :]

        # Merge pieces into chunks respecting chunk_size / overlap
        raw_chunks = _merge_pieces(pieces, sep, chunk_size, overlap)

        # Recursively split any chunk that is still too large
        result: list[str] = []
        for raw in raw_chunks:
            if _token_count(raw) > chunk_size and remaining_seps:
                result.extend(_split_text(raw, chunk_size, overlap, remaining_seps))
            elif raw.strip():
                result.append(raw.strip())
        return result

    # No separator matched — hard split at word boundaries
    return _hard_word_split(text, chunk_size, overlap)


def _merge_pieces(
    pieces: list[str],
    separator: str,
    chunk_size: int,
    overlap: int,
) -> list[str]:
    """Greedily merge *pieces* into chunks not exceeding *chunk_size* tokens.

    When a chunk is emitted, the tail of that chunk (up to *overlap* tokens)
    is prepended to the next chunk.
    """
    chunks: list[str] = []
    current: list[str] = []
    current_tokens = 0

    for piece in pieces:
        piece_tokens = _token_count(piece)

        if current_tokens + piece_tokens > chunk_size and current:
            # Emit the current chunk
            chunk_text = separator.join(current)
            chunks.append(chunk_text)

            # Build overlap tail from the current chunk (word-level)
            overlap_tail = _tail_words(chunk_text, overlap)
            # Start the next chunk with overlap + current piece
            if overlap_tail:
                current = [overlap_tail, piece]
                current_tokens = _token_count(overlap_tail) + piece_tokens
            else:
                current = [piece]
                current_tokens = piece_tokens
        else:
            current.append(piece)
            current_tokens += piece_tokens

    if current:
        chunks.append(separator.join(current))

    return chunks


def _tail_words(text: str, n_tokens: int) -> str:
    """Return the last *n_tokens* words of *text* as a string."""
    words = text.split()
    tail = words[-n_tokens:] if n_tokens < len(words) else words
    return " ".join(tail)


def _hard_word_split(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Split *text* purely at word boundaries with a sliding window."""
    words = text.split()
    if not words:
        return []

    step = max(1, chunk_size - overlap)
    chunks: list[str] = []
    start = 0
    while start < len(words):
        end = min(start + chunk_size, len(words))
        chunk_text = " ".join(words[start:end])
        if chunk_text.strip():
            chunks.append(chunk_text)
        if end >= len(words):
            break
        start += step

    return chunks
