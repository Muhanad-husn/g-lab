"""Tests for the Cypher sanitiser allowlist."""

import pytest

from app.utils.cypher import CypherSanitiser
from app.utils.exceptions import CypherValidationError

sanitiser = CypherSanitiser()


# ── Valid read queries ────────────────────────────────────────────


class TestValidReads:
    """Queries that should pass sanitisation."""

    def test_simple_match_return(self) -> None:
        result = sanitiser.sanitise("MATCH (n) RETURN n")
        assert "MATCH" in result

    def test_match_with_where(self) -> None:
        q = "MATCH (n:Person) WHERE n.name = 'Alice' RETURN n"
        result = sanitiser.sanitise(q)
        assert "WHERE" in result

    def test_optional_match(self) -> None:
        q = (
            "MATCH (n:Person) "
            "OPTIONAL MATCH (n)-[r]->(m) "
            "RETURN n, r, m"
        )
        result = sanitiser.sanitise(q)
        assert "OPTIONAL MATCH" in result

    def test_with_clause(self) -> None:
        q = (
            "MATCH (n) "
            "WITH n, count(*) AS cnt "
            "RETURN n, cnt"
        )
        result = sanitiser.sanitise(q)
        assert "WITH" in result

    def test_order_by_limit_skip(self) -> None:
        q = (
            "MATCH (n) "
            "RETURN n "
            "ORDER BY n.name "
            "SKIP 10 "
            "LIMIT 25"
        )
        result = sanitiser.sanitise(q)
        assert "LIMIT" in result

    def test_unwind(self) -> None:
        q = "UNWIND [1, 2, 3] AS x RETURN x"
        result = sanitiser.sanitise(q)
        assert "UNWIND" in result

    def test_shortest_path(self) -> None:
        q = (
            "MATCH p = shortestPath("
            "(a:Person)-[*..5]-(b:Person)"
            ") RETURN p"
        )
        result = sanitiser.sanitise(q)
        assert "shortestPath" in result

    def test_all_shortest_paths(self) -> None:
        q = (
            "MATCH p = allShortestPaths("
            "(a:Person)-[*..5]-(b:Person)"
            ") RETURN p"
        )
        result = sanitiser.sanitise(q)
        assert "allShortestPaths" in result

    def test_call_db_labels(self) -> None:
        q = "CALL db.labels()"
        result = sanitiser.sanitise(q)
        assert "db.labels" in result

    def test_call_db_relationship_types(self) -> None:
        q = "CALL db.relationshipTypes()"
        result = sanitiser.sanitise(q)
        assert "db.relationshipTypes" in result

    def test_call_db_property_keys(self) -> None:
        q = "CALL db.propertyKeys()"
        result = sanitiser.sanitise(q)
        assert "db.propertyKeys" in result

    def test_match_with_relationship_type(self) -> None:
        q = "MATCH (n)-[r:KNOWS]->(m) RETURN n, r, m"
        result = sanitiser.sanitise(q)
        assert "KNOWS" in result

    def test_contains_predicate(self) -> None:
        q = (
            "MATCH (n:Person) "
            "WHERE n.name CONTAINS 'Ali' "
            "RETURN n"
        )
        result = sanitiser.sanitise(q)
        assert "CONTAINS" in result

    def test_starts_with_predicate(self) -> None:
        q = (
            "MATCH (n:Person) "
            "WHERE n.name STARTS WITH 'A' "
            "RETURN n"
        )
        result = sanitiser.sanitise(q)
        assert "STARTS WITH" in result

    def test_count_aggregate(self) -> None:
        q = "MATCH (n) RETURN count(n)"
        result = sanitiser.sanitise(q)
        assert "count" in result

    def test_distinct(self) -> None:
        q = "MATCH (n) RETURN DISTINCT n.name"
        result = sanitiser.sanitise(q)
        assert "DISTINCT" in result

    def test_variable_length_path(self) -> None:
        q = "MATCH (a)-[*1..3]->(b) RETURN a, b"
        result = sanitiser.sanitise(q)
        assert result

    def test_multiline_query(self) -> None:
        q = """
        MATCH (n:Person)
        WHERE n.age > 30
        RETURN n.name, n.age
        ORDER BY n.age DESC
        LIMIT 10
        """
        result = sanitiser.sanitise(q)
        assert "MATCH" in result


# ── Write operations rejected ─────────────────────────────────────


