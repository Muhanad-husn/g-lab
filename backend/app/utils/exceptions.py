"""Domain-specific exceptions."""


class CypherValidationError(Exception):
    """Raised when a Cypher query fails sanitisation."""

    def __init__(self, message: str, query: str | None = None) -> None:
        self.query = query
        super().__init__(message)


class GuardrailExceededError(Exception):
    """Raised when a guardrail hard limit is exceeded."""

    def __init__(
        self,
        message: str,
        detail: dict[str, object] | None = None,
    ) -> None:
        self.detail = detail or {}
        super().__init__(message)


class Neo4jConnectionError(Exception):
    """Raised when Neo4j is unreachable or connection fails."""
