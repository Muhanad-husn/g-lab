"""Domain enumerations."""

from enum import StrEnum


class ActionType(StrEnum):
    """Types of actions tracked in the action log."""

    NODE_EXPAND = "node_expand"
    NODE_SEARCH = "node_search"
    PATH_DISCOVERY = "path_discovery"
    FILTER_APPLY = "filter_apply"
    FINDING_SAVE = "finding_save"
    FINDING_UPDATE = "finding_update"
    FINDING_DELETE = "finding_delete"
    SESSION_CREATE = "session_create"
    SESSION_RESET = "session_reset"
    SESSION_EXPORT = "session_export"
    SESSION_IMPORT = "session_import"
    RAW_QUERY = "raw_query"


class SessionStatus(StrEnum):
    """Session lifecycle states."""

    ACTIVE = "active"
    CLOSED = "closed"
