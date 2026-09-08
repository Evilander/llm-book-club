"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import * as Dialog from "@radix-ui/react-dialog";
import { ArrowLeft, ChevronLeft, ChevronRight, MessageCircle, X } from "lucide-react";
import { API_BASE, cn } from "@/lib/utils";
import type { CitationData } from "@/types/api";
import { ReaderCompanion, type ReaderNote } from "@/components/reader-companion";

export type ReaderTheme = "cream-daylight" | "aged-paper" | "archive-paper" | "paper-white" | "lamplight-dark";
export type ReaderFont = "serif" | "lexend" | "atkinson" | "dyslexic";
interface ReaderPrefs {
  theme: ReaderTheme; font_family: ReaderFont; font_size_px: number; line_height: number;
  measure_ch: number; focus_reading: boolean; focus_reading_intensity: number;
}
interface ReaderPageData {
  book_id: string; title: string; author: string | null; page: number; page_size: number;
  total_pages: number; total_chars: number; current_section_id: string | null;
  current_section_title: string | null; current_section_order: number | null;
  text: string; char_start: number; char_end: number;
  chunks?: Array<{ chunk_id: string; section_id: string; char_start: number; char_end: number }>;
}
const PAPERS: Array<{ id: ReaderTheme; label: string; description: string }> = [
  { id: "cream-daylight", label: "Fresh paper", description: "Soft off-white, a little grain" },
  { id: "aged-paper", label: "Well-loved", description: "Warm cream, softened edges" },
  { id: "archive-paper", label: "Old favorite", description: "Golden paper, a trace of age" },
  { id: "paper-white", label: "Bright white", description: "Clean and crisp" },
  { id: "lamplight-dark", label: "Evening", description: "An ivory page, a darker desk" },
];
const DEFAULT_PREFS: ReaderPrefs = { theme: "cream-daylight", font_family: "serif", font_size_px: 20, line_height: 1.75, measure_ch: 62, focus_reading: false, focus_reading_intensity: 40 };
const PREFS_KEY = "readagain.lite-reader.prefs";

