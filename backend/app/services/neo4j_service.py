"""Neo4j read-only service layer.

Manages driver lifecycle, schema introspection, and all graph queries.
Every query uses execute_read() — no writes are ever performed.
Element IDs are opaque strings; never parsed or cast.
"""

from __future__ import annotations

import asyncio
from typing import Any

from neo4j import AsyncDriver, AsyncGraphDatabase
from neo4j.exceptions import (
    Neo4jError,
    ServiceUnavailable,
    SessionExpired,
)
from neo4j.graph import Node, Path, Relationship
from neo4j.time import Date, DateTime, Duration, Time

from app.core.logging import get_logger
from app.utils.cypher import CypherSanitiser
from app.utils.exceptions import Neo4jConnectionError

logger: Any = get_logger(__name__)

_MAX_RETRIES = 5
_INITIAL_BACKOFF = 1.0  # seconds
_MAX_BACKOFF = 30.0
_POOL_SIZE = 10
_SCHEMA_TIMEOUT_MS = 10_000
_DEFAULT_TIMEOUT_MS = 30_000


class Neo4jService:
    """Async Neo4j read-only service."""

    def __init__(self) -> None:
        self._driver: AsyncDriver | None = None
        self._sanitiser = CypherSanitiser()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(
        self,
        uri: str,
        user: str,
        password: str,
    ) -> None:
        """Connect to Neo4j with retry (5 attempts, exp backoff, 30s max).

        Raises Neo4jConnectionError if all retries fail.
        """
        backoff = _INITIAL_BACKOFF
        last_err: BaseException | None = None

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                driver = AsyncGraphDatabase.driver(
                    uri,
                    auth=(user, password),
                    max_connection_pool_size=_POOL_SIZE,
                )
                await driver.verify_connectivity()
                self._driver = driver
                logger.info(
                    "neo4j_connected",
                    uri=uri,
                    attempt=attempt,
                )
                return
            except (
                ServiceUnavailable,
                SessionExpired,
                OSError,
            ) as exc:
                last_err = exc
                logger.warning(
                    "neo4j_connect_retry",
                    attempt=attempt,
                    backoff=backoff,
                    error=str(exc),
                )
                if attempt < _MAX_RETRIES:
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, _MAX_BACKOFF)

        raise Neo4jConnectionError(
            f"Failed to connect after {_MAX_RETRIES} attempts: {last_err}"
        )

    async def close(self) -> None:
        """Close the driver and release all connections."""
        if self._driver is not None:
            await self._driver.close()
            self._driver = None
            logger.info("neo4j_disconnected")

    def is_connected(self) -> bool:
        """Return True if the driver is initialised."""
        return self._driver is not None

    # ------------------------------------------------------------------
    # Schema introspection
    # ------------------------------------------------------------------

    async def get_schema(self) -> dict[str, Any]:
        """Return labels and relationship types with counts.

        Counts are fetched concurrently. Timed-out counts become None.
        Returns dict matching SchemaResponse shape.
        """
        self._require_driver()

        labels_task = self._fetch_labels()
        rel_types_task = self._fetch_rel_types()

        labels, rel_types = await asyncio.gather(labels_task, rel_types_task)
        return {"labels": labels, "relationship_types": rel_types}

    async def get_samples(self, label: str, limit: int = 5) -> list[dict[str, Any]]:
        """Return sample nodes for a given label."""
        self._require_driver()
        assert self._driver is not None

        query = f"MATCH (n:`{_escape_label(label)}`) RETURN n LIMIT $limit"
        async with self._driver.session(
            default_access_mode="READ",
        ) as session:
            result = await session.execute_read(
                _run_query,
                query,
                {"limit": limit},
                _SCHEMA_TIMEOUT_MS,
            )
        return [_record_to_node(r["n"]) for r in result]

    async def get_relationship_samples(
        self, rel_type: str, limit: int = 5
    ) -> list[dict[str, Any]]:
        """Return sample relationships of a given type."""
        self._require_driver()
        assert self._driver is not None

        query = (
            f"MATCH (a)-[r:`{_escape_label(rel_type)}`]->(b) "
            f"RETURN a, r, b LIMIT $limit"
        )
        async with self._driver.session(
            default_access_mode="READ",
        ) as session:
            result = await session.execute_read(
                _run_query,
                query,
                {"limit": limit},
                _SCHEMA_TIMEOUT_MS,
            )
        samples = []
        for record in result:
            samples.append(
                {
                    "source": _record_to_node(record["a"]),
                    "relationship": _record_to_edge(record["r"]),
                    "target": _record_to_node(record["b"]),
                }
            )
        return samples

    async def get_overview(self) -> dict[str, Any]:
        """Return schema + top 5 central nodes by degree.

        Returns dict matching GraphOverview shape.
        """
        self._require_driver()
        assert self._driver is not None

        schema = await self.get_schema()

        cypher = (
            "MATCH (n) "
            "RETURN elementId(n) AS id, labels(n) AS labels, "
            "properties(n) AS props, "
            "size([(n)--() | 1]) AS degree "
            "ORDER BY degree DESC LIMIT 5"
        )
        async with self._driver.session(
            default_access_mode="READ",
        ) as session:
            try:
                result = await session.execute_read(
                    _run_query, cypher, {}, _SCHEMA_TIMEOUT_MS
                )
            except (Neo4jError, TimeoutError):
                result = []

        central_nodes = []
        for r in result:
            central_nodes.append(
                {
                    "id": r["id"],
                    "labels": r["labels"],
                    "properties": _sanitize_props(r["props"]),
                    "degree": r["degree"],
                }
            )

        return {"schema": schema, "central_nodes": central_nodes}

    # ------------------------------------------------------------------
    # Query operations
    # ------------------------------------------------------------------

    async def search(
        self,
        query: str,
        labels: list[str] | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Case-insensitive search across node properties."""
        self._require_driver()
        assert self._driver is not None

        label_filter = ""
        if labels:
            label_filter = ":" + ":".join(f"`{_escape_label(lbl)}`" for lbl in labels)

        cypher = (
            f"MATCH (n{label_filter}) "
            f"WHERE any(key IN keys(n) WHERE "
            f"toString(n[key]) =~ $pattern) "
            f"RETURN n LIMIT $limit"
        )
        pattern = f"(?i).*{_escape_regex(query)}.*"

        async with self._driver.session(
            default_access_mode="READ",
        ) as session:
            result = await session.execute_read(
                _run_query,
                cypher,
                {"pattern": pattern, "limit": limit},
                _DEFAULT_TIMEOUT_MS,
            )
        return [_record_to_node(r["n"]) for r in result]

    async def expand(
        self,
        node_ids: list[str],
        rel_types: list[str] | None,
        hops: int,
        limit: int,
        timeout_ms: int = _DEFAULT_TIMEOUT_MS,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Expand from nodes by following relationships.

        Returns (nodes, edges) tuple.
        """
        self._require_driver()
        assert self._driver is not None

        rel_filter = ""
        if rel_types:
            types = "|".join(f"`{_escape_label(t)}`" for t in rel_types)
            rel_filter = f":{types}"

        cypher = (
            f"MATCH (start) WHERE elementId(start) IN $node_ids "
            f"MATCH path = (start)-[r{rel_filter}*1..{hops}]-(end) "
            f"UNWIND relationships(path) AS rel "
            f"WITH DISTINCT rel, startNode(rel) AS sn, "
            f"endNode(rel) AS en "
            f"RETURN sn, rel, en "
            f"LIMIT $limit"
        )

        async with self._driver.session(
            default_access_mode="READ",
        ) as session:
            result = await session.execute_read(
                _run_query,
                cypher,
                {"node_ids": node_ids, "limit": limit},
                timeout_ms,
            )

        nodes_map: dict[str, dict[str, Any]] = {}
        edges_map: dict[str, dict[str, Any]] = {}

        for record in result:
            sn = _record_to_node(record["sn"])
            en = _record_to_node(record["en"])
            edge = _record_to_edge(record["rel"])
            nodes_map[sn["id"]] = sn
            nodes_map[en["id"]] = en
            edges_map[edge["id"]] = edge

        return list(nodes_map.values()), list(edges_map.values())

    async def find_paths(
        self,
        source_id: str,
        target_id: str,
        max_hops: int,
        mode: str = "shortest",
        timeout_ms: int = _DEFAULT_TIMEOUT_MS,
    ) -> tuple[list[list[Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        """Find paths between two nodes.

        Returns (paths, dedup_nodes, dedup_edges).
        """
        self._require_driver()
        assert self._driver is not None

        func = "allShortestPaths" if mode == "all_shortest" else "shortestPath"

        cypher = (
            f"MATCH (a), (b) "
            f"WHERE elementId(a) = $source AND "
            f"elementId(b) = $target "
            f"MATCH p = {func}((a)-[*..{max_hops}]-(b)) "
            f"RETURN p"
        )

        async with self._driver.session(
            default_access_mode="READ",
        ) as session:
            result = await session.execute_read(
                _run_query,
                cypher,
                {"source": source_id, "target": target_id},
                timeout_ms,
            )

        paths: list[list[Any]] = []
        nodes_map: dict[str, dict[str, Any]] = {}
        edges_map: dict[str, dict[str, Any]] = {}

        for record in result:
            path = record["p"]
            path_elements: list[Any] = []
            for node in path.nodes:
                n = _record_to_node(node)
                nodes_map[n["id"]] = n
                path_elements.append(n)
            for rel in path.relationships:
                e = _record_to_edge(rel)
                edges_map[e["id"]] = e
                path_elements.append(e)
            paths.append(path_elements)

        return (
            paths,
            list(nodes_map.values()),
            list(edges_map.values()),
        )

    async def execute_raw(
        self,
        cypher: str,
        timeout_ms: int = _DEFAULT_TIMEOUT_MS,
    ) -> list[dict[str, Any]]:
        """Execute a raw (sanitised) Cypher query.

        The query is validated by the sanitiser before execution.
        """
        self._require_driver()
        assert self._driver is not None

        clean = self._sanitiser.sanitise(cypher)

        async with self._driver.session(
            default_access_mode="READ",
        ) as session:
            result = await session.execute_read(
                _run_query,
                clean,
                {},
                timeout_ms,
            )
        rows = [dict(r) for r in result]
        return [{k: _unpack_neo4j_value(v) for k, v in row.items()} for row in rows]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _require_driver(self) -> None:
        if self._driver is None:
            raise Neo4jConnectionError("Neo4j is not connected")

    async def _fetch_labels(self) -> list[dict[str, Any]]:
        """Fetch all labels with counts and property keys."""
        assert self._driver is not None

        async with self._driver.session(
            default_access_mode="READ",
        ) as session:
            label_result = await session.execute_read(
                _run_query,
                "CALL db.labels() YIELD label RETURN label",
                {},
                _SCHEMA_TIMEOUT_MS,
            )

        labels_info: list[dict[str, Any]] = []

        async def _get_label_info(label: str) -> dict[str, Any]:
            assert self._driver is not None
            count: int | None = None
            props: list[str] = []
            try:
                async with self._driver.session(
                    default_access_mode="READ",
                ) as sess:
                    count_res = await sess.execute_read(
                        _run_query,
                        f"MATCH (n:`{_escape_label(label)}`) RETURN count(n) AS cnt",
                        {},
                        _SCHEMA_TIMEOUT_MS,
                    )
                    if count_res:
                        count = count_res[0]["cnt"]

                    prop_res = await sess.execute_read(
                        _run_query,
                        f"MATCH (n:`{_escape_label(label)}`) "
                        f"WITH keys(n) AS ks LIMIT 100 "
                        f"UNWIND ks AS k "
                        f"RETURN DISTINCT k",
                        {},
                        _SCHEMA_TIMEOUT_MS,
                    )
                    props = [r["k"] for r in prop_res]
            except (Neo4jError, TimeoutError):
                pass  # count stays None

            return {
                "name": label,
                "count": count,
                "property_keys": props,
            }

        label_names = [r["label"] for r in label_result]
        tasks = [_get_label_info(name) for name in label_names]
        labels_info = await asyncio.gather(*tasks)
        return list(labels_info)

    async def _fetch_rel_types(self) -> list[dict[str, Any]]:
        """Fetch all relationship types with counts and property keys."""
        assert self._driver is not None

        async with self._driver.session(
            default_access_mode="READ",
        ) as session:
            type_result = await session.execute_read(
                _run_query,
                "CALL db.relationshipTypes() "
                "YIELD relationshipType RETURN relationshipType",
                {},
                _SCHEMA_TIMEOUT_MS,
            )

        async def _get_type_info(
            rel_type: str,
        ) -> dict[str, Any]:
            assert self._driver is not None
            count: int | None = None
            props: list[str] = []
            try:
                async with self._driver.session(
                    default_access_mode="READ",
                ) as sess:
                    count_res = await sess.execute_read(
                        _run_query,
                        f"MATCH ()-[r:`{_escape_label(rel_type)}`]->() "
                        f"RETURN count(r) AS cnt",
                        {},
                        _SCHEMA_TIMEOUT_MS,
                    )
                    if count_res:
                        count = count_res[0]["cnt"]

                    prop_res = await sess.execute_read(
                        _run_query,
                        f"MATCH ()-[r:`{_escape_label(rel_type)}`]->() "
                        f"WITH keys(r) AS ks LIMIT 100 "
                        f"UNWIND ks AS k "
                        f"RETURN DISTINCT k",
                        {},
                        _SCHEMA_TIMEOUT_MS,
                    )
                    props = [r["k"] for r in prop_res]
            except (Neo4jError, TimeoutError):
                pass

            return {
                "name": rel_type,
                "count": count,
                "property_keys": props,
            }

        type_names = [r["relationshipType"] for r in type_result]
        tasks = [_get_type_info(t) for t in type_names]
        types_info = await asyncio.gather(*tasks)
        return list(types_info)


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------


async def _run_query(
    tx: Any,
    query: str,
    params: dict[str, Any],
    timeout_ms: int,
) -> list[Any]:
    """Run a query inside a read transaction, with timeout."""
    result = await tx.run(query, params, timeout=timeout_ms / 1000)
    return [record async for record in result]


def _sanitize_value(v: Any) -> Any:
    """Convert neo4j native types to JSON-serializable primitives."""
    if isinstance(v, (DateTime, Date, Time)):
        return v.iso_format()
    if isinstance(v, Duration):
        return str(v)
    if isinstance(v, list):
        return [_sanitize_value(i) for i in v]
    if isinstance(v, dict):
        return {k: _sanitize_value(val) for k, val in v.items()}
    return v


def _sanitize_props(props: Any) -> dict[str, Any]:
    return {k: _sanitize_value(v) for k, v in dict(props).items()}


def _record_to_node(node: Any) -> dict[str, Any]:
    """Convert a neo4j Node to our GraphNode dict."""
    return {
        "id": node.element_id,
        "labels": list(node.labels),
        "properties": _sanitize_props(node),
    }


def _record_to_edge(rel: Any) -> dict[str, Any]:
    """Convert a neo4j Relationship to our GraphEdge dict."""
    return {
        "id": rel.element_id,
        "type": rel.type,
        "source": rel.start_node.element_id,
        "target": rel.end_node.element_id,
        "properties": _sanitize_props(rel),
    }


def _unpack_neo4j_value(value: Any) -> Any:
    """Convert Neo4j driver objects to JSON-serializable dicts."""
    if isinstance(value, Path):
        elements: list[Any] = []
        for i, node in enumerate(value.nodes):
            if i > 0:
                elements.append(_record_to_edge(value.relationships[i - 1]))
            elements.append(_record_to_node(node))
        return elements
    if isinstance(value, Node):
        return _record_to_node(value)
    if isinstance(value, Relationship):
        return _record_to_edge(value)
    if isinstance(value, list):
        return [_unpack_neo4j_value(v) for v in value]
    return value


def _escape_label(label: str) -> str:
    """Escape backticks in a label/type name for safe interpolation."""
    return label.replace("`", "``")


def _escape_regex(text: str) -> str:
    """Escape special regex characters for use in Cypher =~ patterns."""
    specials = r"\.[]{}()*+?^$|"
    result = []
    for char in text:
        if char in specials:
            result.append(f"\\{char}")
        else:
            result.append(char)
    return "".join(result)
