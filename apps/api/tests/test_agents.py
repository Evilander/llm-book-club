"""Targeted agent tests for slice-bounded retrieval and citation enforcement."""

import asyncio
from unittest.mock import AsyncMock, patch

from app.discussion.agents import FacilitatorAgent
from app.providers.llm.base import LLMResponse


class _StubLLM:
    async def complete(self, messages, temperature=0.7, max_tokens=2048):
        return '{"analysis":"stub","citations":[]}'

    async def complete_with_usage(self, messages, temperature=0.7, max_tokens=2048):
        return LLMResponse(
            content='{"analysis":"stub","citations":[]}',
            input_tokens=10,
            output_tokens=5,
        )

    async def stream(self, messages, temperature=0.7, max_tokens=2048):
        yield '{"analysis":"stub","citations":[]}'

    @property
    def last_stream_usage(self):
        return LLMResponse(content="", input_tokens=10, output_tokens=5)


def test_agent_retrieval_is_slice_bounded(mock_db):
    """Agents should pass the session slice into retrieval instead of searching the whole book."""
    async def run_test():
        agent = FacilitatorAgent(
            llm_client=_StubLLM(),
            db=mock_db,
            book_id="book-1",
            context="Context",
            mode="conversation",
            allowed_section_ids=["section-a", "section-b"],
            allowed_chunk_ids=["chunk-a"],
        )

        with patch("app.discussion.agents.search_chunks", new_callable=AsyncMock) as mock_search:
            mock_search.return_value = []
            response = await agent.respond_with_retrieval([], query="What matters here?")

        assert response.content == "stub"
        mock_search.assert_awaited_once_with(
            mock_db,
            "book-1",
            "What matters here?",
            limit=5,
            section_ids=["section-a", "section-b"],
        )

    asyncio.run(run_test())
