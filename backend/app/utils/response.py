"""API response envelope helpers.

Every endpoint returns the envelope shape defined in ARCHITECTURE.md §14.1.
"""

from typing import Any
from uuid import uuid4


def envelope(
    data: Any,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    """Wrap data in the standard success envelope.

    The ``duration_ms`` field is filled to 0 here and overwritten
    by the timing middleware in ``main.py``.
    """
    return {
        "data": data,
        "warnings": warnings or [],
        "meta": {
            "request_id": str(uuid4()),
            "duration_ms": 0,
        },
    }


def error_response(
    code: str,
    message: str,
    detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the standard error envelope."""
    body: dict[str, Any] = {
        "error": {
            "code": code,
            "message": message,
        },
        "meta": {
            "request_id": str(uuid4()),
        },
    }
    if detail is not None:
        body["error"]["detail"] = detail
    return body
