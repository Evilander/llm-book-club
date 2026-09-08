"use client";

/**
 * ReadAgain global library search.
 *
 * Compact icon-button in the top nav that opens a fixed overlay panel
 * with a debounced search input and results grouped by source.
 *
 *   - "ingested" rows link to the discussion / reader for the existing book.
 *   - "library" rows trigger ingestion via /v1/library/local/ingest and then
 *     route to the new book once ingestion is queued.
 *
 * Keyboard:
 *   - Cmd/Ctrl+K toggles the overlay.
 *   - Enter selects the first result.
 *   - Esc closes.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { API_BASE } from "@/lib/utils";
import type { LibrarySearchResponse, LibrarySearchResult } from "@/types/api";

interface State {
  q: string;
  loading: boolean;
  error: string | null;
  data: LibrarySearchResponse | null;
}

const INITIAL: State = { q: "", loading: false, error: null, data: null };

export function GlobalSearch() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [state, setState] = useState<State>(INITIAL);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  // Global Cmd/Ctrl+K toggle
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((v) => !v);
      } else if (e.key === "Escape" && open) {
        setOpen(false);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  // Focus input when overlay opens
  useEffect(() => {
    if (open) {
      const id = window.setTimeout(() => inputRef.current?.focus(), 30);
      return () => window.clearTimeout(id);
    }
    return undefined;
  }, [open]);

  // Debounced fetch as user types
  useEffect(() => {
    if (!open) return;
    const q = state.q.trim();
    if (q.length < 2) {
      setState((s) => ({ ...s, data: null, error: null, loading: false }));
      return;
    }
    const handle = window.setTimeout(() => {
      abortRef.current?.abort();
      const ctrl = new AbortController();
      abortRef.current = ctrl;
      setState((s) => ({ ...s, loading: true, error: null }));
      fetch(`${API_BASE}/v1/library/search?q=${encodeURIComponent(q)}&limit=24`, {
        signal: ctrl.signal,
      })
        .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`${r.status}`))))
        .then((data: LibrarySearchResponse) => {
          setState((s) => ({ ...s, data, loading: false }));
        })
        .catch((err: unknown) => {
          if ((err as { name?: string })?.name === "AbortError") return;
          setState((s) => ({ ...s, error: String(err), loading: false }));
        });
    }, 220);
    return () => window.clearTimeout(handle);
  }, [state.q, open]);

  const selectResult = useCallback(
    async (r: LibrarySearchResult) => {
      setOpen(false);
      if (r.source === "ingested" && r.book_id) {
        router.push(`/books/${r.book_id}`);
        return;
      }
      if (r.source === "library" && r.path) {
        // Queue ingestion, then route to the resulting book id when known
        try {
          const res = await fetch(`${API_BASE}/v1/library/local/ingest`, {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify({ path: r.path }),
          });
          if (res.ok) {
            const j = await res.json();
            if (j?.book_id) {
              router.push(`/books/${j.book_id}`);
              return;
            }
          }
        } catch {
          /* swallow — surface via the shelf */
        }
        router.push("/");
      }
    },
    [router]
  );

  const onSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault();
      const first = state.data?.results?.[0];
      if (first) selectResult(first);
    },
    [state.data, selectResult]
  );

  const grouped = useMemo(() => {
    const ingested = state.data?.results.filter((r) => r.source === "ingested") ?? [];
    const library = state.data?.results.filter((r) => r.source === "library") ?? [];
    return { ingested, library };
  }, [state.data]);

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="readagain-search-trigger"
        aria-label="Search the library (Cmd+K)"
        title="Search the library  ⌘K"
      >
        <svg width="14" height="14" viewBox="0 0 16 16" stroke="currentColor" strokeWidth="1.4" fill="none" strokeLinecap="round">
          <circle cx="7" cy="7" r="4.5" />
          <path d="M10.5 10.5 L14 14" />
        </svg>
        <span className="readagain-search-trigger-label">Search</span>
        <span className="readagain-search-trigger-kbd">⌘K</span>
      </button>

      {open ? (
        <div
          className="readagain-search-overlay"
          role="dialog"
          aria-modal="true"
          aria-label="Library search"
          onClick={(e) => {
            if (e.target === e.currentTarget) setOpen(false);
          }}
        >
          <div className="readagain-search-panel">
            <form onSubmit={onSubmit} className="readagain-search-form">
              <svg width="16" height="16" viewBox="0 0 16 16" stroke="currentColor" strokeWidth="1.4" fill="none" strokeLinecap="round" aria-hidden="true">
                <circle cx="7" cy="7" r="4.5" />
                <path d="M10.5 10.5 L14 14" />
              </svg>
              <input
                ref={inputRef}
                type="search"
                value={state.q}
                onChange={(e) => setState((s) => ({ ...s, q: e.target.value }))}
                placeholder="Find a book by title or author…"
                className="readagain-search-input"
                autoComplete="off"
                spellCheck={false}
              />
              <button type="button" onClick={() => setOpen(false)} className="readagain-search-close" aria-label="Close">
                Esc
              </button>
            </form>

            <div className="readagain-search-meta">
              {state.loading
                ? "searching…"
                : state.data
                ? `${state.data.total} matches  ·  ${state.data.ingested_count} ingested  ·  ${state.data.library_count} on disk`
                : state.q.trim().length < 2
                ? "type at least two characters"
                : "no matches"}
              {state.error ? `  ·  ${state.error}` : null}
            </div>

            <div className="readagain-search-results">
              {grouped.ingested.length > 0 ? (
                <div className="readagain-search-group">
                  <div className="readagain-search-group-label">on the shelf</div>
                  {grouped.ingested.map((r, idx) => (
                    <ResultRow key={`i-${idx}`} r={r} onSelect={selectResult} />
                  ))}
                </div>
              ) : null}
              {grouped.library.length > 0 ? (
                <div className="readagain-search-group">
                  <div className="readagain-search-group-label">in your library on disk</div>
                  {grouped.library.map((r, idx) => (
                    <ResultRow key={`l-${idx}`} r={r} onSelect={selectResult} />
                  ))}
                </div>
              ) : null}
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}

function ResultRow({
  r,
  onSelect,
}: {
  r: LibrarySearchResult;
  onSelect: (r: LibrarySearchResult) => void;
}) {
  return (
    <button type="button" className="readagain-search-row" onClick={() => onSelect(r)}>
      <div className="readagain-search-row-title">
        <span>{r.title}</span>
        {r.extension ? <span className="readagain-search-row-ext">.{r.extension}</span> : null}
      </div>
      <div className="readagain-search-row-meta">
        {r.author ? <span>{r.author}</span> : null}
        {r.author && r.parent_folder ? <span className="readagain-search-row-dot">·</span> : null}
        {r.parent_folder ? <span>{r.parent_folder}</span> : null}
        {r.audiobook_count > 0 ? (
          <>
            <span className="readagain-search-row-dot">·</span>
            <span className="readagain-search-row-audiobook">audiobook</span>
          </>
        ) : null}
      </div>
      <div className="readagain-search-row-action">
        {r.source === "ingested" ? "open →" : "ingest →"}
      </div>
    </button>
  );
}
