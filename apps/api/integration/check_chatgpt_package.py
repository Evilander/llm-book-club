"""Packaged runtime smoke: synthetic replies, no account or API credentials.

Run inside the integration API container, against its isolated fixture provider.
The production runtime/config are used; only model routing and sign-in status
are substituted. This verifies protocol/isolation, not real model quality.
"""
import asyncio
import json
import os
from pathlib import Path
import tempfile

import httpx

from app.providers.llm.base import LLMMessage
from app.providers.llm.chatgpt import ChatGPTClient
from app.providers.llm.codex_runtime import CodexRuntime


async def main():
    provider = os.environ.get("TEST_PROVIDER_URL", "http://provider:9000")
    binary = os.environ.get("TEST_CODEX_BINARY", "codex")

    class FixtureRuntime(CodexRuntime):
        async def account(self):
            return {"connected": True, "plan": "fixture"}

        async def request(self, method, params=None):
            if method == "model/list":
                return {"data": [{"model": "gpt-6-astra", "isDefault": True, "defaultReasoningEffort": "low"}]}
            if method == "thread/start":
                params = {**params, "modelProvider": "readagain_fixture", "config": {"model_providers": {"readagain_fixture": {
                    "name": "Offline test peer", "base_url": f"{provider}/v1", "wire_api": "responses",
                    "requires_openai_auth": False, "supports_websockets": False,
                }}}}
            return await super().request(method, params)

    with tempfile.TemporaryDirectory(prefix="readagain-package-smoke-") as temp:
        runtime = FixtureRuntime([binary], Path(temp) / "profile")
        try:
            # The actual runtime must be disconnected before the fixture override.
            real_account = await CodexRuntime.account(runtime)
            assert real_account["connected"] is False
            async with httpx.AsyncClient() as http:
                await http.post(f"{provider}/test/reset")
            result = await ChatGPTClient(runtime).complete_with_usage([
                LLMMessage("system", "Read the supplied page. Answer in JSON with analysis and citations. No tools. The only current book is FIXTURE_CURRENT_BOOK."),
                LLMMessage("user", "The cartographer held the compass. What might it ask her to trust?"),
            ])
            assert json.loads(result.content)["analysis"] == "The compass invites a question about trust."
            assert result.input_tokens == 24 and result.output_tokens == 7
            assert runtime._subscriptions == {}
            await ChatGPTClient(runtime).complete([
                LLMMessage("system", "Discuss only FIXTURE_SECOND_BOOK. Respond in JSON. No tools."),
                LLMMessage("user", "Another book begins with a river."),
            ])
            async with httpx.AsyncClient() as http:
                calls = (await http.get(f"{provider}/test/requests")).json()
            assert len(calls) == 2, "Each reading turn should make one model request."
            assert "FIXTURE_CURRENT_BOOK" not in json.dumps(calls[1]), "Native threads must not retain another book's context."
            assert "FIXTURE_SECOND_BOOK" in json.dumps(calls[1])
            assert not list(Path(temp).rglob("rollout-*.jsonl")), "Ephemeral turns must not persist native conversation rollouts."
            wire = calls[0]
            encoded = json.dumps(wire)
            assert "FIXTURE_CURRENT_BOOK" in encoded
            # Time and a native request-for-input tool can be advertised by a
            # model catalog. No file, shell, network, app, or memory tool may be.
            permitted = {"curr_time", "request_user_input_async", "send_message_to_user_async"}
            def names(tool):
                if tool.get("type") == "namespace":
                    return {name for child in tool.get("tools", []) for name in names(child)}
                return {tool.get("name", tool.get("type"))}
            tool_names = {name for call in calls for tool in call.get("tools", []) for name in names(tool)}
            assert tool_names <= permitted, f"Unexpected tools advertised: {sorted(tool_names - permitted)}"
            print("Packaged ChatGPT runtime: isolated config, streamed final answer, token usage, and thread cleanup passed.")
        finally:
            await runtime.close()


if __name__ == "__main__":
    asyncio.run(main())