function readerId(): string {
  try {
    const id = localStorage.getItem("readagain.reader-id") || `r-${crypto.randomUUID()}`;
    localStorage.setItem("readagain.reader-id", id);
    return id;
  } catch { return "local-reader"; }
}
function safePrefs(value: Partial<ReaderPrefs>): ReaderPrefs {
  return { ...DEFAULT_PREFS, ...value,
    theme: PAPERS.some((paper) => paper.id === value.theme) ? value.theme! : DEFAULT_PREFS.theme,
    font_family: ["serif", "lexend", "atkinson", "dyslexic"].includes(value.font_family || "") ? value.font_family! : "serif",
    font_size_px: Math.min(32, Math.max(12, Number(value.font_size_px) || DEFAULT_PREFS.font_size_px)),
    line_height: Math.min(2, Math.max(1.3, Number(value.line_height) || DEFAULT_PREFS.line_height)),
    measure_ch: Math.min(90, Math.max(40, Number(value.measure_ch) || DEFAULT_PREFS.measure_ch)),
    focus_reading: value.focus_reading === true,
    focus_reading_intensity: Math.min(60, Math.max(25, Number(value.focus_reading_intensity) || 40)),
  };
}
function applyBionicText(text: string, pct: number): React.ReactNode {
  // Split on word boundaries, preserving punctuation + whitespace
  const segmenter = new Intl.Segmenter(undefined, { granularity: "grapheme" });
  const parts = text.split(/(\s+|[^\p{L}\p{M}\p{N}’']+)/u);
  return parts.map((part, idx) => {
    if (!/\p{L}/u.test(part) || part.length < 4) {
      return part;
    }
    const letters = Array.from(segmenter.segment(part), (item) => item.segment);
    const n = Math.max(1, Math.round((letters.length * pct) / 100));
    return (
      <span key={idx}>
        <b className="fr-b">{letters.slice(0, n).join("")}</b>
        <span className="fr-r">{letters.slice(n).join("")}</span>
      </span>
    );
  });
}


function PageProse({ text, start = 0, notes = [], onSelectNote, focusOn, focusPct }: {
  text: string; start?: number; notes?: ReaderNote[]; onSelectNote?: (note: ReaderNote) => void; focusOn: boolean; focusPct: number;
}) {
  // Python API offsets count Unicode code points; JS string offsets count UTF-16.
  const paragraphs = useMemo(() => {
    let offset = start;
    return text.split(/(\n\s*\n)/).map((part) => { const result = { text: part, start: offset }; offset += Array.from(part).length; return result; }).filter((part) => part.text.trim());
  }, [text, start]);
  return <div className={cn("lite-prose", focusOn && "is-focus")}>{paragraphs.map((paragraph) => {
    const chars = Array.from(paragraph.text);
    const end = paragraph.start + chars.length;
    const here = notes.filter((note) => note.char_start < end && note.char_end > paragraph.start);
    const edges = [...new Set([paragraph.start, end, ...here.flatMap((note) => [Math.max(paragraph.start, note.char_start), Math.min(end, note.char_end)])])].sort((a, b) => a - b);
    return <p key={paragraph.start}>{edges.slice(0, -1).map((edge, index) => {
      const fragment = chars.slice(edge - paragraph.start, edges[index + 1] - paragraph.start).join("");
      const note = here.find((item) => item.char_start <= edge && item.char_end >= edges[index + 1]);
      const content = focusOn ? applyBionicText(fragment, focusPct) : fragment;
      return note ? <button type="button" className="passage-mark" key={edge} onClick={() => onSelectNote?.(note)} title={note.question} aria-label={`Discuss highlighted passage: ${fragment}`}>{content}</button> : <span key={edge}>{content}</span>;
    })}</p>;
  })}</div>;
}

function pageSizeForScreen(prefs: ReaderPrefs) {
  const small = window.innerWidth <= 560;
  const rail = window.innerWidth > 900 ? (window.innerWidth <= 1150 ? 320 : 350) : 0;
  const roomPadding = small ? 24 : window.innerWidth <= 900 ? 64 : 84;
  const paperPadding = small ? 52 : Math.min(140, Math.max(60, window.innerWidth * .092));
  const width = Math.min(750, window.innerWidth - rail - roomPadding) - paperPadding;
  const lines = Math.max(4, Math.floor((window.innerHeight - (small ? 330 : 400)) / (prefs.font_size_px * prefs.line_height)) - 3);
  const columns = Math.min(prefs.measure_ch, width / (prefs.font_size_px * .45));
  return Math.max(200, Math.min(1800, Math.floor(lines * columns / 100) * 100));
}

export function LiteReader({ bookId, initialPage, initialPageSize = 1800 }: { bookId: string; initialPage?: number; initialPageSize?: number }) {
  const [prefs, setPrefs] = useState<ReaderPrefs>(DEFAULT_PREFS);
  const [prefsReady, setPrefsReady] = useState(false);
  const [booted, setBooted] = useState(false);
  const [page, setPage] = useState<ReaderPageData | null>(null);
  const [pageNum, setPageNum] = useState(initialPage || 1);
  const [pageSize, setPageSize] = useState(1800);
  const pageSizeRef = useRef(1800);
  const anchorRef = useRef(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [railOpen, setRailOpen] = useState(false);
  const [companionOpen, setCompanionOpen] = useState(false);
  const [mobile, setMobile] = useState(false);
  const [enabled, setEnabled] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [pageReady, setPageReady] = useState(false);
  const [notes, setNotes] = useState<ReaderNote[]>([]);
  const [notesLoading, setNotesLoading] = useState(false);
  const [notesError, setNotesError] = useState<string | null>(null);
  const [notesAttempt, setNotesAttempt] = useState(0);
  const [selectedNote, setSelectedNote] = useState<ReaderNote | null>(null);
  const [selectedText, setSelectedText] = useState("");
  const pendingQuote = useRef<ReaderNote | null>(null);
  const [citationHighlight, setCitationHighlight] = useState<ReaderNote | null>(null);
  const [snapshot, setSnapshot] = useState<ReaderPageData | null>(null);
  const [turning, setTurning] = useState<"left" | "right" | null>(null);
  const pendingTurn = useRef<"left" | "right" | null>(null);
  const proseRef = useRef<HTMLElement>(null);
  const touchStart = useRef<{ x: number; y: number } | null>(null);
  const dirtyPrefs = useRef(false);
  const placeKey = `readagain.book.${bookId}.page-v2`;

  const updatePrefs = (change: (current: ReaderPrefs) => ReaderPrefs) => { dirtyPrefs.current = true; setPrefs(change); };
  useEffect(() => {
    const mobileQuery = matchMedia("(max-width: 900px)");
    setMobile(mobileQuery.matches);
    setCompanionOpen(!mobileQuery.matches);
    const onSize = () => { setMobile(mobileQuery.matches); setCompanionOpen(!mobileQuery.matches); };
    mobileQuery.addEventListener("change", onSize);
    let localPrefs = DEFAULT_PREFS;
    let savedPage = initialPage || 1;
    let savedSize = initialPageSize;
    let savedOffset = (savedPage - 1) * savedSize;
    try {
      const local = localStorage.getItem(PREFS_KEY);
      if (local) { localPrefs = safePrefs(JSON.parse(local)); setPrefs(localPrefs); }
      if (!initialPage) {
        const saved = JSON.parse(localStorage.getItem(`${placeKey}.location`) || "null");
        savedPage = Math.max(1, Number(saved?.page || localStorage.getItem(placeKey)) || 1);
        savedSize = Math.max(200, Math.min(1800, Number(saved?.page_size) || 1800));
        savedOffset = Math.max(0, Number(saved?.char_start) || (savedPage - 1) * savedSize);
      }
      setEnabled(localStorage.getItem(`readagain.book.${bookId}.companion`) === "on");
    } catch { /* Reading works when browser storage is unavailable. */ }
    const size = pageSizeForScreen(localPrefs);
    pageSizeRef.current = size; anchorRef.current = savedOffset;
    setPageSize(size); setPageNum(size === savedSize ? savedPage : Math.floor(savedOffset / size) + 1);
    setBooted(true);
    const controller = new AbortController();
    fetch(`${API_BASE}/v1/users/me/reading-prefs`, { headers: { "X-Reader-Id": readerId() }, signal: controller.signal })
      .then((res) => res.ok ? res.json() : null)
      .then((value) => { if (value && !dirtyPrefs.current) setPrefs(safePrefs(value)); })
      .catch(() => undefined).finally(() => { if (!controller.signal.aborted) setPrefsReady(true); });
    return () => { controller.abort(); mobileQuery.removeEventListener("change", onSize); };
  }, [bookId, initialPage, initialPageSize, placeKey]);

  useEffect(() => {
    if (!booted) return;
    function resizePages() {
      const size = pageSizeForScreen(prefs);
      if (size === pageSizeRef.current) return;
      pageSizeRef.current = size;
      setPageSize(size); setPageNum(Math.floor(anchorRef.current / size) + 1);
      setSnapshot(null); setTurning(null); pendingTurn.current = null;
    }
    resizePages();
    // Mobile keyboards change height without changing reading space. Only
    // resize on orientation/width changes there, so typing never turns pages.
    let lastWidth = window.innerWidth;
    const onResize = () => { if (window.innerWidth <= 900 && window.innerWidth === lastWidth) return; lastWidth = window.innerWidth; resizePages(); };
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, [booted, prefs.font_size_px, prefs.line_height, prefs.measure_ch, prefs.font_family]);

  useEffect(() => {
    if (!prefsReady) return;
    try { localStorage.setItem(PREFS_KEY, JSON.stringify(prefs)); } catch { /* no storage */ }
    if (!dirtyPrefs.current) return;
    const timeout = setTimeout(() => {
      fetch(`${API_BASE}/v1/users/me/reading-prefs`, { method: "PATCH", headers: { "Content-Type": "application/json", "X-Reader-Id": readerId() }, body: JSON.stringify(prefs) }).catch(() => undefined);
    }, 500);
    return () => clearTimeout(timeout);
  }, [prefs, prefsReady]);

  useEffect(() => {
    if (!booted) return;
    const controller = new AbortController();
    setLoading(true);
    setPageReady(false);
    setError(null);
    fetch(`${API_BASE}/v1/books/${bookId}/reader?page=${pageNum}&page_size=${pageSize}`, { signal: controller.signal })
      .then(async (res) => { if (!res.ok) throw new Error("page"); return res.json() as Promise<ReaderPageData>; })
      .then((next) => {
        if (controller.signal.aborted) return;
        setPage(next);
        setLoading(false);
        setTurning(pendingTurn.current);
        pendingTurn.current = null;
        const quote = pendingQuote.current;
        const chars = Array.from(next.text);
        const found = quote && chars.slice(quote.char_start - next.char_start, quote.char_end - next.char_start).join("") === quote.quote ? quote : null;
        setCitationHighlight(found);
        setSelectedNote(null); setSelectedText(found?.quote || ""); setNotes([]);
        pendingQuote.current = null;
        anchorRef.current = next.char_start;
        try { localStorage.setItem(placeKey, String(next.page)); localStorage.setItem(`${placeKey}.location`, JSON.stringify({ page: next.page, page_size: next.page_size, char_start: next.char_start })); } catch { /* no storage */ }
        window.history.replaceState(null, "", `${window.location.pathname}?page=${next.page}&size=${next.page_size}`);
      }).catch((err) => { if (err.name !== "AbortError") { setLoading(false); setError("This page couldn’t be opened. Please try again."); setSnapshot(null); pendingTurn.current = null; } });
    return () => controller.abort();
  }, [bookId, pageNum, pageSize, booted, attempt, placeKey]);

  useEffect(() => {
    if (!turning) return;
    const timeout = setTimeout(() => { setTurning(null); setSnapshot(null); }, 650);
    return () => clearTimeout(timeout);
  }, [turning]);

  useEffect(() => {
    if (!enabled || !page || loading) return;
    const currentPage = page;
    const sectionIds = [...new Set(currentPage.chunks?.map((chunk) => chunk.section_id) || (currentPage.current_section_id ? [currentPage.current_section_id] : []))];
    if (!sectionIds.length) { setNotesError("This page doesn’t have a reading section yet."); return; }
    const controller = new AbortController();
    setNotesLoading(true); setNotesError(null);
    const timeout = setTimeout(async () => {
      try {
        const response = await fetch(`${API_BASE}/v1/books/${bookId}/companion`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ section_ids: sectionIds, page: currentPage.page, page_size: currentPage.page_size }), signal: controller.signal });
        if (!response.ok) throw new Error("companion");
        const companion = await response.json();
        if (controller.signal.aborted) return;
        setSessionId(companion.session_id);
        setPageReady(true);
        const noteRes = await fetch(`${API_BASE}/v1/books/${bookId}/reader-notes`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ session_id: companion.session_id, page: currentPage.page, page_size: currentPage.page_size }), signal: controller.signal });
        if (!noteRes.ok) throw new Error("notes");
        const data = await noteRes.json();
        if (controller.signal.aborted) return;
        const chars = Array.from(currentPage.text);
        setNotes((data.notes || []).filter((note: ReaderNote) => note.verified && note.char_start >= currentPage.char_start && note.char_end <= currentPage.char_end && chars.slice(note.char_start - currentPage.char_start, note.char_end - currentPage.char_start).join("") === note.quote));
      } catch { if (!controller.signal.aborted) setNotesError("I couldn’t leave questions on this page just yet. You can still read or try again."); }
      finally { if (!controller.signal.aborted) setNotesLoading(false); }
    }, 700);
    return () => { clearTimeout(timeout); controller.abort(); };
  }, [bookId, enabled, page, loading, notesAttempt]);

  const turnPage = useCallback((direction: "left" | "right") => {
    if (!page || loading || turning || pendingTurn.current) return;
    const next = page.page + (direction === "right" ? 1 : -1);
    if (next < 1 || next > page.total_pages) return;
    const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (!reduceMotion) { setSnapshot(page); pendingTurn.current = direction; }
    setPageNum(next);
  }, [page, loading, turning]);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.defaultPrevented || event.metaKey || event.ctrlKey || event.altKey || railOpen || (mobile && companionOpen)) return;
      const target = event.target as HTMLElement;
      if (target.closest("input, textarea, select, button, a, [contenteditable='true'], [role='dialog']")) return;
      if (event.key === "ArrowRight") { event.preventDefault(); turnPage("right"); }
      if (event.key === "ArrowLeft") { event.preventDefault(); turnPage("left"); }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [turnPage, railOpen, mobile, companionOpen]);

  function selectNote(note: ReaderNote) { setSelectedNote(note); setSelectedText(""); setCompanionOpen(true); }
  function selectPassage() {
    const selection = window.getSelection();
    if (!selection?.rangeCount || !proseRef.current?.contains(selection.getRangeAt(0).commonAncestorContainer)) return;
    const text = selection.toString().trim();
    if (text.length > 2 && text.length <= 1000) { setSelectedText(text); setSelectedNote(null); }
  }
  async function selectCitation(citation: CitationData) {
    if (!citation.verified || citation.char_start == null) return;
    try {
      const query = new URLSearchParams({ chunk_id: citation.chunk_id, char_start: String(citation.char_start), page_size: String(pageSize) });
      const res = await fetch(`${API_BASE}/v1/books/${bookId}/reader-location?${query}`);
      if (!res.ok) throw new Error("location");
      const location = await res.json();
      const quote: ReaderNote = { id: `citation-${citation.chunk_id}`, chunk_id: citation.chunk_id, section_id: location.section_id, quote: citation.text, question: "From our conversation", char_start: location.char_start, char_end: location.char_start + Array.from(citation.text).length, verified: true };
      if (location.page !== page?.page) { pendingQuote.current = quote; setPageNum(location.page); }
      else { const chars = Array.from(page?.text || ""); if (chars.slice(quote.char_start - (page?.char_start || 0), quote.char_end - (page?.char_start || 0)).join("") === quote.quote) setCitationHighlight(quote); setSelectedText(citation.text); }
    } catch { setNotesError("The quoted passage couldn’t be opened. Its text is still in our conversation."); }
  }
  const companion = <ReaderCompanion hidden={!mobile && !companionOpen} bookId={bookId} sessionId={sessionId} pageReady={pageReady && !loading} enabled={enabled} onEnable={() => { setEnabled(true); try { localStorage.setItem(`readagain.book.${bookId}.companion`, "on"); } catch { /* no storage */ } }} onPause={() => { setEnabled(false); setNotes([]); setNotesLoading(false); setPageReady(false); try { localStorage.removeItem(`readagain.book.${bookId}.companion`); } catch { /* no storage */ } }} onClose={() => setCompanionOpen(false)} notes={notes} notesLoading={notesLoading} notesError={notesError} onRetryNotes={() => setNotesAttempt((n) => n + 1)} selectedNote={selectedNote} selectedText={selectedText} onClearSelection={() => { setSelectedNote(null); setSelectedText(""); setCitationHighlight(null); }} onSelectNote={selectNote} onDiscussNote={(note) => { setSelectedNote(note); setSelectedText(note.quote); }} onSelectCitation={(citation) => void selectCitation(citation)} />;

  return <div className={cn("lite-reader", `lite-${prefs.theme}`, `lite-font-${prefs.font_family}`, companionOpen && !mobile && "with-companion")}
    style={{ "--lite-fs": `${prefs.font_size_px}px`, "--lite-lh": prefs.line_height, "--lite-measure": `${prefs.measure_ch}ch` } as React.CSSProperties}>
    <header className="reader-toolbar">
      <Link href="/#library" className="reader-back" aria-label="Back to your library"><ArrowLeft size={17} /><span>Library</span></Link>
      <div className="reader-book-title"><strong>{page?.title || "Your book"}</strong>{page?.author ? <span>{page.author}</span> : null}</div>
      <div className="reader-tools"><button onClick={() => setRailOpen(true)} aria-label="Paper and typography settings" className="reader-type-button">Aa</button><button onClick={() => setCompanionOpen((open) => !open)} aria-label="Toggle reading companion" aria-expanded={companionOpen}><MessageCircle size={18} /><span>Companion</span>{notes.length > 0 ? <b>{notes.length}</b> : null}</button></div>
    </header>
    <div className="reader-layout"><div className="lite-room">
      <div className="reader-running-head"><span>{page?.current_section_title}</span><span>{page ? `${page.page} / ${page.total_pages}` : ""}</span></div>
      <div className="paper-stage">
        <article className="lite-page" ref={proseRef} aria-label="Book page" aria-busy={loading} onMouseUp={selectPassage}
          onTouchStart={(event) => { touchStart.current = { x: event.touches[0].clientX, y: event.touches[0].clientY }; }}
          onTouchEnd={(event) => { const start = touchStart.current; touchStart.current = null; if (!start || window.getSelection()?.toString()) return; const dx = event.changedTouches[0].clientX - start.x; const dy = event.changedTouches[0].clientY - start.y; if (Math.abs(dx) > 70 && Math.abs(dx) > Math.abs(dy) * 2) turnPage(dx < 0 ? "right" : "left"); else selectPassage(); }}>
          {error ? <div className="lite-error" role="alert"><p>{error}</p><button onClick={() => setAttempt((n) => n + 1)} className="lite-retry">Try again</button>{pageNum > 1 ? <button className="lite-retry" onClick={() => setPageNum(1)}>First page</button> : null}</div> : !page ? <div className="lite-loading" role="status">Opening the page…</div> : <>
            <div className="lite-chapno">{page.current_section_order != null ? `Chapter ${page.current_section_order + 1}` : ""}</div>
            <h1 className="lite-chap">{page.current_section_title || page.title}</h1><div className="lite-orn" aria-hidden="true">·</div>
            <PageProse text={page.text} start={page.char_start} notes={citationHighlight ? [...notes, citationHighlight] : notes} onSelectNote={selectNote} focusOn={prefs.focus_reading} focusPct={prefs.focus_reading_intensity} />
            <div className="lite-folio"><span /> <span>{page.page}</span> <span /></div>
          </>}
        </article>
        {snapshot && turning ? <div className={cn("paper-turn-sheet", `turn-${turning}`)} aria-hidden="true"><div className="lite-chapno">{snapshot.current_section_order != null ? `Chapter ${snapshot.current_section_order + 1}` : ""}</div><h2 className="lite-chap">{snapshot.current_section_title || snapshot.title}</h2><div className="lite-orn">·</div><PageProse text={snapshot.text} focusOn={prefs.focus_reading} focusPct={prefs.focus_reading_intensity} /><div className="lite-folio">{snapshot.page}</div></div> : null}
      </div>
      <nav className="reader-pagination" aria-label="Page navigation"><button aria-label="Previous page" disabled={!page || loading || page.page <= 1 || !!turning} onClick={() => turnPage("left")}><ChevronLeft size={18} /><span>Previous</span></button><span aria-live="polite">{loading && page ? "Turning the page…" : page ? `Page ${page.page} of ${page.total_pages}` : ""}</span><button aria-label="Next page" disabled={!page || loading || page.page >= page.total_pages || !!turning} onClick={() => turnPage("right")}><span>Next</span><ChevronRight size={18} /></button></nav>
      {selectedText ? <button className="reading-button secondary discuss-selection" onClick={() => setCompanionOpen(true)}>Discuss selected passage <MessageCircle size={15} /></button> : null}
      <p className="reader-place-note">Your place is saved on this device.</p>
    </div>{!mobile ? companion : null}</div>
    <Dialog.Root open={mobile && companionOpen} onOpenChange={setCompanionOpen}><Dialog.Portal><Dialog.Overlay className="reading-dialog-scrim" /><Dialog.Content className="companion-drawer" aria-describedby={undefined}><Dialog.Title className="sr-only">Your reading companion</Dialog.Title>{companion}</Dialog.Content></Dialog.Portal></Dialog.Root>
    <Dialog.Root open={railOpen} onOpenChange={setRailOpen}><Dialog.Portal><Dialog.Overlay className="reading-dialog-scrim" /><Dialog.Content className="reading-preferences" aria-describedby={undefined}>
      <div className="preferences-heading"><Dialog.Title>Paper & type</Dialog.Title><Dialog.Close aria-label="Close reading settings"><X size={19} /></Dialog.Close></div>
      <p className="preferences-intro">Find the page that feels like yours.</p>
      <div className="paper-options">{PAPERS.map((paper) => <button key={paper.id} className={cn("paper-option", prefs.theme === paper.id && "is-selected")} onClick={() => updatePrefs((current) => ({ ...current, theme: paper.id }))} aria-pressed={prefs.theme === paper.id}><span className={`paper-swatch swatch-${paper.id}`} aria-hidden="true">Aa</span><span><strong>{paper.label}</strong><small>{paper.description}</small></span><span className="paper-choice-dot" /></button>)}</div>
      <div className="preferences-typography">
        <div className="lite-rail-ornrule" />

        <section className="bionic-setting" aria-labelledby="bionic-title">
          <div className="lite-rail-peg">
            <span id="bionic-title">Bionic text</span>
            <button type="button" role="switch" aria-label="Bionic text" aria-describedby="bionic-description" aria-checked={prefs.focus_reading} className={cn("lite-rail-toggle", prefs.focus_reading && "is-on")} onClick={() => updatePrefs((current) => ({ ...current, focus_reading: !current.focus_reading }))}><span className="lite-rail-knob" /></button>
          </div>
          <p id="bionic-description" className="bionic-description">Emphasize the beginning of words. See how it feels to read this way.</p>
          <p className={cn("bionic-preview", prefs.focus_reading && "is-focus")}>{prefs.focus_reading ? applyBionicText("Follow the sentence, at your own pace.", prefs.focus_reading_intensity) : "Follow the sentence, at your own pace."}</p>
          {prefs.focus_reading ? <div className="bionic-emphasis"><label htmlFor="bionic-emphasis" className="lite-rail-lbl">Emphasis <em>{prefs.focus_reading_intensity}%</em></label><input id="bionic-emphasis" aria-label="Bionic emphasis" type="range" min={25} max={60} step={5} value={prefs.focus_reading_intensity} onChange={(event) => updatePrefs((current) => ({ ...current, focus_reading_intensity: Number(event.target.value) }))} /></div> : null}
        </section>
        <div className="lite-rail-ornrule" />

        <section>
          <div className="lite-rail-lbl">
            Typeface
            <em>{prefs.font_family === "dyslexic" ? "OpenDys" : prefs.font_family}</em>
          </div>
          <div className="lite-rail-fonts">
            {(
              [
                { id: "serif", label: "Serif" },
                { id: "lexend", label: "Lexend" },
                { id: "atkinson", label: "Atkinson" },
                { id: "dyslexic", label: "OpenDys" },
              ] as Array<{ id: ReaderFont; label: string }>
            ).map((f) => (
              <button
                key={f.id}
                type="button"
                className={cn(
                  "lite-rail-chip",
                  `lite-rail-chip-${f.id}`,
                  prefs.font_family === f.id && "is-active"
                )}
                onClick={() => updatePrefs((p) => ({ ...p, font_family: f.id }))}
              >
                {f.label}
              </button>
            ))}
          </div>
        </section>

        <div className="lite-rail-ornrule" />

        <section>
          <div className="lite-rail-lbl">
            Text size <em>{prefs.font_size_px} px</em>
          </div>
          <input
            type="range"
            aria-label="Text size"
            min={12}
            max={32}
            step={1}
            value={prefs.font_size_px}
            onChange={(e) =>
              updatePrefs((p) => ({ ...p, font_size_px: Number(e.target.value) }))
            }
          />

          <div className="lite-rail-lbl" style={{ marginTop: 14 }}>
            Line spacing <em>{prefs.line_height.toFixed(2)}</em>
          </div>
          <input
            type="range"
            aria-label="Line spacing"
            min={130}
            max={200}
            step={5}
            value={Math.round(prefs.line_height * 100)}
            onChange={(e) =>
              updatePrefs((p) => ({
                ...p,
                line_height: Number(e.target.value) / 100,
              }))
            }
          />

          <div className="lite-rail-lbl" style={{ marginTop: 14 }}>
            Line width <em>{prefs.measure_ch} ch</em>
          </div>
          <input
            type="range"
            aria-label="Line width"
            min={40}
            max={90}
            step={2}
            value={prefs.measure_ch}
            onChange={(e) =>
              updatePrefs((p) => ({ ...p, measure_ch: Number(e.target.value) }))
            }
          />
        </section>

        <div className="lite-rail-ornrule" />



      </div>
    </Dialog.Content></Dialog.Portal></Dialog.Root>
  </div>;
}
