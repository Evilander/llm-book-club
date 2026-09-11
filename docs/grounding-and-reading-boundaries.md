# Grounding and the current page

The companion should follow the page the reader is looking at. Three implementation details undermined that: quotation verification accepted unordered word overlap, reused sessions accumulated later chapters, and structured model responses streamed their JSON syntax into the conversation. These checks now sit on the server and apply to both synchronous and streamed replies.

## Quotation contract

A verified citation contains the original chunk text and zero-based, exclusive-end Python character offsets:

```json
{
  "chunk_id": "source-chunk-id",
  "text": "The lamp was lit.",
  "char_start": 0,
  "char_end": 17,
  "verified": true,
  "match_type": "exact"
}
```

The server enforces `citation.text == chunk.text[char_start:char_end]`. A quote must be contiguous, within the authorized chunk and current reading boundary, and start and end at grapheme boundaries. The original database text is never normalized or rewritten.

Matching permits Unicode NFKC normalization, case folding, and collapsed whitespace. A normalized match is mapped back to the complete original graphemes and checked again. This supports ligatures, decomposed accents, and differing whitespace without accepting shuffled words, changed negations, or a substring of a ligature. The distinction between code points and user-perceived characters follows [Unicode's text segmentation specification](https://www.unicode.org/reports/tr29/). JavaScript consumers convert strings with `Array.from` before using these code-point offsets.

Chunk IDs and offsets supplied by a model are untrusted. Supplied offsets must be integers, in range, and match the quotation; invalid offsets are not silently repaired by guessing a different location. A historical citation with null offsets can be aligned again. Model-supplied `verified` and `match_type` values are ignored. The old fuzzy word-overlap path has been removed.

The primary response format remains `{analysis, citations}` with numbered markers. Both it and legacy `[cite: ...]` responses go through the same verifier. Unresolved or duplicate numbered references fail verification. One bounded repair call can correct invalid citations using the allowed evidence. If any citation remains invalid, the final reply is replaced with a short explanation inviting another look at the page. Repair instructions are a system message; the prior response, invalid citations, and evidence are untrusted JSON data in a user message.

History responses reverify saved citations, including old records marked as fuzzy matches. They load all needed source chunks in one query and preserve each message's citation markers. No saved conversation is deleted by this check.

## Pinning a turn to an edition

All reader endpoints use one canonical assembly of the chunks, ordered by section, chunk order, source start, and ID. Reading queries load prose and coordinates, excluding embedding arrays. An edition is the SHA-256 of the UTF-8 assembled reading text.

The additive API fields are:

| Endpoint | Change |
| --- | --- |
| `GET /v1/books/{id}/reader` | Returns `edition_id` with the page. |
| `POST /v1/books/{id}/companion` | Accepts optional `edition_id` alongside `page`, `page_size`, and `section_ids`; returns `reading_position`. |
| `POST /v1/sessions/{id}/message` and `/message/stream` | Accept optional `reading_position: {page, page_size, edition_id}`. The reader sends it on every turn. |
| `GET /v1/sessions/{id}/messages` | Accepts the same fields as query parameters; companion history is filtered to that position. |
| `POST /v1/books/{id}/reader-notes` | Accepts optional `edition_id` and rejects a changed edition. |

Companion positions use pages starting at 1 and page sizes from 200 to 4,000 characters. Edition IDs are 64 lowercase hexadecimal characters. A stale edition or missing usable companion position returns HTTP 409 before inference. The interface can reopen the page and reconnect. Older clients can omit the position and use the last saved companion position; they do not get the new client's protection against another tab changing that position.

The server derives the current page boundary; it does not accept arbitrary source offsets from the browser. Each new message records `metadata_json.reading_scope = {edition_id, char_end}`. This needs no schema migration. The scope is fixed when the engine is constructed, so another tab cannot change an in-flight turn's context by updating session preferences.

For the page companion, retrieval can use the book's prefix through the end of the displayed page. For a book-club session, evidence remains restricted to its selected sections. Candidate chunk IDs are filtered in SQL, and a chunk straddling the page boundary is clipped before reranking, prompt assembly, or repair. Initial page/slice evidence and retrieved passages share `MAX_CONTEXT_TOKENS * 4` characters; half is reserved for initial evidence. This is an approximate token budget for source text, not a precise provider count or a cap on the entire prompt.

## Memory when returning to an earlier page

Before model input is assembled, conversation history and native book recall exclude messages recorded beyond the current boundary or in a different edition. This filtering happens before the history limit. Earlier reader thoughts remain available even when their session later visits other chapters. Recall merges semantic and keyword matches into up to six saved reader thoughts, labelled as conversation rather than book evidence. See [local search and memory](local-search.md) for ranking, limits, and model provenance.

Old messages without reading provenance stay in the database. They are available to inference once the current reading boundary reaches the end of the book. Existing aggregate book summaries also lack trustworthy page provenance, so they are withheld before that point. This intentionally avoids guessing where an old thought or summary belongs; it does not erase the reader's memory.

Margin notes are cached as hidden session messages. Their key hashes `margin-v3`, edition, page, page size, and page text. They have no time-based expiry and last with the session. A changed edition/page/size produces a different key; session deletion removes its cached notes. Conversation changes do not regenerate an already annotated page. Notes are limited to two, and each anchor must match an exact span of that page. Empty or malformed model output, and nonempty candidates with no verified anchors, return a retryable HTTP 503 without caching. A valid `{"notes":[]}` remains an intentional empty margin. Version 3 invalidates earlier cached failures that were indistinguishable from an intentional empty margin.

## Streaming and playback

An incremental parser emits only the decoded top-level `analysis` string, including escaped Unicode and split surrogate pairs. It handles structured JSON, fenced JSON, and the legacy plain-text path. Citation JSON never becomes visible prose. A malformed structured response produces a recoverable final message.

Text deltas remain provisional. The final `message_end` replaces them with the citation-checked or repaired response. Sentence events use that finalized text and arrive immediately before `message_end`, so audio starts later but cannot speak an unverified draft quotation. The backend advertises sentence events and the frontend does not fall back to reading raw deltas on this protocol.

Changing pages unmounts the previous conversation and aborts its browser request while the new position loads. The old history cannot linger beside an earlier page. Aborting the browser does not promise server-side cancellation or rollback; saved turns can be reloaded at an eligible position.

## Verification and remaining limits

Deterministic tests cover real quote/span alignment, forged offsets and IDs, reordered words, combining marks, ligatures, malformed references, failed repair, and retrieval restricted before reranking. A history test verifies that multiple messages share one source query. Budget tests reject an oversized passage bypass and preserve source text when clipping.

SQLite API tests exercise two tabs moving through one companion session, edition changes, and saved history. The separate Postgres/Redis/HTTP workflow uploads generated TXT, EPUB, and PDF documents, runs the real ingestion worker, discusses a later page, returns to an earlier position, and inspects the actual provider request. Later-page markers and thoughts must be absent. Streamed prose must equal the checked final response for these valid fixtures. The browser suite checks loading isolation, recovery, citation navigation, paper choices, and Bionic text.

These are boundary and transport guarantees. They do not establish that every interpretation is supported by its citation, that a model will never invent a claim, or that a model's pretraining cannot reveal later events. Provisional text can still be corrected at the end. Native provider citation formats could strengthen generation; for example, [Claude's citation API](https://platform.claude.com/docs/en/build-with-claude/citations) supports source-linked citations, but this app has not integrated it yet.

Remaining work includes broader live-provider quality and latency evaluation, claim-level grounding, sustained long-book memory evaluation, and durable turn replay. Full-chunk embedding/FTS scores can be influenced by the unread tail of a boundary chunk even though that tail never reaches reranking or generation. Whole-book assembly still occurs per request.

The proposed reading cache first needs a `books.reading_revision BIGINT NOT NULL DEFAULT 0` incremented in the same transaction that publishes a completed ingestion; every later chunk edit must increment it too. Each request would check the book's revision/status before using `reading:v1:{book_id}:{reading_revision}`. A process-local LRU capped at four entries/64 MiB, expiring after 60 seconds, would store assembled text, coordinates, and its edition hash and skip oversized entries. Revision changes, deletion, and non-completed ingestion bypass old entries immediately across all workers; TTL evicts abandoned entries. This would save repeated chunk loading and assembly. It is a follow-up design, not an implemented cache.

CodeRabbit reviewed this change. Its repeated citation-query, combined evidence-budget, and stale TTS-documentation findings were addressed. Its whole-book cache recommendation is retained as the revision-aware follow-up above.
