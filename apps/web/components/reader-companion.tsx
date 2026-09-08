"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import ReactMarkdown from "react-markdown";
import { ArrowUp, BookOpen, Loader2, MessageCircle, X } from "lucide-react";
import { useDiscussionSession } from "@/hooks/use-discussion-session";
import type { CitationData } from "@/types/api";

export interface ReaderNote {
  id: string;
  question: string;
  quote: string;
  char_start: number;
  char_end: number;
  chunk_id: string;
  section_id: string;
  verified: boolean;
}

interface Props {
  bookId: string;
  hidden?: boolean;
  sessionId: string | null;
  pageReady: boolean;
  enabled: boolean;
  onEnable: () => void;
  onPause: () => void;
  onClose: () => void;
  notes: ReaderNote[];
  notesLoading: boolean;
  notesError: string | null;
  onRetryNotes: () => void;
  selectedNote: ReaderNote | null;
  selectedText: string;
  onClearSelection: () => void;
  onSelectNote: (note: ReaderNote) => void;
  onDiscussNote: (note: ReaderNote) => void;
  onSelectCitation: (citation: CitationData) => void;
}

const noSpeech = () => undefined;

function CompanionConversation({ sessionId, bookId, selectedText, onClearSelection, onSelectCitation, pageReady, onRetryNotes, selectedQuestion }: Pick<Props, "bookId" | "selectedText" | "onClearSelection" | "onSelectCitation" | "pageReady" | "onRetryNotes"> & { sessionId: string; selectedQuestion?: string }) {
  const draftKey = `readagain.book.${bookId}.draft`;
  const [input, setInput] = useState(() => { try { return localStorage.getItem(draftKey) || ""; } catch { return ""; } });
  useEffect(() => { try { if (input) localStorage.setItem(draftKey, input); else localStorage.removeItem(draftKey); } catch { /* storage is optional */ } }, [draftKey, input]);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const followRef = useRef(true);
  const { messages, sending, loading, session, error, submitMessage, loadSession } = useDiscussionSession({ sessionId, experienceMode: "text", onSentenceReady: noSpeech, startAutomatically: false, includeCloseReader: false });

  useEffect(() => {
    if (followRef.current && scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [messages]);
  useEffect(() => { if (selectedText) inputRef.current?.focus(); }, [selectedText]);

  async function send() {
    const question = input.trim();
    if (!question || sending || !pageReady) return;
    followRef.current = true;
    const message = selectedText ? `${question}\n\nThe passage we’re discussing: “${selectedText}”${selectedQuestion ? `\nYour question in the margin: ${selectedQuestion}` : ""}` : question;
    if (await submitMessage(message)) { setInput(""); onClearSelection(); }
  }

  return <div className="companion-conversation">
    <div className="companion-messages" ref={scrollRef} onScroll={() => { const el = scrollRef.current; if (el) followRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80; }} aria-label="Conversation with your reading companion">
      {loading ? <p className="companion-muted" role="status">Finding our place…</p> : !messages.length ? <div className="companion-empty"><MessageCircle size={22} strokeWidth={1.3} /><h3>What’s on your mind?</h3><p>Ask about a line, follow a hunch, or tell me what you’re noticing.</p></div> : null}
      {messages.map((message) => <div className={`companion-message ${message.role === "user" ? "from-reader" : "from-companion"}`} key={message.id}>
        <p className="companion-message-name">{message.role === "user" ? "You" : "Sam"}</p>
        <div className="companion-message-prose"><ReactMarkdown>{message.content || "Thinking…"}</ReactMarkdown></div>
        {message.citations?.map((citation, index) => <button key={`${citation.chunk_id}-${index}`} className="companion-citation" disabled={!citation.verified || citation.char_start == null} onClick={() => onSelectCitation(citation)}><BookOpen size={12} /> “{citation.text.slice(0, 85)}{citation.text.length > 85 ? "…" : ""}”{!citation.verified ? " (unverified)" : ""}</button>)}
      </div>)}
      {sending ? <p className="companion-muted" role="status">Sam is with the page…</p> : null}
    </div>
    {error ? <div className="companion-error" role="alert"><p>{error}</p><button onClick={() => { onRetryNotes(); void loadSession(); }} disabled={sending}>Reconnect companion</button></div> : null}
    <form className="companion-form" onSubmit={(event) => { event.preventDefault(); void send(); }}>
      {selectedText ? <div className="companion-selected"><p>“{selectedText}”</p><button type="button" aria-label="Clear selected passage" onClick={onClearSelection}><X size={14} /></button></div> : null}
      <label className="sr-only" htmlFor="companion-question">Your thought or question</label>
      <textarea id="companion-question" ref={inputRef} value={input} onChange={(event) => setInput(event.target.value)} placeholder={selectedText ? "What does this bring up for you?" : "A thought, a question, a little wondering…"} rows={3} maxLength={8000} disabled={loading || !session?.is_active}
        onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); void send(); } }} />
      <div className="companion-form-foot"><span>{pageReady ? "Saved with this book" : "Finding the current page…"}</span><button className="companion-send" type="submit" disabled={sending || loading || !pageReady || !input.trim() || !session?.is_active} aria-label="Send to your companion">{sending ? <Loader2 size={17} className="animate-spin" /> : <ArrowUp size={18} />}</button></div>
    </form>
  </div>;
}

