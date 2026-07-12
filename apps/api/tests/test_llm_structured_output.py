"""Provider contract tests for schema-constrained discussion responses."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

from app.providers.llm.anthropic import AnthropicClient
from app.providers.llm.base import LLMMessage, LLMResponse
from app.providers.llm.gemini import GeminiClient
from app.providers.llm.grok import GrokClient
from app.providers.llm.openai import OpenAIClient


SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {"answer": {"type": "string"}},
    "required": ["answer"],
}
MESSAGES = [LLMMessage(role="user", content="Discuss this passage")]


def async_client_mock(payload: dict):
    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = payload
    entered_client = MagicMock()
    entered_client.post = AsyncMock(return_value=response)
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=entered_client)
    context.__aexit__ = AsyncMock(return_value=None)
    return context, entered_client


def test_openai_sends_strict_json_schema_and_parses_usage():
    context, http_client = async_client_mock(
        {
            "model": "gpt-4.1",
            "choices": [
                {"message": {"content": '{"answer":"grounded"}', "refusal": None}}
            ],
            "usage": {"prompt_tokens": 11, "completion_tokens": 4},
        }
    )
    client = OpenAIClient(api_key="test", model="gpt-4.1")

    with patch("app.providers.llm.openai.httpx.AsyncClient", return_value=context):
        result = asyncio.run(
            client.complete_structured(
                MESSAGES,
                schema_name="grounded_response",
                json_schema=SCHEMA,
                temperature=0.2,
                max_tokens=500,
            )
        )

    request = http_client.post.await_args.kwargs["json"]
    assert request["response_format"] == {
        "type": "json_schema",
        "json_schema": {
            "name": "grounded_response",
            "strict": True,
            "schema": SCHEMA,
        },
    }
    assert result.parsed == {"answer": "grounded"}
    assert result.total_tokens == 15


def test_openai_surfaces_refusal_without_parsing_content():
    context, _ = async_client_mock(
        {
            "choices": [{"message": {"content": None, "refusal": "Cannot comply"}}],
            "usage": {},
        }
    )
    client = OpenAIClient(api_key="test")

    with patch("app.providers.llm.openai.httpx.AsyncClient", return_value=context):
        result = asyncio.run(
            client.complete_structured(
                MESSAGES,
                schema_name="grounded_response",
                json_schema=SCHEMA,
            )
        )

    assert result.parsed is None
    assert result.refusal == "Cannot comply"


def test_local_openai_compatible_client_uses_json_text_adapter():
    client = OpenAIClient(
        api_key="local",
        model="local-model",
        base_url="http://localhost:11434/v1",
    )
    client.complete_with_usage = AsyncMock(
        return_value=LLMResponse(
            content="```json\n{\"answer\":\"local\"}\n```",
            input_tokens=8,
            output_tokens=3,
            model="local-model",
        )
    )

    result = asyncio.run(
        client.complete_structured(
            MESSAGES,
            schema_name="grounded_response",
            json_schema=SCHEMA,
        )
    )

    fallback_messages = client.complete_with_usage.await_args.args[0]
    assert json.dumps(SCHEMA, separators=(",", ":")) in fallback_messages[-1].content
    assert result.parsed == {"answer": "local"}


def test_anthropic_uses_native_output_config():
    context, http_client = async_client_mock(
        {
            "model": "claude-sonnet-4-6",
            "content": [{"type": "text", "text": '{"answer":"grounded"}'}],
            "usage": {"input_tokens": 9, "output_tokens": 5},
            "stop_reason": "end_turn",
        }
    )
    client = AnthropicClient(api_key="test")

    with patch("app.providers.llm.anthropic.httpx.AsyncClient", return_value=context):
        result = asyncio.run(
            client.complete_structured(
                MESSAGES,
                schema_name="grounded_response",
                json_schema=SCHEMA,
            )
        )

    request = http_client.post.await_args.kwargs["json"]
    assert request["output_config"] == {
        "format": {"type": "json_schema", "schema": SCHEMA}
    }
    assert result.parsed == {"answer": "grounded"}
    assert result.total_tokens == 14


def test_gemini_uses_json_schema_and_adds_v2_property_ordering():
    context, http_client = async_client_mock(
        {
            "modelVersion": "gemini-2.0-flash",
            "candidates": [
                {
                    "content": {"parts": [{"text": '{"answer":"grounded"}'}]},
                    "finishReason": "STOP",
                }
            ],
            "usageMetadata": {"promptTokenCount": 7, "candidatesTokenCount": 3},
        }
    )
    client = GeminiClient(api_key="test", model="gemini-2.0-flash")

    with patch("app.providers.llm.gemini.httpx.AsyncClient", return_value=context):
        result = asyncio.run(
            client.complete_structured(
                MESSAGES,
                schema_name="grounded_response",
                json_schema=SCHEMA,
            )
        )

    config = http_client.post.await_args.kwargs["json"]["generationConfig"]
    assert config["responseMimeType"] == "application/json"
    assert config["responseJsonSchema"]["propertyOrdering"] == ["answer"]
    assert result.parsed == {"answer": "grounded"}
    assert result.total_tokens == 10


def test_grok_reuses_openai_json_schema_wire_contract():
    context, http_client = async_client_mock(
        {
            "model": "grok-3",
            "choices": [
                {"message": {"content": '{"answer":"grounded"}', "refusal": None}}
            ],
            "usage": {},
        }
    )
    client = GrokClient(api_key="test", model="grok-3")

    with patch("app.providers.llm.openai.httpx.AsyncClient", return_value=context):
        asyncio.run(
            client.complete_structured(
                MESSAGES,
                schema_name="grounded_response",
                json_schema=SCHEMA,
            )
        )

    call = http_client.post.await_args
    assert call.args[0] == "https://api.x.ai/v1/chat/completions"
    assert call.kwargs["json"]["response_format"]["type"] == "json_schema"
