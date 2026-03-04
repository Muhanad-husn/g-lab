"""Cypher query sanitiser using an allowlist approach.

Only read-only Cypher passes. Write clauses, destructive operations,
and comment injection are rejected. See backend/CLAUDE.md for the
full allowlist.
"""

from __future__ import annotations

import re

from app.utils.exceptions import CypherValidationError

# --- Allowed clause keywords (case-insensitive) ---
# Each entry is matched as a whole-word boundary at the start of a clause.
_ALLOWED_CLAUSES: set[str] = {
    "MATCH",
    "OPTIONAL MATCH",
    "RETURN",
    "WHERE",
    "WITH",
    "ORDER BY",
    "LIMIT",
    "SKIP",
    "UNWIND",
    "AS",
    "AND",
    "OR",
    "NOT",
    "IN",
    "IS",
    "NULL",
    "TRUE",
    "FALSE",
    "CONTAINS",
    "STARTS WITH",
    "ENDS WITH",
    "EXISTS",
    "CASE",
    "WHEN",
    "THEN",
    "ELSE",
    "END",
    "DISTINCT",
    "COUNT",
    "COLLECT",
    "ASC",
    "DESC",
    "BY",
}

# Allowed CALL procedures (prefix match).
_ALLOWED_CALL_PREFIXES: tuple[str, ...] = ("db.",)

# Allowed path functions.
_ALLOWED_FUNCTIONS: set[str] = {"SHORTESTPATH", "ALLSHORTESTPATHS"}

# --- Forbidden patterns (case-insensitive) ---
_FORBIDDEN_KEYWORDS: set[str] = {
    "CREATE",
    "MERGE",
    "SET",
    "DELETE",
    "DETACH",
    "REMOVE",
    "DROP",
    "FOREACH",
    "LOAD",
    "CSV",
}

# Matches standalone CALL { ... } (subquery syntax) — NOT "CALL db.labels()".
_CALL_SUBQUERY_RE = re.compile(r"\bCALL\s*\{", re.IGNORECASE)

# Single-line (//) and multi-line (/* */) comments.
_LINE_COMMENT_RE = re.compile(r"//.*$", re.MULTILINE)
_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)

# Semicolons (query chaining / injection).
_SEMICOLON_RE = re.compile(r";")

# Detects "CALL <procedure>" (allowed) vs bare CALL.
_CALL_PROCEDURE_RE = re.compile(r"\bCALL\s+([\w.]+)", re.IGNORECASE)

# Matches forbidden keywords as whole words.
_FORBIDDEN_RE = re.compile(
    r"\b(" + "|".join(_FORBIDDEN_KEYWORDS) + r")\b",
    re.IGNORECASE,
)


class CypherSanitiser:
    """Validates that a Cypher query is read-only.

    Usage::

        sanitiser = CypherSanitiser()
        clean = sanitiser.sanitise("MATCH (n) RETURN n")
    """

    def sanitise(self, query: str) -> str:
        """Validate and return the query, or raise on violation.

        Returns the query with comments stripped.

        Raises:
            CypherValidationError: If the query contains forbidden clauses.
        """
        if not query or not query.strip():
            raise CypherValidationError("Empty query", query=query)

        cleaned = self._strip_comments(query)

        self._reject_semicolons(cleaned, query)
        self._reject_call_subqueries(cleaned, query)
        self._reject_forbidden_keywords(cleaned, query)
        self._validate_call_procedures(cleaned, query)

        return cleaned.strip()

    # ------------------------------------------------------------------
    # Internal checks
    # ------------------------------------------------------------------

    @staticmethod
    def _strip_comments(query: str) -> str:
        """Remove single-line and block comments."""
        result = _BLOCK_COMMENT_RE.sub(" ", query)
        result = _LINE_COMMENT_RE.sub(" ", result)
        return result

    @staticmethod
    def _reject_semicolons(cleaned: str, original: str) -> None:
        if _SEMICOLON_RE.search(cleaned):
            raise CypherValidationError(
                "Semicolons are not allowed",
                query=original,
            )

    @staticmethod
    def _reject_call_subqueries(cleaned: str, original: str) -> None:
        if _CALL_SUBQUERY_RE.search(cleaned):
            raise CypherValidationError(
                "CALL {} subqueries are not allowed",
                query=original,
            )

    @staticmethod
    def _reject_forbidden_keywords(cleaned: str, original: str) -> None:
        match = _FORBIDDEN_RE.search(cleaned)
        if match:
            keyword = match.group(1).upper()
            raise CypherValidationError(
                f"Forbidden keyword: {keyword}",
                query=original,
            )

    @staticmethod
    def _validate_call_procedures(cleaned: str, original: str) -> None:
        """Ensure CALL is only used with allowed procedure prefixes."""
        for m in _CALL_PROCEDURE_RE.finditer(cleaned):
            procedure = m.group(1)
            if not any(
                procedure.lower().startswith(prefix)
                for prefix in _ALLOWED_CALL_PREFIXES
            ):
                raise CypherValidationError(
                    f"Procedure not allowed: {procedure}",
                    query=original,
                )
