"""The library's isolated, managed ChatGPT connection over Codex JSONL.

This talks to the documented app-server protocol, never to consumer endpoints
or copied subscription tokens. The process owns a dedicated credential folder.
"""
from __future__ import annotations

import asyncio
from contextlib import suppress
import json
import logging
import os
from pathlib import Path
import shutil
import signal
import time

CODEX_VERSION = "0.154.0"
logger = logging.getLogger(__name__)


class CodexUnavailable(RuntimeError):
    """A public-safe connection error; never include a raw provider payload."""


# Versioned with the bundled CLI. The per-thread environments=[] setting is
# also mandatory: in 0.154 it removes shell, patch, and file tools entirely.
PROFILE = """# Managed by ReadAgain. Keep personal Codex configuration elsewhere.
forced_login_method = "chatgpt"
cli_auth_credentials_store = "file"
approval_policy = "never"
sandbox_mode = "read-only"
web_search = "disabled"
project_doc_max_bytes = 0
thread_unload_delay_secs = 0
include_apps_instructions = false
include_collaboration_mode_instructions = false
include_environment_context = false
include_permissions_instructions = false
notify = []

[history]
persistence = "none"
[analytics]
enabled = false
[feedback]
enabled = false
[apps._default]
enabled = false
[agents]
enabled = false
[memories]
generate_memories = false
use_memories = false
dedicated_tools = false
[skills]
include_instructions = false
[skills.bundled]
enabled = false
[tools.update_plan]
enabled = false
[tools.experimental_request_user_input]
enabled = false
[features]
apps = false
plugins = false
hooks = false
codex_hooks = false
plugin_hooks = false
shell_tool = false
unified_exec = false
code_mode = false
code_mode_host = false
js_repl = false
browser_use = false
computer_use = false
image_generation = false
view_image = false
multi_agent = false
multi_agent_v2 = false
memories = false
memory_tool = false
goals = false
sleep_tool = false
request_permissions_tool = false
tool_suggest = false
deferred_executor = false
token_budget = false
current_time_reminder = false
skip_host_skill_discovery = true
"""


def prepare_state_directory(directory: Path) -> Path:
    """Only initialize an empty directory or an existing ReadAgain profile."""
    if directory.is_symlink():
        raise CodexUnavailable("ChatGPT needs a dedicated storage folder, without a symlink.")
    directory = directory.resolve()
    personal = {Path.home().resolve(), (Path.home() / ".codex").resolve(), Path("/")}
    inherited = os.environ.get("CODEX_HOME")
    if inherited:
        personal.add(Path(inherited).resolve())
    if directory in personal:
        raise CodexUnavailable("ChatGPT needs its own library connection folder.")
    marker = directory / ".readagain-managed"
    if marker.is_symlink() or (marker.exists() and marker.read_text() != "readagain-codex-v1\n"):
        raise CodexUnavailable("The ChatGPT connection folder is not managed by this library.")
    if directory.exists() and any(directory.iterdir()) and not marker.is_file():
        raise CodexUnavailable("Choose an empty folder for this library's ChatGPT connection.")
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory.chmod(0o700)
    # These files belong to this app, not the user's coding profile.
    if not marker.exists():
        with marker.open("x") as stream:
            stream.write("readagain-codex-v1\n")
    marker.chmod(0o600)
    profile = directory / "config.toml"
    if profile.is_symlink():
        raise CodexUnavailable("The ChatGPT connection profile must be a regular file.")
    # Atomic replacement also avoids following an existing hard link.
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", dir=directory, delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(PROFILE)
    temporary.replace(profile)
    return directory


