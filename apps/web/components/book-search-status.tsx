"use client";

import { useEffect, useRef, useState } from "react";
import { API_BASE } from "@/lib/utils";
import { connectionRequest } from "@/components/chatgpt-connection";

type IndexStatus = { ready: boolean; local: boolean; state: string; passages: number; passages_ready: number; thoughts: number; thoughts_ready: number };
const working = new Set(["queued", "started", "scheduled", "deferred"]);

export function BookSearchStatus({ bookId }: { bookId: string }) {
  const [status, setStatus] = useState<IndexStatus | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const operation = useRef<AbortController | null>(null);

  useEffect(() => {
    setBusy(false);
    setError("");
    return () => operation.current?.abort();
  }, [bookId]);

  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    setStatus(null);
    async function load() {
      try {
        const response = await fetch(`${API_BASE}/v1/books/${bookId}/search-index`, { signal: controller.signal, cache: "no-store" });
        if (!response.ok) throw new Error("Search status is unavailable.");
        const next: IndexStatus = await response.json();
        if (controller.signal.aborted) return;
        setStatus(next);
        if (working.has(next.state)) timer = setTimeout(load, 3000);
      } catch {
        if (!controller.signal.aborted) {
          setStatus(null);
          setError("We couldn’t check book search. Try again in a moment.");
        }
      }
    }
    void load();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [bookId, attempt]);

  async function refresh() {
    const controller = new AbortController();
    operation.current = controller;
    setBusy(true);
    setError("");
    try {
      await connectionRequest(`books/${bookId}/search-index`, {}, controller.signal);
      if (!controller.signal.aborted) setAttempt((n) => n + 1);
    } catch (failure) {
      if (!controller.signal.aborted) setError(failure instanceof Error ? failure.message : "Search could not be refreshed.");
    } finally { if (!controller.signal.aborted) setBusy(false); }
  }

  if (status?.ready || (!status && !error)) return null;
  const preparing = status && working.has(status.state);
  return <div className="book-search-status">
    {error ? <p role="alert">{error}</p> : preparing ? <p role="status">Remembering this book… {status.passages_ready + status.thoughts_ready} of {status.passages + status.thoughts} passages and thoughts ready. You can keep reading.</p> : <p>Refresh search to help your companion connect passages with your earlier thoughts.{status?.local ? " This runs locally." : " This uses your configured embedding provider."}</p>}
    {!preparing ? <button className="text-link" disabled={busy} onClick={() => status ? void refresh() : (setError(""), setAttempt((n) => n + 1))}>{busy ? "Preparing…" : status ? "Refresh search & memory" : "Check again"}</button> : null}
  </div>;
}
