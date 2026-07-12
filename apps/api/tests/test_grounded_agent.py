"""End-to-end agent tests for claim-bound grounded responses and repair."""

import asyncio
import json
from unittest.mock import AsyncMock, patch

from app.discussion.agents import FacilitatorAgent
from app.discussion.grounded_response import GROUNDING_FALLBACK_TEXT
from app.providers.llm.base import StructuredLLMResponse
from app.retrieval.search import SearchResult


class StructuredStub:
    def __init__(self, *payloads: dict, refusal: str | None = None):
        self.payloads = list(payloads)
        self.refusal = refusal
        self.calls: list[dict] = []

    async def complete_structured(self, messages, **kwargs):
        self.calls.append({"messages": messages, **kwargs})
        if self.refusal:
            return StructuredLLMResponse(
                content="",
                parsed=None,
                refusal=self.refusal,
                input_tokens=4,
                output_tokens=1,
            )
        payload = self.payloads.pop(0)
        return StructuredLLMResponse(
            content=json.dumps(payload),
            parsed=payload,
            input_tokens=10,
            output_tokens=5,
        )


def grounded_payload(chunk_id: str, quote: str, claim: str = "The image suspends time"):
    return {
        "segments": [
            {
                "id": "claim",
                "kind": "interpretation",
                "text": claim,
                "citation_ids": ["evidence"],
            },
            {
                "id": "question",
                "kind": "question",
                "text": "Did the moment feel peaceful or ominous to you?",
                "citation_ids": [],
            },
        ],
        "citations": [
            {"id": "evidence", "chunk_id": chunk_id, "quote": quote}
        ],
    }


def result_for(chunk) -> SearchResult:
    return SearchResult(
        chunk_id=chunk.id,
        section_id=chunk.section_id,
        section_title="Chapter 1",
        text=chunk.text,
        char_start=chunk.char_start,
        char_end=chunk.char_end,
        source_ref=None,
        score=1.0,
    )


def run_agent(mock_db, sample_book, llm):
    chunk = sample_book["chunks"][0]
    agent = FacilitatorAgent(
        llm_client=llm,
        db=mock_db,
        book_id=sample_book["book"].id,
        context="Selected reading context",
        allowed_section_ids=[sample_book["section"].id],
        allowed_chunk_ids=[chunk.id],
    )
    with patch(
        "app.discussion.agents.search_chunks",
        new_callable=AsyncMock,
        return_value=[result_for(chunk)],
    ):
        response = asyncio.run(
            agent.respond_with_retrieval([], query="What does the image do?")
        )
    return agent, response


def test_valid_claim_is_bound_to_verified_span(mock_db, sample_book):
    chunk = sample_book["chunks"][0]
    llm = StructuredStub(
        grounded_payload(chunk.id, "The morning sun cast long shadows")
    )

    agent, response = run_agent(mock_db, sample_book, llm)

    assert agent.uses_grounded_segments is True
    assert "GROUNDING OUTPUT CONTRACT" in agent.system_prompt
    assert len(llm.calls) == 1
    assert response.citations[0].verified is True
    assert response.citations[0].citation_id == "evidence"
    assert response.citations[0].segment_ids == ["claim"]
    assert response.segments[0]["citation_ids"] == ["evidence"]
    assert response.grounding_metadata["metrics"]["retained_claim_segments"] == 1
    assert response.input_tokens == 10
    assert response.output_tokens == 5


def test_invalid_claim_gets_one_successful_repair(mock_db, sample_book):
    chunk = sample_book["chunks"][0]
    llm = StructuredStub(
        grounded_payload(chunk.id, "fabricated quote", "Unsupported first claim"),
        grounded_payload(
            chunk.id,
            "The morning sun cast long shadows",
            "The long shadows make the opening feel suspended",
        ),
    )

    _, response = run_agent(mock_db, sample_book, llm)

    assert len(llm.calls) == 2
    assert "Unsupported first claim" not in response.content
    assert "long shadows make" in response.content
    assert response.grounding_metadata["repair_attempted"] is True
    assert response.grounding_metadata["repair_succeeded"] is True
    assert response.citation_metrics.repair_attempted is True
    assert response.input_tokens == 20
    assert "invalid_citation" in llm.calls[1]["messages"][-1].content


def test_failed_repair_never_restores_unsupported_claim(mock_db, sample_book):
    chunk = sample_book["chunks"][0]
    llm = StructuredStub(
        grounded_payload(chunk.id, "first fabricated quote", "First unsupported claim"),
        grounded_payload(chunk.id, "second fabricated quote", "Second unsupported claim"),
    )

    _, response = run_agent(mock_db, sample_book, llm)

    assert len(llm.calls) == 2
    assert "unsupported claim" not in response.content.lower()
    assert response.citations == []
    assert [segment["kind"] for segment in response.segments] == ["question"]
    assert response.grounding_metadata["repair_succeeded"] is False


def test_schema_failure_repairs_once_then_uses_safe_fallback(mock_db, sample_book):
    llm = StructuredStub(
        {"segments": []},
        {"segments": []},
    )

    _, response = run_agent(mock_db, sample_book, llm)

    assert len(llm.calls) == 2
    assert response.content == GROUNDING_FALLBACK_TEXT
    assert response.citations == []
    assert response.grounding_metadata["fallback_used"] is True
    assert response.grounding_metadata["repair_attempted"] is True


def test_provider_refusal_is_safe_and_not_retried(mock_db, sample_book):
    llm = StructuredStub(refusal="I can't help with that request.")

    _, response = run_agent(mock_db, sample_book, llm)

    assert len(llm.calls) == 1
    assert response.content == "I can't help with that request."
    assert response.citations == []
    assert response.segments[0]["kind"] == "reader_reflection"
    assert response.grounding_metadata["refused"] is True