class CodexRuntime:
    """One account process; turns have separate ephemeral threads and queues."""

    def __init__(self, command: list[str], state_dir: Path, *, request_timeout: float = 20):
        self.command = command
        self.state_dir = state_dir
        self.request_timeout = request_timeout
        self.process: asyncio.subprocess.Process | None = None
        self._reader: asyncio.Task | None = None
        self._start_lock = asyncio.Lock()
        self._write_lock = asyncio.Lock()
        self._login_lock = asyncio.Lock()
        self._next_id = 0
        self._pending: dict[int, asyncio.Future] = {}
        self._subscriptions: dict[str, asyncio.Queue] = {}
        self._active_turns: dict[str, str] = {}
        self._cleanup_tasks: dict[str, asyncio.Task] = {}
        self.login: dict | None = None
        self._login_results: dict[str, bool] = {}
        self.loop = asyncio.get_running_loop()

    @property
    def available(self) -> bool:
        return bool(self.command and shutil.which(self.command[0]))

    async def start(self):
        async with self._start_lock:
            if self.process is not None and self.process.returncode is None:
                return
            if not self.available:
                raise CodexUnavailable("Install the bundled ChatGPT connection runtime, then try again.")
            try:
                directory = prepare_state_directory(self.state_dir)
                work_dir = directory / "empty-workspace"
                if work_dir.is_symlink():
                    raise CodexUnavailable("The ChatGPT workspace must be a dedicated folder.")
                work_dir.mkdir(exist_ok=True, mode=0o700)
            except OSError:
                raise CodexUnavailable("ChatGPT cannot use its connection folder. Check its location and permissions.") from None
            # Configure only this child process's proper Codex home. Do not
            # inherit API keys, coding profile overrides, or plugin settings.
            child_env = {key: os.environ[key] for key in (
                "PATH", "LANG", "LC_ALL", "TMPDIR", "SYSTEMROOT", "WINDIR",
                "HTTPS_PROXY", "HTTP_PROXY", "NO_PROXY", "SSL_CERT_FILE",
            ) if key in os.environ}
            child_env["CODEX_HOME"] = str(directory)
            child_env["RUST_LOG"] = "off"
            try:
                version = await asyncio.create_subprocess_exec(
                    *self.command, "--version", cwd=work_dir, env=child_env,
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
                    start_new_session=os.name == "posix",
                )
                try:
                    output, _ = await asyncio.wait_for(version.communicate(), 10)
                    if version.returncode != 0 or output.strip() != f"codex-cli {CODEX_VERSION}".encode():
                        raise CodexUnavailable("Use the bundled Codex runtime version.")
                finally:
                    await self._stop_process(version)
                self.process = await asyncio.create_subprocess_exec(
                    *self.command, "app-server", "--strict-config", "--listen", "stdio://",
                    cwd=work_dir, env=child_env, stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
                    limit=1024 * 1024,
                    start_new_session=os.name == "posix",
                )
                self._reader = asyncio.create_task(self._read_messages())
                await self._request("initialize", {
                    "clientInfo": {"name": "readagain", "title": "ReadAgain", "version": "1.0.0"},
                    "capabilities": {"experimentalApi": True},
                })
                await self._send({"method": "initialized", "params": {}})
                config = (await self._request("config/read", {"includeLayers": False})).get("config", {})
                if (
                    config.get("mcp_servers")
                    or config.get("model_provider") not in {None, "openai"}
                    or (config.get("model_providers") or {}).get("openai")
                    or config.get("chatgpt_base_url") not in {None, "https://chatgpt.com/backend-api", "https://chatgpt.com/backend-api/"}
                    or config.get("model_instructions_file")
                    or config.get("notify")
                ):
                    raise CodexUnavailable("An external runtime configuration prevents an isolated reading connection.")
            except asyncio.CancelledError:
                await self.close()
                raise
            except (OSError, TimeoutError, CodexUnavailable):
                await self.close()
                raise CodexUnavailable("The ChatGPT connection could not start. Check the installed Codex runtime.") from None

    async def _send(self, payload: dict):
        async with self._write_lock:
            if self.process is None or self.process.returncode is not None or self.process.stdin is None:
                raise CodexUnavailable("The ChatGPT connection stopped. Reconnect and try again.")
            try:
                self.process.stdin.write((json.dumps(payload, ensure_ascii=False) + "\n").encode())
                await self.process.stdin.drain()
            except (BrokenPipeError, ConnectionResetError):
                raise CodexUnavailable("The ChatGPT connection stopped. Reconnect and try again.") from None

    async def _request(self, method: str, params: dict | None = None):
        self._next_id += 1
        request_id = self._next_id
        future = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future
        try:
            await self._send({"id": request_id, "method": method, "params": params or {}})
            return await asyncio.wait_for(future, timeout=self.request_timeout)
        except TimeoutError:
            raise CodexUnavailable("ChatGPT took too long to respond. Please try again.") from None
        finally:
            self._pending.pop(request_id, None)
            if not future.done():
                future.cancel()
            elif not future.cancelled():
                future.exception()  # Consume a simultaneous disconnect/write failure.

    async def request(self, method: str, params: dict | None = None):
        await self.start()
        return await self._request(method, params)

    def subscribe(self, thread_id: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=256)
        self._subscriptions[thread_id] = queue
        return queue

    def unsubscribe(self, thread_id: str):
        self._subscriptions.pop(thread_id, None)
        self._active_turns.pop(thread_id, None)

    async def finish_thread(self, thread_id: str, turn_id: str | None, *, completed: bool):
        await asyncio.shield(self._schedule_cleanup(thread_id, turn_id, completed=completed))

    def _schedule_cleanup(self, thread_id: str, turn_id: str | None, *, completed: bool) -> asyncio.Task:
        if thread_id not in self._cleanup_tasks:
            task = asyncio.create_task(self._finish_thread(thread_id, turn_id, completed=completed))
            self._cleanup_tasks[thread_id] = task
            task.add_done_callback(lambda _: self._cleanup_tasks.pop(thread_id, None))
        return self._cleanup_tasks[thread_id]

    async def _finish_thread(self, thread_id: str, turn_id: str | None, *, completed: bool):
        if self.process is not None and self.process.returncode is None:
            try:
                async with asyncio.timeout(3):
                    active_id = turn_id or self._active_turns.get(thread_id)
                    if not completed and active_id is None:
                        # Cancellation may race the turn/start acknowledgment.
                        # Without an id we cannot confirm a targeted interrupt.
                        await self.close()
                        self.unsubscribe(thread_id)
                        return
                    if active_id and not completed:
                        await self._request("turn/interrupt", {"threadId": thread_id, "turnId": active_id})
                    await self._request("thread/unsubscribe", {"threadId": thread_id})
            except (CodexUnavailable, TimeoutError):
                # If an interrupt cannot be confirmed, stop the process rather
                # than leave a detached model turn consuming the user's quota.
                await self.close()
        self.unsubscribe(thread_id)

    def _fail_waiters(self):
        if self.login and self.login["state"] == "pending":
            self._finish_login(False)
        for future in self._pending.values():
            if not future.done():
                future.set_exception(CodexUnavailable("The ChatGPT connection stopped. Reconnect and try again."))
        for queue in self._subscriptions.values():
            # Failure must reach even a consumer that was temporarily slow.
            while queue.full():
                queue.get_nowait()
            queue.put_nowait({"method": "readagain/disconnected", "params": {}})

    async def _read_messages(self):
        process = self.process
        assert process is not None and process.stdout is not None
        try:
            while line := await process.stdout.readline():
                payload = json.loads(line)
                if not isinstance(payload, dict):
                    raise ValueError("Invalid protocol frame")
                if "id" in payload and "method" not in payload:
                    if not isinstance(payload["id"], (int, str)):
                        raise ValueError("Invalid response id")
                    future = self._pending.get(payload["id"])
                    if future is not None and not future.done():
                        if "error" in payload:
                            future.set_exception(CodexUnavailable("ChatGPT could not complete that request. Reconnect or try again."))
                        else:
                            result = payload.get("result", {})
                            if not isinstance(result, dict):
                                raise ValueError("Invalid response object")
                            future.set_result(result)
                    continue
                method = payload.get("method")
                params = payload.get("params") or {}
                if not isinstance(params, dict):
                    raise ValueError("Invalid notification")
                if "id" in payload:
                    # Never execute a client tool or accept an approval on the
                    # model's behalf. The reading connection has no such tools.
                    await self._send({"id": payload["id"], "error": {"code": -32601, "message": "Tools are unavailable in this reading connection."}})
                    continue
                if method == "account/login/completed" and isinstance(params.get("loginId"), str):
                    login_id = params["loginId"]
                    success = params.get("success") is True
                    # The notification can arrive immediately after the RPC
                    # response, before begin_login resumes to store its id.
                    self._login_results[login_id] = success
                    if len(self._login_results) > 16:
                        self._login_results.pop(next(iter(self._login_results)))
                    if self.login and login_id == self.login["login_id"]:
                        self._finish_login(success)
                thread_id = params.get("threadId")
                if isinstance(thread_id, str) and thread_id in self._subscriptions:
                    if method == "turn/started" and isinstance(params.get("turn", {}).get("id"), str):
                        self._active_turns[thread_id] = params["turn"]["id"]
                    queue = self._subscriptions[thread_id]
                    try:
                        queue.put_nowait(payload)
                    except asyncio.QueueFull:
                        # A slow browser must not disconnect other readers.
                        while not queue.empty():
                            queue.get_nowait()
                        queue.put_nowait({"method": "readagain/disconnected", "params": {}})
                        self._subscriptions.pop(thread_id, None)
                        self._schedule_cleanup(thread_id, None, completed=False)
                        logger.warning("A ChatGPT reading stream was stopped because its consumer fell behind")
        except asyncio.CancelledError:
            pass
        except (OSError, ValueError, CodexUnavailable) as error:
            # Exception strings and protocol frames may contain private text.
            logger.warning("ChatGPT protocol stream stopped (%s)", type(error).__name__)
        finally:
            self._fail_waiters()
            await self._stop_process(process)

    async def account(self) -> dict:
        result = await self.request("account/read", {"refreshToken": False})
        account = result.get("account") or {}
        return {"connected": account.get("type") == "chatgpt", "plan": account.get("planType")}

    async def begin_login(self) -> dict:
        async with self._login_lock:
            if self.login and self.login["state"] == "pending":
                if time.monotonic() < self.login["deadline"]:
                    return dict(self.login)
                await self._cancel_login()
            return await self._begin_login()

    def _finish_login(self, success: bool):
        if self.login:
            self.login["state"] = "completed" if success else "failed"
            self.login.pop("user_code", None)
            self.login.pop("verification_url", None)

    async def _begin_login(self) -> dict:
        from urllib.parse import urlsplit
        result = await self.request("account/login/start", {"type": "chatgptDeviceCode"})
        url = urlsplit(result.get("verificationUrl", ""))
        if result.get("type") != "chatgptDeviceCode" or url.scheme != "https" or url.netloc != "auth.openai.com" or url.path != "/codex/device" or url.query or url.fragment:
            raise CodexUnavailable("ChatGPT returned an unsupported sign-in flow. Please try again.")
        if any(not isinstance(result.get(key), str) or not 1 <= len(result[key]) <= 128 for key in ("userCode", "loginId")):
            raise CodexUnavailable("ChatGPT could not start sign-in. Please try again.")
        self.login = {"login_id": result["loginId"], "user_code": result["userCode"],
                      "verification_url": result["verificationUrl"], "state": "pending", "deadline": time.monotonic() + 600}
        if self.login["login_id"] in self._login_results:
            self._finish_login(self._login_results.pop(self.login["login_id"]))
        return dict(self.login)

    async def login_status(self, login_id: str) -> dict | None:
        async with self._login_lock:
            if not self.login or self.login["login_id"] != login_id:
                return None
            if self.login["state"] == "pending" and time.monotonic() >= self.login["deadline"]:
                await self._cancel_login()
                self.login["state"] = "expired"
            return dict(self.login)

    async def _cancel_login(self):
        if self.login and self.login["state"] == "pending":
            login_id = self.login["login_id"]
            self._finish_login(False)
            self.login["state"] = "cancelled"
            await self.request("account/login/cancel", {"loginId": login_id})

    async def cancel_login(self, login_id: str):
        async with self._login_lock:
            if self.login and self.login["login_id"] == login_id:
                await self._cancel_login()

    async def logout(self):
        async with self._login_lock:
            await self._cancel_login()
            await self.request("account/logout")
            self.login = None
            await self.close()

    @staticmethod
    async def _stop_process(process: asyncio.subprocess.Process):
        # npm's codex launcher creates a child. Killing only the launcher
        # leaves the runtime alive with open pipes (and hangs shutdown).
        if os.name == "posix":
            with suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
        elif process.returncode is None:
            with suppress(ProcessLookupError):
                process.kill()
        with suppress(TimeoutError):
            await asyncio.wait_for(process.wait(), 5)

    async def close(self):
        reader, process = self._reader, self.process
        if reader is not None and reader is not asyncio.current_task():
            reader.cancel()
            with suppress(asyncio.CancelledError):
                await reader
        if process is not None:
            await self._stop_process(process)
        self._reader = None
        self.process = None
        self._fail_waiters()


_runtime: CodexRuntime | None = None


def get_codex_runtime() -> CodexRuntime:
    from ...settings import settings
    global _runtime
    loop = asyncio.get_running_loop()
    if _runtime is None or _runtime.loop is not loop:
        _runtime = CodexRuntime([settings.chatgpt_codex_binary], Path(settings.chatgpt_state_dir))
    return _runtime


async def close_codex_runtime():
    if _runtime is not None and _runtime.loop is asyncio.get_running_loop():
        await _runtime.close()
