# Product direction

ReadAgain is a quiet place to read a book with a thoughtful companion. The book gets the most space. The companion can notice passages, remember the reader's earlier thoughts, and make room for a book-club discussion.

## Product requirements

| Requirement | Evidence needed before calling it complete |
| --- | --- |
| Quiet, convincing paper and page turns | Desktop and phone checks with real imported books, all five paper choices, reflow, reduced motion, and saved position. |
| Optional Bionic text | Saved intensity, accessible controls, and exact preservation of quotes, punctuation, and reading position. |
| A companion beside the page | A real provider streams into the sidebar; page context follows the reader; failed requests can recover without duplicating turns. |
| Questions anchored in the book | Every highlighted quote is an exact allowed span; fabricated IDs, reordered words, and out-of-slice evidence fail verification. |
| Memory across a whole book | Earlier thoughts survive session rotation and restarts; the model can recall relevant discussion without treating it as evidence or revealing unread text. |
| Book-club conversations | Distinct, useful perspectives with visible speakers, grounded citations, bounded latency, and bounded cost. |
| Simple provider connection | Clear supported sign-in or key configuration; ChatGPT first and Claude second where a supported native integration exists. |
| A dependable local library | A fresh checkout starts, imports PDF/EPUB/TXT, persists state, and upgrades without losing books or silently skipping schema changes. |
| Privacy | Local services stay on loopback by default. Credentials, private books, personal notes, and workstation paths stay out of commits and public artifacts. |

## Current engineering priorities

Installation, migrations, ingestion, and the complete discussion path now have reproducible checks against real Postgres and Redis, with a deterministic HTTP provider.

1. Tighten discussion citation verification. The older fuzzy word-overlap fallback is insufficient proof of a quotation, even though margin questions already require exact spans.
2. Enforce the current reading boundary in retrieval and memory, including re-reading and returning to earlier pages.
3. Make provider setup and embedding-model compatibility work end to end; evaluate supported native sign-in and verify a live conversation.
4. Improve long-book recall and reader control over saved memory, backed by realistic retrieval and discussion evaluations.
5. Complete release checks for privacy, dependency maintenance, backup/restore, and the repository's canonical branch.

The existing browser fixture is useful UI evidence. The HTTP provider fixture proves transport, persistence, and retrieval plumbing. Neither is evidence of live model quality. Keep that distinction in release notes.

The deployment target is one person's local library. Hosting unrelated users requires a separate authorization and ownership design before it can be offered.
