import asyncio
from pathlib import Path
import stat
import sys

import pytest

from app.providers.llm.codex_runtime import CodexRuntime, CodexUnavailable, prepare_state_directory


def runtime_for(tmp_path):
    return CodexRuntime([sys.executable, str(Path(__file__).parent / "fixtures/codex_process.py")], tmp_path / "profile", request_timeout=1)


@pytest.mark.asyncio
async def test_isolated_profile_does_not_inherit_keys_or_personal_home(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "PRIVATE_TOKEN_CANARY")
    runtime = runtime_for(tmp_path)
    try:
        state = await runtime.request("fixture/environment")
        assert state == {"inherited_api_key": False, "inherited_home": False, "codex_home": str(tmp_path / "profile")}
        assert stat.S_IMODE((tmp_path / "profile").stat().st_mode) == 0o700
        assert stat.S_IMODE((tmp_path / "profile/config.toml").stat().st_mode) == 0o600
    finally:
        await runtime.close()


@pytest.mark.parametrize("kind", ["personal", "nonempty", "symlink", "marker_symlink", "profile_symlink"])
def test_refuses_personal_or_redirected_credential_folder(tmp_path, monkeypatch, kind):
    directory = tmp_path / "profile"
    if kind == "personal":
        monkeypatch.setenv("CODEX_HOME", str(directory))
    elif kind == "nonempty":
        directory.mkdir()
        (directory / "auth.json").write_text("private fixture")
    elif kind == "symlink":
        directory.symlink_to(tmp_path)
    else:
        prepare_state_directory(directory)
        path = directory / (".readagain-managed" if kind == "marker_symlink" else "config.toml")
        path.unlink()
        target = tmp_path / "private"
        target.write_text("private fixture")
        path.symlink_to(target)
    with pytest.raises(CodexUnavailable):
        prepare_state_directory(directory)
    if (tmp_path / "private").exists():
        assert (tmp_path / "private").read_text() == "private fixture"


@pytest.mark.asyncio
async def test_login_completion_before_response_is_not_lost_or_leaked(tmp_path):
    runtime = runtime_for(tmp_path)
    try:
        await runtime.request("fixture/setup", {"early_complete": True})
        login = await runtime.begin_login()
        assert login["state"] == "completed"
        assert "user_code" not in login and "verification_url" not in login
        assert await runtime.account() == {"connected": True, "plan": "plus"}
        await runtime.logout()
        assert runtime.process is None
        assert runtime.login is None
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_concurrent_login_reuses_code_and_expiry_clears_it(tmp_path):
    runtime = runtime_for(tmp_path)
    try:
        a, b = await asyncio.gather(runtime.begin_login(), runtime.begin_login())
        assert a == b
        runtime.login["deadline"] = 0
        login = await runtime.login_status(a["login_id"])
        assert login["state"] == "expired"
        assert "user_code" not in login
        assert await runtime.login_status("unknown") is None
    finally:
        await runtime.close()


@pytest.mark.parametrize("url", ["http://auth.openai.com/codex/device", "https://example.com/codex/device", "https://auth.openai.com/codex/device?redirect=private", "https://auth.openai.com@evil.example/codex/device"])
@pytest.mark.asyncio
async def test_only_official_device_verification_url_is_returned(tmp_path, url):
    runtime = runtime_for(tmp_path)
    try:
        await runtime.request("fixture/setup", {"url": url})
        with pytest.raises(CodexUnavailable, match="unsupported sign-in"):
            await runtime.begin_login()
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_runtime_rejects_tool_execution_and_hides_raw_errors(tmp_path):
    runtime = runtime_for(tmp_path)
    try:
        queue = runtime.subscribe("tools")
        await runtime.request("fixture/tool")
        assert (await asyncio.wait_for(queue.get(), 2))["method"] == "fixture/toolRejected"
        with pytest.raises(CodexUnavailable) as error:
            await runtime.request("fixture/error")
        assert "PRIVATE_TOKEN_CANARY" not in str(error.value)
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_crash_fails_waiters_and_pending_login_then_can_restart(tmp_path):
    runtime = runtime_for(tmp_path)
    try:
        await runtime.begin_login()
        queue = runtime.subscribe("thread")
        with pytest.raises(CodexUnavailable):
            await runtime.request("fixture/crash")
        assert (await queue.get())["method"] == "readagain/disconnected"
        assert runtime.login["state"] == "failed"
        assert "user_code" not in runtime.login
        await runtime.close()
        assert (await runtime.account())["connected"] is False
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_unresponsive_turn_cleanup_stops_the_process(tmp_path):
    runtime = runtime_for(tmp_path)
    try:
        await runtime.start()
        process = runtime.process
        with pytest.raises(CodexUnavailable, match="too long"):
            await runtime.request("fixture/hang")
        await runtime.finish_thread("thread", "turn", completed=False)
        assert runtime.process is None
        assert process.returncode is not None
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_slow_consumer_is_interrupted_without_stopping_other_readers(tmp_path):
    runtime = runtime_for(tmp_path)
    try:
        slow = runtime.subscribe("slow")
        healthy = runtime.subscribe("healthy")
        await runtime.request("fixture/flood")
        assert (await slow.get())["method"] == "readagain/disconnected"
        assert (await healthy.get())["method"] == "fixture/healthy"
        await runtime.finish_thread("slow", "slow-turn", completed=False)
        assert runtime.process.returncode is None
        assert "slow" not in runtime._subscriptions
        assert (await runtime.account())["connected"] is False
    finally:
        await runtime.close()
