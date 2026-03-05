"""Document parsers — tiered parse pipeline.

Tier 1 (high):     DoclingParser — structural extraction.
Tier 2 (standard): UnstructuredParser — general-purpose element extraction.
Tier 3 (basic):    RawParser — plain text via PyPDF2 / python-docx.
"""
