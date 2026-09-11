"""Offline JSONL peer for connection lifecycle tests. Contains no credentials."""
import json
import os
import sys
import time

if "--version" in sys.argv:
    print("codex-cli 0.154.0")
    raise SystemExit


def emit(value):
    print(json.dumps(value), flush=True)


connected = False
options = {}
for line in sys.stdin:
    request = json.loads(line)
    method = request.get("method")
    if "id" not in request:
        continue
    if "error" in request:
        emit({"method": "fixture/toolRejected", "params": {"threadId": "tools"}})
        continue
    result = {}
    if method == "fixture/setup":
        options.update(request["params"])
    elif method == "fixture/environment":
        result = {"inherited_api_key": "OPENAI_API_KEY" in os.environ, "inherited_home": "HOME" in os.environ, "codex_home": os.environ["CODEX_HOME"]}
    elif method == "fixture/error":
        emit({"id": request["id"], "error": {"message": "PRIVATE_TOKEN_CANARY"}})
        continue
    elif method == "fixture/tool":
        emit({"id": "native-tool", "method": "item/tool/call", "params": {"threadId": "tools", "arguments": "do not execute"}})
    elif method == "fixture/flood":
        emit({"method": "turn/started", "params": {"threadId": "slow", "turn": {"id": "slow-turn"}}})
        for index in range(260):
            emit({"method": "item/agentMessage/delta", "params": {"threadId": "slow", "delta": "fixture"}})
        emit({"method": "fixture/healthy", "params": {"threadId": "healthy"}})
    elif method == "fixture/crash":
        raise SystemExit(1)
    elif method == "fixture/hang":
        time.sleep(60)
    elif method == "config/read":
        result = {"config": {"model_provider": "openai", "mcp_servers": {}}}
    elif method == "account/read":
        result = {"account": {"type": "chatgpt", "email": "fixture@example.com", "planType": "plus"} if connected else None}
    elif method == "account/login/start":
        if options.get("early_complete"):
            connected = True
            emit({"method": "account/login/completed", "params": {"loginId": "fixture-login", "success": True}})
        result = {"type": "chatgptDeviceCode", "loginId": "fixture-login", "userCode": "TEST-CODE", "verificationUrl": options.get("url", "https://auth.openai.com/codex/device")}
    elif method == "account/logout":
        connected = False
    emit({"id": request["id"], "result": result})
