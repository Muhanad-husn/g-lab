"""Unit tests for CopilotPipeline with document retrieval."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.schemas import (
    ChunkMetadata,
    CopilotQueryRequest,
    DocumentChunk,
    PresetConfig,
    RouterIntent,
)
from app.services.copilot.pipeline import CopilotPipeline
from app.services.copilot.sse import SSEEvent


def _make_chunk(chunk_id: str) -> DocumentChunk:
    return DocumentChunk(
        id=chunk_id,
        text="relevant document text",
        metadata=ChunkMetadata(
            document_id="doc-1",
            library_id="lib-1",
            page_number=2,
            section_heading=None,
            chunk_index=0,
            parse_tier="high",
        ),
        similarity_score=0.9,
    )


def _preset() -> PresetConfig:
    return PresetConfig(
        models={
            "router": "m/r",
            "graphRetrieval": "m/g",
            "synthesiser": "m/s",
        },
        tokenBudgets={"router": 128, "graphRetrieval": 256, "synthesiser": 512},
    )


def _make_synth_events() -> list[SSEEvent]:
    return [
        SSEEvent(event="text_chunk", data={"text": "Answer here."}),
        SSEEvent(event="evidence", data={"sources": []}),
        SSEEvent(event="confidence", data={"score": 0.85, "band": "high"}),
        SSEEvent(event="done", data={}),
    ]


def _make_low_conf_events() -> list[SSEEvent]:
    return [
        SSEEvent(event="text_chunk", data={"text": "Partial answer."}),
        SSEEvent(event="confidence", data={"score": 0.2, "band": "low"}),
        SSEEvent(event="done", data={}),
    ]


@pytest.fixture()
def semaphore() -> asyncio.Semaphore:
    return asyncio.Semaphore(1)


@pytest.fixture()
def request_obj() -> CopilotQueryRequest:
    return CopilotQueryRequest(query="Who owns company X?", session_id="sess-1")


async def _collect(gen: AsyncGenerator[SSEEvent, None]) -> list[SSEEvent]:
    return [e async for e in gen]


# ---------------------------------------------------------------------------
# Happy path: graph + doc retrieval run in parallel, synthesiser gets both
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pipeline_with_doc_retrieval(
    semaphore: asyncio.Semaphore,
    request_obj: CopilotQueryRequest,
) -> None:
    synth_events = _make_synth_events()

    mock_openrouter = MagicMock()
    mock_neo4j = MagicMock()
    mock_retrieval_svc = AsyncMock()
    mock_reranker_svc = AsyncMock()

    doc_chunks = [_make_chunk("c1"), _make_chunk("c2")]

    intent = RouterIntent(needs_graph=True, needs_docs=True, doc_query="company ownership")

    with (
        patch(
            "app.services.copilot.pipeline.RouterService.classify",
            new=AsyncMock(return_value=intent),
        ),
        patch(
            "app.services.copilot.pipeline.GraphRetrievalService.retrieve",
            new=AsyncMock(return_value=([{"node": "A"}], [], "")),
        ),
        patch(
            "app.services.copilot.pipeline.DocumentRetrievalRole.retrieve",
            new=AsyncMock(return_value=(doc_chunks, [])),
        ),
        patch(
            "app.services.copilot.pipeline.SynthesiserService.synthesise",
            return_value=_async_iter(synth_events),
        ),
    ):
        pipeline = CopilotPipeline()
        events = await _collect(
            pipeline.execute(
                request=request_obj,
                neo4j_service=mock_neo4j,
                openrouter_client=mock_openrouter,
                preset_config=_preset(),
                session_id="sess-1",
                semaphore=semaphore,
                retrieval_service=mock_retrieval_svc,
                reranker_service=mock_reranker_svc,
                library_id="lib-1",
            )
        )

    event_types = [e.event for e in events]
    assert "text_chunk" in event_types
    assert "done" in event_types
    # Status events should include retrieving
    assert any(
        e.event == "status" and isinstance(e.data, dict) and e.data.get("stage") == "retrieving"
        for e in events
    )


# ---------------------------------------------------------------------------
# Re-retrieval increases doc top-k by 5
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pipeline_reretrieval_increases_doc_top_k(
    semaphore: asyncio.Semaphore,
    request_obj: CopilotQueryRequest,
) -> None:
    low_conf_events = _make_low_conf_events()
    high_conf_events = _make_synth_events()

    mock_openrouter = MagicMock()
    mock_neo4j = MagicMock()
    mock_retrieval_svc = AsyncMock()
    mock_reranker_svc = AsyncMock()

    intent = RouterIntent(needs_graph=True, needs_docs=True, doc_query="query")

    call_count = {"n": 0}
    synth_call_count = {"n": 0}

    doc_retrieve_calls: list[dict[str, Any]] = []

    async def fake_doc_retrieve(**kwargs: Any) -> tuple[list[DocumentChunk], list]:
        doc_retrieve_calls.append(kwargs)
        return [_make_chunk(f"c{len(doc_retrieve_calls)}")], []

    async def fake_synth(**kwargs: Any) -> AsyncGenerator[SSEEvent, None]:
        synth_call_count["n"] += 1
        if synth_call_count["n"] == 1:
            for e in low_conf_events:
                yield e
        else:
            for e in high_conf_events:
                yield e

    with (
        patch(
            "app.services.copilot.pipeline.RouterService.classify",
            new=AsyncMock(return_value=intent),
        ),
        patch(
            "app.services.copilot.pipeline.GraphRetrievalService.retrieve",
            new=AsyncMock(return_value=([], [], "")),
        ),
        patch(
            "app.services.copilot.pipeline.DocumentRetrievalRole.retrieve",
            new=AsyncMock(side_effect=fake_doc_retrieve),
        ),
        patch.object(
            type(CopilotPipeline()),
            "_execute_pipeline",
        ),
    ):
        # We need to test the actual _execute_pipeline; patch synthesise instead
        pass

    # Simpler: directly patch SynthesiserService.synthesise
    with (
        patch(
            "app.services.copilot.pipeline.RouterService.classify",
            new=AsyncMock(return_value=intent),
        ),
        patch(
            "app.services.copilot.pipeline.GraphRetrievalService.retrieve",
            new=AsyncMock(return_value=([], [], "")),
        ),
        patch(
            "app.services.copilot.pipeline.DocumentRetrievalRole.retrieve",
            new=AsyncMock(side_effect=fake_doc_retrieve),
        ),
        patch(
            "app.services.copilot.pipeline.SynthesiserService.synthesise",
            side_effect=fake_synth,
        ),
    ):
        pipeline = CopilotPipeline()
        events = await _collect(
            pipeline.execute(
                request=request_obj,
                neo4j_service=mock_neo4j,
                openrouter_client=mock_openrouter,
                preset_config=_preset(),
                session_id="sess-1",
                semaphore=semaphore,
                retrieval_service=mock_retrieval_svc,
                reranker_service=mock_reranker_svc,
                library_id="lib-1",
            )
        )

    # Re-retrieval should have fired a re_retrieving status event
    assert any(
        e.event == "status"
        and isinstance(e.data, dict)
        and e.data.get("stage") == "re_retrieving"
        for e in events
    )
    # doc retrieve was called twice (initial + re-retrieval)
    assert len(doc_retrieve_calls) == 2
    # re-retrieval call has top_k = initial (5) + 5 = 10
    initial_top_k = doc_retrieve_calls[0].get("top_k", 0)
    reretrieval_top_k = doc_retrieve_calls[1].get("top_k", 0)
    assert reretrieval_top_k == initial_top_k + 5


# ---------------------------------------------------------------------------
# No retrieval service → doc retrieval skipped, pipeline still works
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pipeline_no_doc_services(
    semaphore: asyncio.Semaphore,
    request_obj: CopilotQueryRequest,
) -> None:
    synth_events = _make_synth_events()
    intent = RouterIntent(needs_graph=True, needs_docs=True, doc_query="query")

    with (
        patch(
            "app.services.copilot.pipeline.RouterService.classify",
            new=AsyncMock(return_value=intent),
        ),
        patch(
            "app.services.copilot.pipeline.GraphRetrievalService.retrieve",
            new=AsyncMock(return_value=([], [], "")),
        ),
        patch(
            "app.services.copilot.pipeline.SynthesiserService.synthesise",
            return_value=_async_iter(synth_events),
        ),
    ):
        pipeline = CopilotPipeline()
        events = await _collect(
            pipeline.execute(
                request=request_obj,
                neo4j_service=MagicMock(),
                openrouter_client=MagicMock(),
                preset_config=_preset(),
                session_id="sess-1",
                semaphore=semaphore,
                # No retrieval_service / reranker_service / library_id
            )
        )

    assert any(e.event == "done" for e in events)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _async_iter(events: list[SSEEvent]) -> AsyncGenerator[SSEEvent, None]:
    """Return an async generator from a plain list of SSEEvents."""

    async def _gen() -> AsyncGenerator[SSEEvent, None]:
        for e in events:
            yield e

    return _gen()