class TestWriteRejection:
    """Write operations must be rejected."""

    def test_create_rejected(self) -> None:
        with pytest.raises(CypherValidationError, match="CREATE"):
            sanitiser.sanitise("CREATE (n:Person {name: 'Eve'})")

    def test_merge_rejected(self) -> None:
        with pytest.raises(CypherValidationError, match="MERGE"):
            sanitiser.sanitise(
                "MERGE (n:Person {name: 'Eve'})"
            )

    def test_set_rejected(self) -> None:
        with pytest.raises(CypherValidationError, match="SET"):
            sanitiser.sanitise(
                "MATCH (n) SET n.name = 'Evil'"
            )

    def test_delete_rejected(self) -> None:
        with pytest.raises(CypherValidationError, match="DELETE"):
            sanitiser.sanitise("MATCH (n) DELETE n")

    def test_detach_delete_rejected(self) -> None:
        with pytest.raises(CypherValidationError, match="DETACH"):
            sanitiser.sanitise("MATCH (n) DETACH DELETE n")

    def test_remove_rejected(self) -> None:
        with pytest.raises(CypherValidationError, match="REMOVE"):
            sanitiser.sanitise("MATCH (n) REMOVE n.name")

    def test_drop_rejected(self) -> None:
        with pytest.raises(CypherValidationError, match="DROP"):
            sanitiser.sanitise("DROP INDEX my_index")

    def test_foreach_rejected(self) -> None:
        with pytest.raises(CypherValidationError, match="FOREACH"):
            sanitiser.sanitise(
                "MATCH p=(a)-[*]->(b) "
                "FOREACH (n IN nodes(p) | SET n.marked = true)"
            )

    def test_load_csv_rejected(self) -> None:
        with pytest.raises(CypherValidationError, match="LOAD"):
            sanitiser.sanitise(
                "LOAD CSV FROM 'file:///data.csv' AS row "
                "CREATE (n {id: row[0]})"
            )


# ── Case insensitivity ────────────────────────────────────────────


class TestCaseInsensitive:
    """Forbidden keywords are caught regardless of casing."""

    def test_lowercase_create(self) -> None:
        with pytest.raises(CypherValidationError):
            sanitiser.sanitise("create (n:Person)")

    def test_mixed_case_merge(self) -> None:
        with pytest.raises(CypherValidationError):
            sanitiser.sanitise("MeRgE (n:Person)")

    def test_uppercase_delete(self) -> None:
        with pytest.raises(CypherValidationError):
            sanitiser.sanitise("MATCH (n) DELETE n")

    def test_lowercase_set(self) -> None:
        with pytest.raises(CypherValidationError):
            sanitiser.sanitise("MATCH (n) set n.x = 1")


# ── Injection attempts ────────────────────────────────────────────


class TestInjectionPrevention:
    """Common Cypher injection patterns are blocked."""

    def test_semicolon_chaining(self) -> None:
        with pytest.raises(CypherValidationError, match="Semicolon"):
            sanitiser.sanitise(
                "MATCH (n) RETURN n; CREATE (m:Evil)"
            )

    def test_semicolon_only(self) -> None:
        with pytest.raises(CypherValidationError, match="Semicolon"):
            sanitiser.sanitise("MATCH (n) RETURN n;")

    def test_comment_hiding_single_line(self) -> None:
        # The comment is stripped, but CREATE remains visible.
        with pytest.raises(CypherValidationError, match="CREATE"):
            sanitiser.sanitise(
                "MATCH (n) RETURN n // ignore\n"
                "CREATE (m:Evil)"
            )

    def test_comment_hiding_block(self) -> None:
        with pytest.raises(CypherValidationError, match="CREATE"):
            sanitiser.sanitise(
                "MATCH (n) /* comment */ CREATE (m:Evil)"
            )

    def test_call_subquery_rejected(self) -> None:
        with pytest.raises(
            CypherValidationError, match="CALL.*subquer"
        ):
            sanitiser.sanitise(
                "CALL { CREATE (n:Evil) } IN TRANSACTIONS"
            )

    def test_unapproved_procedure_rejected(self) -> None:
        with pytest.raises(
            CypherValidationError, match="not allowed"
        ):
            sanitiser.sanitise("CALL apoc.util.validate(true, 'x')")

    def test_comments_stripped_from_output(self) -> None:
        q = "MATCH (n) // comment\nRETURN n"
        result = sanitiser.sanitise(q)
        assert "//" not in result

    def test_block_comment_stripped(self) -> None:
        q = "MATCH (n) /* block */ RETURN n"
        result = sanitiser.sanitise(q)
        assert "/*" not in result

    def test_write_hidden_after_comment(self) -> None:
        """Even if a write keyword is after a comment on a new line."""
        with pytest.raises(CypherValidationError):
            sanitiser.sanitise(
                "MATCH (n) RETURN n //\nDELETE n"
            )


# ── Edge cases ────────────────────────────────────────────────────


class TestEdgeCases:
    """Boundary and edge-case inputs."""

    def test_empty_string_rejected(self) -> None:
        with pytest.raises(CypherValidationError, match="Empty"):
            sanitiser.sanitise("")

    def test_whitespace_only_rejected(self) -> None:
        with pytest.raises(CypherValidationError, match="Empty"):
            sanitiser.sanitise("   \n\t  ")

    def test_result_is_stripped(self) -> None:
        result = sanitiser.sanitise("  MATCH (n) RETURN n  ")
        assert result == "MATCH (n) RETURN n"

    def test_preserves_string_literals(self) -> None:
        q = "MATCH (n) WHERE n.name = 'Bob' RETURN n"
        result = sanitiser.sanitise(q)
        assert "'Bob'" in result

    def test_call_db_with_yield(self) -> None:
        q = "CALL db.labels() YIELD label RETURN label"
        result = sanitiser.sanitise(q)
        assert "label" in result
