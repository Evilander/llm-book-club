# Connect ChatGPT

Choose **Read with me** beside a book, or open **Settings → Connect & read with ChatGPT**, copy the displayed code, and follow **Continue at OpenAI**. Approve the connection there. The library selects ChatGPT after sign-in completes; the choice survives restarts. Choose **Continue reading** to return to the same page and draft. Cancelled or expired sign-ins leave the previous provider selected. If a connection is missing during a discussion, **Connect a reading partner** opens the same setup without leaving the book.

This uses the Codex access available to your ChatGPT account and its usage limits. If OpenAI requests it, enable device-code sign-in in your ChatGPT security settings. Availability can depend on your plan and workspace policy. The connection uses OpenAI's managed [App Server authentication flow](https://learn.chatgpt.com/docs/app-server), described further in the [authentication documentation](https://learn.chatgpt.com/docs/auth).

Book search and memory use the bundled CPU encoder by default, with no embedding API key. Existing installations retain their configured embedding provider. Voice keeps its own settings. See [local search and memory](local-search.md) for setup and refreshing existing books.

## Installation

The Docker image includes Codex CLI **0.154.0**. A dedicated `chatgpt_state` volume holds the runtime's connection files. The API and ingestion worker share this volume; uploaded books use a separate volume. Do not mount your personal coding profile into the app.

For a non-Docker installation, install the same runtime version in an app-owned directory from the repository root:

```bash
npm install --prefix .readagain/runtime --ignore-scripts --no-audit --no-fund @openai/codex@0.154.0
```

Set `CHATGPT_CODEX_BINARY` in `apps/api/.env` to the absolute path of `.readagain/runtime/node_modules/.bin/codex`. The default `CHATGPT_STATE_DIR=.readagain/chatgpt` is relative to the API's working directory. Use the same absolute state directory for the API and worker when running them separately. The app initializes only an empty directory or its own previously managed profile, and rejects the personal Codex home.

The runtime is version-pinned because disabling workspace access uses the experimental `environments: []` App Server field. Upgrading requires testing the generated protocol and packaged runtime together. A different CLI version fails with a connection setup error.

`FRONTEND_APP_URL` and `CORS_ORIGINS` must match the origin you use in the browser, including the port. Connection actions require an exact allowed Origin and the app's settings request header. This protects local browser actions against cross-site requests; the application remains a single-owner local library, not a multi-user hosted service.

## Memory and privacy

Reading history, margin questions, and book memory remain in the library database. Connecting ChatGPT does not import other ChatGPT or Codex conversations. Every reply starts a separate ephemeral native thread with only the context supplied by ReadAgain. The database remains the source of book memory across sessions and model changes.

The runtime uses its own credential directory with owner-only permissions. Credentials are managed by the runtime and are never sent to the frontend, stored in the library configuration table, or copied from a personal coding profile. The app excludes API keys from the runtime's environment. Ephemeral threads do not write native conversation rollouts; provider-side data handling still applies to the passages and conversation sent for a reply.

Reading turns have no workspace environment. Shell, file, browsing, app, plugin, and native memory tools are disabled. Native client tool/approval requests are rejected. A model may advertise its internal clock or request-for-input tool; these do not grant workspace access.

Disconnecting removes the local runtime connection and stops its active API-process replies. It keeps ChatGPT selected, so future reading requests require reconnection instead of silently falling back to an API key. An already running ingestion job is a separate worker process and may finish its current task. To revoke account access beyond this installation, use your OpenAI account controls.

## Limits and verification

`CHATGPT_MODEL` optionally selects an available account model. Omit it to use the runtime's default model. The app requests low reasoning effort when supported.

App Server does not expose an output-token cap or sampling temperature in this protocol. ReadAgain applies a response-character limit, a default 90-second turn timeout, and interruption on cancelled requests. These limit runaway work but are not a precise token or spending cap. Reported usage comes from the runtime's actual token counts. ChatGPT plan limits continue to apply.

The test suite covers device-code state, expiry, first-party request checks, provider persistence, cancellation, queue isolation, and the browser flow. The packaged-runtime check uses a synthetic local model response and confirms streaming, usage, separate book contexts, absence of native rollouts, and the exposed tool set. It does not establish live account access, model quality, or real-provider latency.

## Local models and connection checks

For a local model server, set `LLM_PROVIDER=local`, `LOCAL_LLM_BASE_URL` to its OpenAI-compatible `/v1` endpoint, and `LOCAL_LLM_MODEL` to an installed model ID. The default is `llama3.2`. Explicit IDs, including `gpt-oss` variants, are passed through unchanged. With the bundled Ollama service, run `docker compose --profile local up -d ollama` and `docker compose exec ollama ollama pull llama3.2` (substitute your chosen model) before selecting **Local model** in Settings. These variables can also be set in the repository-root Compose `.env` when overriding Docker defaults.

Connection checks read the local server's [`/v1/models` list](https://docs.ollama.com/api/openai-compatibility); they do not load a model or generate text. An absent server or missing model offers setup instead of showing a connected badge. API-key providers are checked for configuration only, without billable validation requests. A configured key or reachable local model can still encounter account, capacity, or inference errors during a reply.

`POST /v1/providers/reading-status` returns `{provider, connected, message}` with the same first-party header and Origin checks as connection changes. Generative reading endpoints return HTTP 409 with `detail.code = "reading_connection_required"` when prerequisites are missing, before saving a new reader turn or opening an SSE stream. Page/edition conflicts keep their existing response. Cached margin notes and saved conversation history remain readable without a model connection. A failure after a turn has started still requires checking the saved conversation before retrying.
