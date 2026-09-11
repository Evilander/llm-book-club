# Live reading evaluation

The opt-in `evals.live_reading` command exercises an actual model through the API, ingestion worker, search, saved conversation, margin notes, and streaming endpoints. It uploads an original three-chapter miniature. It never imports a personal book, reads provider credentials, or signs into an account.

Use a separate local test library. The command creates a book and two sessions, leaves them available for inspection, and invokes whichever discussion provider that library has selected. Start the API and worker with the same isolated database, storage, Redis, and embedding configuration; see [development](development.md) and [local search](local-search.md). For the deliberately short recent-history test, set `MAX_HISTORY_MESSAGES=2` on the API. Saved thoughts must then supply the older image in the later session.

For an Ollama model that supports disabling reasoning, one tested configuration is:

```dotenv
LLM_PROVIDER=local
LOCAL_LLM_BASE_URL=http://localhost:11434/v1
LOCAL_LLM_MODEL=qwen3:8b
LOCAL_LLM_REASONING_EFFORT=none
MAX_HISTORY_MESSAGES=2
MAX_TOKENS_PER_TURN=2048
```

Select **Local model** in the test library if it has a saved provider selection. The model must already be installed on its server. `LOCAL_LLM_REASONING_EFFORT=provider`, the default, omits the optional field for compatibility with other servers. Values are model dependent: Ollama exposes `reasoning_effort` on its [compatible chat endpoint](https://docs.ollama.com/api/openai-compatibility), and its [thinking guide](https://docs.ollama.com/capabilities/thinking) explains that some models, including GPT-OSS, cannot disable reasoning entirely. Restart the API and worker after configuration changes.

The project's regular Compose file takes the local model and reasoning setting from Compose interpolation variables. To use its Ollama service, set `LOCAL_LLM_MODEL=qwen3:8b` and `LOCAL_LLM_REASONING_EFFORT=none` in the shell or Compose `.env`, alongside `LLM_PROVIDER=local` in `apps/api/.env`. The default container URL is `http://ollama:11434/v1`. Use a separate Compose project and library for evaluation.

From `apps/api`, with the base requirements installed:

```bash
python -m evals.live_reading \
  --base-url http://127.0.0.1:58000 \
  --model-label 'qwen3:8b, reasoning none, record server version and hardware separately' \
  --output /tmp/readagain-live-reading.json
```

The command accepts only a credential-free loopback API URL. It does not bypass application authentication. The output contains the authored story's generated discussion, timing, citation metadata, and evaluation record IDs. It is not a production log or a transcript exporter.

## Checks and interpretation

The command exits unsuccessfully if a request fails or any recorded check fails. The deterministic checks cover:

- At least one real page anchor on the evaluation's first page, and reuse of those verified cached notes.
- Completed streams, first visible prose within 15 seconds by default, and exact citation offsets within the selected reading boundary.
- Citations on substantive evaluation replies, a brief pause acknowledgment, and no repetition of the same club answer after citation markers and punctuation are removed.
- Recall of the reader's earlier metaphor in another session, with no invented citation of that metaphor as book text.
- Absence of the planted instruction's output phrase and the unread ending's identifying details.

Read the transcript as well. Keyword checks cannot prove that a response answered the question, respected every spoiler boundary, or ignored all possible attacks. Exact quotes do not prove that they support the associated interpretation. The reader-image check intentionally asks for the earlier image; a broad paraphrase can be useful without repeating it. Distinct wording does not establish distinct club contributions. The report includes specific human-review questions for these limitations.

Cold model loading is included in the margin request's duration. Discussion timing begins at the HTTP request and includes search and memory work; first visible prose excludes hidden reasoning and JSON framing. Final response time includes citation repair. This is a small local regression exercise, not a whole-book memory benchmark, a provider comparison, or a ChatGPT account certification.

## Failures this exercise exposed

The original prompts displayed an invalid JSON example and pushed the companions toward constant enthusiasm. Plain replies with citation numbers could bypass citation verification. Saved assistant prose also encouraged subsequent replies to drop the response format, while book-club turns could be sent as a continuation of the previous voice. The revised turn context, quieter guidance, valid example, and unresolved-marker repair address those failures.

A reasoning model exhausted the margin's 650-token allowance without producing answer text. The app previously cached that as a successful empty margin. Blank, malformed, truncated, or entirely ungrounded output now fails visibly and remains retryable; a valid `{"notes":[]}` still means the model intentionally left the margin empty. See [the cache and grounding contract](grounding-and-reading-boundaries.md).

## Recorded local run

On September 11, 2026, the nine-turn exercise passed all 42 deterministic checks with Qwen3 8B Q4_K_M, Ollama 0.34.0, a 16,384-token context, reasoning disabled, and an RTX 4080 Super. Local Qwen3 embeddings prepared the authored EPUB in 11.1 seconds. Margin generation took 1.9 seconds; median first visible prose was 0.83 seconds, with a maximum of 5.73 seconds. Ten agent replies carried eleven verified quotations in total. The pause response was five words. The earlier metaphor returned in a new session, and Ellis contributed a different detail in the final club exchange.

Human review still found weaknesses: occasional praise, confident interpretations of ambiguous gestures, and details such as the room's "coldness" that the supplied text did not establish. This small model remains an evaluation target rather than a validated quality recommendation. The run also encountered an earlier GPU startup timeout, which remained retryable; the recorded successful run used Ollama's CUDA 12 library after restarting the isolated model container. These results do not establish reliable cold-start latency or the quality of other providers.
