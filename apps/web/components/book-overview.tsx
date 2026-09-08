"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowLeft, ArrowRight, BookOpen, Loader2, Users } from "lucide-react";
import { API_BASE } from "@/lib/utils";
import { SessionSetup } from "@/components/session-setup";
import type { ExplorePayload } from "@/types/api";

export function BookOverview({ bookId, onStartSession }: { bookId: string; onStartSession: (sessionId: string) => void }) {
  const [book, setBook] = useState<ExplorePayload | null>(null);
  const [sectionId, setSectionId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [customize, setCustomize] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setError(null);
    fetch(`${API_BASE}/v1/books/${bookId}/explore`, { signal: controller.signal })
      .then(async (res) => { if (!res.ok) throw new Error("This book is not ready to open yet. Please try again."); return res.json() as Promise<ExplorePayload>; })
      .then((data) => { setBook(data); setSectionId(data.progress?.resume_section_id || data.active_section?.id || data.sections[0]?.id || ""); })
      .catch((err) => { if (err.name !== "AbortError") setError("We couldn’t open this book. Check your connection and try again."); });
    return () => controller.abort();
  }, [bookId, attempt]);

  async function startClub() {
    if (!sectionId || starting) return;
    setStarting(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE}/v1/sessions/start`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ book_id: bookId, mode: "conversation", section_ids: [sectionId], time_budget_min: 20,
          discussion_style: "cozy", experience_mode: "text", reader_goal: "Read closely together. Stay within the selected chapter, make room for my thoughts, and ground observations in quoted passages." }),
      });
      const data = await response.json();
      if (!response.ok || !data.session_id) throw new Error("The book club couldn’t start. Please try again.");
      onStartSession(data.session_id);
    } catch { setError("The book club couldn’t start. Please try again."); }
    finally { setStarting(false); }
  }

  return (
    <div className="book-overview">
      <Link href="/#library" className="text-link"><ArrowLeft size={15} /> Your library</Link>
      {!book && !error ? <p role="status" className="overview-loading">Opening your book…</p> : null}
      {error ? <div className="library-notice" role="alert"><p>{error}</p><button className="text-link" onClick={() => book ? void startClub() : setAttempt((n) => n + 1)} disabled={starting}>Try again</button></div> : null}
      {book ? <>
        <header className="overview-title"><p className="quiet-eyebrow">A book worth spending time with</p><h1>{book.title}</h1>{book.author ? <p>{book.author}</p> : null}</header>
        <div className="overview-options">
          <section><BookOpen size={25} strokeWidth={1.3} aria-hidden="true" /><h2>One page at a time.</h2><p>Settle into the book. Your reading companion is a tap away whenever a sentence makes you stop and think.</p><Link href={`/books/${bookId}/read`} className="reading-button">Open the book <ArrowRight size={16} /></Link></section>
          <section><Users size={25} strokeWidth={1.3} aria-hidden="true" /><h2>Let’s talk about it.</h2><p>Sam guides the conversation. Ellis looks closely at the language. Kit brings another point of view. You set the pace.</p>
            <label className="overview-section">What are we reading?<select value={sectionId} onChange={(event) => setSectionId(event.target.value)}>{book.sections.map((section) => <option value={section.id} key={section.id}>{section.title || `Section ${section.order_index + 1}`}</option>)}</select></label>
            <button className="reading-button secondary" onClick={() => void startClub()} disabled={starting || !sectionId}>{starting ? <Loader2 size={16} className="animate-spin" /> : <Users size={16} />} {starting ? "Opening the conversation…" : "Start a book club session"}</button>
            <p className="overview-note">Text first · Selected chapter · About 20 minutes</p>
          </section>
        </div>
        <details className="overview-customize" open={customize} onToggle={(event) => setCustomize(event.currentTarget.open)}><summary>Choose a different discussion style, voice, or reading selection</summary>{customize ? <SessionSetup bookId={bookId} onBack={() => setCustomize(false)} onStartSession={onStartSession} /> : null}</details>
      </> : null}
    </div>
  );
}
