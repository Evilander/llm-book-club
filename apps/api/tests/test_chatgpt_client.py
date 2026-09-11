import asyncio
import json
from unittest.mock import AsyncMock

import pytest

from app.providers.llm.base import LLMMessage
from app.providers.llm.chatgpt import ChatGPTClient
from app.providers.llm.codex_runtime import CodexUnavailable
from app.settings import settings


class Peer:
    def __init__(self, events, *, connected=True):
        self.events = events
        self.connected = connected
        self.calls = []
        self.cleanup = []
        self.queue = asyncio.Queue()

    async def account(self):
        return {"connected": self.connected}

    async def request(self, method, params):
        self.calls.append((method, params))
        if method == "model/list":
            return {"data": [{"model": "fixture-model", "isDefault": True, "defaultReasoningEffort": "low"}]}
        if method == "thread/start":
            return {"thread": {"id": "thread"}, "model": "fixture-model"}
        if method == "turn/start":
            for event in self.events:
                self.queue.put_nowait(event)
            return {"turn": {"id": "turn"}}
        raise AssertionError(method)

    def subscribe(self, _thread_id):
        return self.queue

    async def finish_thread(self, thread_id, turn_id, *, completed):
        self.cleanup.append((thread_id, turn_id, completed))


def event(method, **params):
    return {"method": method, "params": {"threadId": "thread", "turnId": "turn", **params}}


def answer_events(text="A quiet thought.", phase="final_answer"):
    return [
        event("item/started", item={"type": "agentMessage", "id": "answer", "phase": phase}),
        event("item/agentMessage/delta", itemId="answer", delta=text[:5]),
        event("item/agentMessage/delta", itemId="answer", delta=text[5:]),
        event("item/completed", item={"type": "agentMessage", "id": "answer", "phase": phase, "text": text}),
        event("thread/tokenUsage/updated", tokenUsage={"total": {"inputTokens": 24, "outputTokens": 7}}),
        event("turn/completed", turn={"id": "turn", "status": "completed"}),
    ]


@pytest.mark.asyncio
async def test_only_final_prose_streams_with_usage_and_scoped_input():
    peer = Peer([
        event("item/started", item={"type": "agentMessage", "id": "comment", "phase": "commentary"}),
        event("item/agentMessage/delta", itemId="comment", delta="Do not show this commentary"),
        event("item/agentMessage/delta", itemId="answer", turnId="other-turn", delta="Cross-turn text"),
        *answer_events(),
    ])
    client = ChatGPTClient(peer)
    result = await client.complete_with_usage([LLMMessage("system", "Only page one evidence."), LLMMessage("user", "What do you notice?")])
    assert result.content == "A quiet thought."
    assert result.input_tokens == 24 and result.output_tokens == 7 and result.model == "fixture-model"
    thread = next(params for method, params in peer.calls if method == "thread/start")
    turn = next(params for method, params in peer.calls if method == "turn/start")
    assert thread["ephemeral"] is True and thread["environments"] == [] and turn["environments"] == []
    assert thread["approvalPolicy"] == "never" and thread["sandbox"] == "read-only"
    assert "Only page one evidence." in thread["developerInstructions"]
    assert json.loads(turn["input"][0]["text"]) == [{"role": "user", "content": "What do you notice?"}]
    assert peer.cleanup == [("thread", "turn", True)]


@pytest.mark.asyncio
async def test_unlabelled_answer_is_buffered_until_completion():
    peer = Peer(answer_events(phase=None))
    chunks = [part async for part in ChatGPTClient(peer).stream([LLMMessage("user", "A thought?")])]
    assert chunks == ["A quiet thought."]


@pytest.mark.asyncio
async def test_disconnect_never_falls_back_to_an_api_key():
    peer = Peer([], connected=False)
    with pytest.raises(CodexUnavailable, match="Connect ChatGPT"):
        await ChatGPTClient(peer).complete([LLMMessage("user", "Hello")])
    assert peer.calls == []


@pytest.mark.asyncio
async def test_output_limit_interrupts_before_leaking_oversized_reply():
    peer = Peer(answer_events("x" * 30))
    with pytest.raises(CodexUnavailable, match="too long"):
        await ChatGPTClient(peer).complete([LLMMessage("user", "Hello")], max_tokens=1)
    assert peer.cleanup == [("thread", "turn", False)]


@pytest.mark.asyncio
async def test_cancelled_browser_consumer_interrupts_its_turn():
    peer = Peer(answer_events()[:2])
    stream = ChatGPTClient(peer).stream([LLMMessage("user", "Hello")])
    assert await anext(stream) == "A qui"
    await stream.aclose()
    assert peer.cleanup == [("thread", "turn", False)]


@pytest.mark.asyncio
async def test_failed_turn_and_timeout_do_not_report_success(monkeypatch):
    peer = Peer([event("turn/completed", turn={"id": "turn", "status": "failed", "error": {"message": "PRIVATE_TOKEN_CANARY"}})])
    with pytest.raises(CodexUnavailable) as error:
        await ChatGPTClient(peer).complete([LLMMessage("user", "Hello")])
    assert "PRIVATE_TOKEN_CANARY" not in str(error.value)
    monkeypatch.setattr(settings, "chatgpt_turn_timeout_seconds", 0.02)
    peer = Peer([])
    with pytest.raises(CodexUnavailable, match="too long"):
        await ChatGPTClient(peer).complete([LLMMessage("user", "Hello")])
    assert peer.cleanup == [("thread", "turn", False)]


@pytest.mark.asyncio
async def test_closing_discussion_stream_reaches_native_turn_cleanup(mock_db, sample_session, sample_book, monkeypatch):
    from app.discussion.engine import DiscussionEngine
    from app.retrieval.selector import select_session_slice

    peer = Peer(answer_events('{"analysis":"A quiet thought in progress')[:3])
    client = ChatGPTClient(peer)
    monkeypatch.setattr("app.discussion.engine.get_llm_client", lambda **_: client)
    monkeypatch.setattr("app.discussion.agents.search_chunks", AsyncMock(return_value=[]))
    engine = DiscussionEngine(mock_db, sample_session, select_session_slice(mock_db, sample_book["book"].id, section_ids=[sample_book["section"].id]))
    events = engine.stream_user_message("What do you notice?", include_close_reader=False, adaptive=False)
    while True:
        message = await anext(events)
        if message["type"] == "message_delta":
            break
        assert message["type"] != "agent_error", message
    await events.aclose()
    assert peer.cleanup == [("thread", "turn", False)]