export function ReaderCompanion(props: Props) {
  const [tab, setTab] = useState<"margin" | "conversation">("margin");
  const selectedNoteRef = useRef<HTMLDivElement>(null);
  useEffect(() => { if (props.selectedNote) { setTab("margin"); selectedNoteRef.current?.scrollIntoView({ block: "nearest" }); } }, [props.selectedNote]);
  useEffect(() => { if (props.selectedText) setTab("conversation"); }, [props.selectedText]);

  return <aside hidden={props.hidden} className="reader-companion" aria-label="Reading companion">
    <header className="companion-heading"><div><p className="quiet-eyebrow">Beside the page</p><h2><span className="companion-dot" /> Your reading companion</h2></div><button className="companion-close" onClick={props.onClose} aria-label="Close companion"><X size={18} /></button></header>
    {props.enabled ? <div className="companion-tabs" role="tablist" aria-label="Companion views" onKeyDown={(event) => { if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return; event.preventDefault(); const next = event.key === "Home" ? "margin" : event.key === "End" ? "conversation" : tab === "margin" ? "conversation" : "margin"; setTab(next); document.getElementById(`${next}-tab`)?.focus(); }}><button id="margin-tab" role="tab" tabIndex={tab === "margin" ? 0 : -1} aria-selected={tab === "margin"} aria-controls="margin-panel" onClick={() => setTab("margin")}>In the margin {props.notes.length ? <span>{props.notes.length}</span> : null}</button><button id="conversation-tab" role="tab" tabIndex={tab === "conversation" ? 0 : -1} aria-selected={tab === "conversation"} aria-controls="conversation-panel" onClick={() => setTab("conversation")}>Our conversation</button></div> : null}
    {!props.enabled ? <div className="companion-welcome"><BookOpen size={28} strokeWidth={1.2} /><h3>A second pair of eyes.</h3><p>I’m Sam, your AI reading companion. I can leave a few questions in the margin as you read, and we can talk whenever something catches your attention.</p><button className="reading-button" onClick={props.onEnable}>Read with me <MessageCircle size={16} /></button><p className="companion-muted">Our conversation stays with this book, from chapter to chapter.</p></div> : <>
      <div id="margin-panel" role="tabpanel" aria-labelledby="margin-tab" hidden={tab !== "margin"} className="companion-notes">
        <p className="companion-muted">A few things we could linger on.</p>
        {props.notesLoading ? <p className="companion-muted" role="status"><Loader2 size={14} className="animate-spin inline mr-2" /> Reading this page with you…</p> : null}
        {props.notes.map((note, index) => <div className={`margin-question ${props.selectedNote?.id === note.id ? "is-selected" : ""}`} key={note.id} ref={props.selectedNote?.id === note.id ? selectedNoteRef : undefined}>
          <button className="margin-quote" onClick={() => props.onSelectNote(note)}><span>{index + 1}</span><q>{note.quote}</q></button><p>{note.question}</p><button className="text-link" onClick={() => { props.onDiscussNote(note); setTab("conversation"); }}>Talk about this <MessageCircle size={13} /></button>
        </div>)}
        {!props.notesLoading && !props.notesError && !props.notes.length ? <p className="companion-muted">No questions in this margin yet. You can select a passage or start with a thought of your own.</p> : null}
        {props.notesError ? <div className="companion-error" role="alert"><p>{props.notesError}</p><button onClick={props.onRetryNotes}>Try again</button></div> : null}
        <Link href={`/books/${props.bookId}`} className="companion-club">Bring this chapter to the book club <span>↗</span></Link>
        <button className="text-link companion-pause" onClick={props.onPause}>Read on my own for a while</button>
      </div>
      <div id="conversation-panel" role="tabpanel" aria-labelledby="conversation-tab" hidden={tab !== "conversation"} className="companion-chat-panel">
        {props.sessionId ? <CompanionConversation key={props.sessionId} sessionId={props.sessionId} bookId={props.bookId} pageReady={props.pageReady} onRetryNotes={props.onRetryNotes} selectedText={props.selectedText || props.selectedNote?.quote || ""} selectedQuestion={props.selectedNote?.question} onClearSelection={props.onClearSelection} onSelectCitation={props.onSelectCitation} /> : <p className="companion-muted" role="status">Opening our conversation…</p>}
      </div>
    </>}
  </aside>;
}
