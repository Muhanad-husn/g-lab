"""Unit tests for Neo4jService helpers (no live driver required)."""

from __future__ import annotations

from app.services.neo4j_service import (
    Neo4jService,
    _escape_label,
    _escape_regex,
    _record_to_edge,
    _record_to_node,
)

# ---------------------------------------------------------------------------
# Mock neo4j primitives
# ---------------------------------------------------------------------------


class _MockNode:
    """Minimal neo4j Node stand-in: supports dict() via keys()+__getitem__."""

    def __init__(
        self,
        element_id: str,
        labels: set[str],
        properties: dict[str, object],
    ) -> None:
        self.element_id = element_id
        self.labels = labels
        self._props = properties

    def keys(self) -> object:
        return self._props.keys()

    def __getitem__(self, key: str) -> object:
        return self._props[key]

    def __iter__(self) -> object:
        return iter(self._props)


class _MockStartNode:
    def __init__(self, element_id: str) -> None:
        self.element_id = element_id


class _MockRel:
    """Minimal neo4j Relationship stand-in."""

    def __init__(
        self,
        element_id: str,
        rel_type: str,
        start_id: str,
        end_id: str,
        properties: dict[str, object],
    ) -> None:
        self.element_id = element_id
        self.type = rel_type
        self.start_node = _MockStartNode(start_id)
        self.end_node = _MockStartNode(end_id)
        self._props = properties

    def keys(self) -> object:
        return self._props.keys()

    def __getitem__(self, key: str) -> object:
        return self._props[key]

    def __iter__(self) -> object:
        return iter(self._props)


# ---------------------------------------------------------------------------
# _escape_label
# ---------------------------------------------------------------------------


class TestEscapeLabel:
    def test_plain_label_unchanged(self) -> None:
        assert _escape_label("Person") == "Person"

    def test_label_with_spaces_unchanged(self) -> None:
        # spaces are valid in labels; only backticks need escaping
        assert _escape_label("My Label") == "My Label"

    def test_single_backtick_escaped(self) -> None:
        assert _escape_label("My`Label") == "My``Label"

    def test_multiple_backticks_escaped(self) -> None:
        assert _escape_label("A`B`C") == "A``B``C"

    def test_leading_backtick(self) -> None:
        assert _escape_label("`Evil") == "``Evil"

    def test_empty_string_passthrough(self) -> None:
        assert _escape_label("") == ""


# ---------------------------------------------------------------------------
# _escape_regex
# ---------------------------------------------------------------------------


class TestEscapeRegex:
    def test_plain_word_unchanged(self) -> None:
        assert _escape_regex("Alice") == "Alice"

    def test_dot_escaped(self) -> None:
        assert _escape_regex("a.b") == "a\\.b"

    def test_backslash_escaped(self) -> None:
        assert _escape_regex("a\\b") == "a\\\\b"

    def test_brackets_escaped(self) -> None:
        assert _escape_regex("[test]") == "\\[test\\]"

    def test_parens_escaped(self) -> None:
        assert _escape_regex("(foo)") == "\\(foo\\)"

    def test_caret_escaped(self) -> None:
        assert _escape_regex("^start") == "\\^start"

    def test_pipe_escaped(self) -> None:
        assert _escape_regex("a|b") == "a\\|b"

    def test_combined_special_chars(self) -> None:
        result = _escape_regex("a.b(c)")
        assert result == "a\\.b\\(c\\)"

    def test_empty_string(self) -> None:
        assert _escape_regex("") == ""


# ---------------------------------------------------------------------------
# _record_to_node
# ---------------------------------------------------------------------------


class TestRecordToNode:
    def test_basic_node(self) -> None:
        node = _MockNode("4:abc:1", {"Person"}, {"name": "Alice", "age": 30})
        result = _record_to_node(node)
        assert result["id"] == "4:abc:1"
        assert result["labels"] == ["Person"]
        assert result["properties"] == {"name": "Alice", "age": 30}

    def test_multiple_labels(self) -> None:
        node = _MockNode("4:abc:2", {"Person", "Employee"}, {})
        result = _record_to_node(node)
        assert set(result["labels"]) == {"Person", "Employee"}

    def test_empty_properties(self) -> None:
        node = _MockNode("4:abc:3", {"Company"}, {})
        result = _record_to_node(node)
        assert result["properties"] == {}

    def test_element_id_is_string(self) -> None:
        node = _MockNode("4:xyz:99", {"Address"}, {"street": "Main St"})
        result = _record_to_node(node)
        assert isinstance(result["id"], str)

    def test_nested_property_preserved(self) -> None:
        node = _MockNode("4:abc:4", {"Event"}, {"tags": ["a", "b"]})
        result = _record_to_node(node)
        assert result["properties"]["tags"] == ["a", "b"]


# ---------------------------------------------------------------------------
# _record_to_edge
# ---------------------------------------------------------------------------


class TestRecordToEdge:
    def test_basic_edge(self) -> None:
        rel = _MockRel("5:abc:1", "KNOWS", "4:abc:1", "4:abc:2", {"since": 2020})
        result = _record_to_edge(rel)
        assert result["id"] == "5:abc:1"
        assert result["type"] == "KNOWS"
        assert result["source"] == "4:abc:1"
        assert result["target"] == "4:abc:2"
        assert result["properties"] == {"since": 2020}

    def test_empty_properties(self) -> None:
        rel = _MockRel("5:abc:2", "WORKS_AT", "4:abc:1", "4:abc:3", {})
        result = _record_to_edge(rel)
        assert result["properties"] == {}

    def test_element_id_preserved(self) -> None:
        rel = _MockRel("5:xyz:999", "OWNS", "4:abc:5", "4:abc:6", {})
        result = _record_to_edge(rel)
        assert result["id"] == "5:xyz:999"

    def test_source_target_are_strings(self) -> None:
        rel = _MockRel("5:abc:3", "LOCATED_AT", "4:abc:1", "4:abc:2", {})
        result = _record_to_edge(rel)
        assert isinstance(result["source"], str)
        assert isinstance(result["target"], str)


# ---------------------------------------------------------------------------
# Neo4jService lifecycle (no driver)
# ---------------------------------------------------------------------------


class TestNeo4jServiceLifecycle:
    def test_not_connected_initially(self) -> None:
        svc = Neo4jService()
        assert svc.is_connected() is False

    def test_close_when_not_connected_is_safe(self) -> None:
        import asyncio

        svc = Neo4jService()
        # Should not raise even if never connected
        asyncio.get_event_loop().run_until_complete(svc.close())
        assert svc.is_connected() is False
