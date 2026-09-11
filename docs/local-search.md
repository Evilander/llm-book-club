# Local book search and memory

New installations use a CPU encoder for book passages and the reader’s earlier thoughts. ChatGPT, Claude, and other discussion providers receive the selected context; they do not own the library’s memory. Conversations remain in Postgres when you change discussion providers.

## Setup

Docker includes the CPU dependencies. The first book preparation downloads the public model weights into `embedding_models`, a volume shared by the API and worker. Later starts reuse that cache. Book text is encoded locally; the download does not upload your books or use a Hugging Face account.

For a Python installation, install the base requirements and then:

```bash
pip install torch==2.9.1 --index-url https://download.pytorch.org/whl/cpu
pip install -r apps/api/requirements-local.txt
```

Use these settings in `apps/api/.env`:

```env
EMBEDDINGS_PROVIDER=local
LOCAL_EMBEDDINGS_BASE_URL=
LOCAL_EMBEDDINGS_MODEL=Qwen/Qwen3-Embedding-0.6B
LOCAL_EMBEDDINGS_REVISION=97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3
LOCAL_EMBEDDINGS_DIMENSION=1024
```

The [model card](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B) documents its Apache 2.0 license, native 1,024 dimensions, and query instructions. ReadAgain pins the model revision, disables remote model code, loads safetensors, uses separate query/document prompts, and limits inputs to 2,048 tokens. CPU inference runs outside the web event loop, with one model instance and serialized inference per process.

`LOCAL_EMBEDDINGS_CACHE_DIR` selects the weight cache for Python installations. Docker sets it to the shared volume. `LOCAL_EMBEDDINGS_THREADS` defaults to four. A different CPU or competing workloads can change latency considerably.

## Existing books and changing models

Keep the API and worker’s embedding settings identical. Restart both after changing the provider, model, revision, dimensions, prompts, or input limit. Open an existing book’s overview and select **Refresh search & memory**. You can continue reading while the worker prepares the new vectors.

The refresh updates derived vectors in validated batches of 32. It preserves chunk IDs, original prose, citations, reading positions, sessions, and messages. It can resume after a failed batch and skips data already indexed with the chosen model. A repeated click reuses an active job.

Old installations did not record which model produced their vectors. Migration 009 keeps those vectors unlabelled instead of guessing from their dimensions. Full-text retrieval remains available; semantic retrieval resumes as passages are refreshed. The overview shows preparation progress and offers retry after failure.

Smaller native vectors are normalized and zero-padded into the existing 3,072-dimensional column. This preserves cosine similarity. Queries also filter by a SHA-256 identifier covering the complete encoder contract; vectors from different models are never compared just because their stored sizes match. The non-secret contract is recorded in `embedding_spaces`.

For an HTTP embedding server, set `LOCAL_EMBEDDINGS_BASE_URL`, its exact model name, native dimension, and an operator-maintained revision. Set `LOCAL_EMBEDDINGS_QUERY_PROMPT` and `LOCAL_EMBEDDINGS_DOCUMENT_PROMPT` to the server model’s documented prefixes. Change the revision whenever the server’s weights or encoding behavior changes. Hosted model aliases are provider-managed; ReadAgain cannot detect a provider silently changing the weights behind an unchanged model name.

## What is remembered

New reader messages receive derived embeddings when a discussion turn is prepared. The refresh also indexes earlier reader messages across the book’s sessions. Recall merges semantic and keyword matches, retaining up to six labelled thoughts alongside recent conversation. It reserves space for the reader’s starting point and latest earlier thought. Each recalled entry is capped at 600 characters; the complete message remains saved.

Book, edition, and reading-boundary filters apply before ranking or limiting memory candidates. Later-page conversations stay unavailable when you return to an earlier page. Legacy messages without position metadata become eligible at the end of the book. Memory is labelled as the reader’s own untrusted conversation, not book evidence; citations still require verified book spans. Retrieval is bounded and can miss a relevant detail—it is not a transcript of every previous turn in every prompt.

The query cache uses the model contract, query task, and full query hash as its key, with a one-hour TTL. A changed contract automatically gets a separate cache namespace. Raw queries and connection exception messages are not logged. If encoding or Redis fails, already prepared books remain readable with keyword recall and full-text passage retrieval. Preparing a new book still requires a working encoder.

## Verification

The regular Postgres suite verifies migration from unlabelled vectors, refresh preservation, model isolation, and filtering forbidden memories before ranking. Run the real local encoder separately:

```bash
cd apps/api
python -m evals.local_search --cache-dir .readagain/models
```

This uses an authored 18-passage literary fixture and ten paraphrased memory queries with distractors. It requires literary recall@5 ≥ 0.8, MRR ≥ 0.9, every target memory in the first three results, and warm CPU queries under two seconds. It prints model revision, timing, and retrieval metrics. It does not test live discussion quality, semantic support for generated claims, or arbitrary books.
