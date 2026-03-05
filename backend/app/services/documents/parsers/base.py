"""Base dataclasses shared by all document parsers."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Section:
    """A logical section of a parsed document."""

    content: str
    heading: str | None = None
    page_number: int | None = None


@dataclass
class ParseResult:
    """Output produced by any parser tier.

    Attributes:
        text:       Full plain-text content of the document (all sections joined).
        sections:   Structured sections if the parser could extract them, else None.
        parse_tier: One of ``"high"``, ``"standard"``, or ``"basic"``.
    """

    text: str
    parse_tier: str
    sections: list[Section] | None = field(default=None)
