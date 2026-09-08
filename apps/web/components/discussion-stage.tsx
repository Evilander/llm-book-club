"use client";

import type { ReactNode } from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ArrowLeft, ArrowUp, Loader2, X } from "lucide-react";
import * as Dialog from "@radix-ui/react-dialog";
import Link from "next/link";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { toast } from "sonner";

import { LocalAudiobookPlayer } from "@/components/local-audiobook-player";
import { VoiceInput } from "@/components/voice-input";
import {
  AgentSeal,
  AntiqueMicrophone,
  InkNib,
  Phonograph,
  RibbonBookmark,
  RuleOrnament,
  WaxSeal,
  type LamplightInk,
} from "@/components/lamplight";
import { API_BASE, cn } from "@/lib/utils";
import { useAudioPlayback } from "@/hooks/use-audio-playback";
import { useDiscussionSession } from "@/hooks/use-discussion-session";
import type {
  CitationData,
  ExplorePayload,
  Message,
  SessionPreferences,
} from "@/types/api";

interface DiscussionStageProps {
  sessionId: string;
  onBack: () => void;
}

type ExperienceMode = "audio" | "text";
type AgentRole =
  | "facilitator"
  | "close_reader"
  | "skeptic"
  | "after_dark_guide"
  | "user";

// ── Agent identity (ink color + initial, NO Lucide icons by design) ──────────

interface AgentVoice {
  name: string;
  role: AgentRole;
  ink: LamplightInk;
  initial: string;
  subtitle: string;
}

const BASE_AGENTS: Record<AgentRole, AgentVoice> = {
  facilitator: {
    name: "Sam",
    role: "facilitator",
    ink: "sam",
    initial: "S",
    subtitle: "facilitator",
  },
  close_reader: {
    name: "Ellis",
    role: "close_reader",
    ink: "ellis",
    initial: "E",
    subtitle: "close reader",
  },
  skeptic: {
    name: "Kit",
    role: "skeptic",
    ink: "kit",
    initial: "K",
    subtitle: "skeptic",
  },
  after_dark_guide: {
    name: "Sable",
    role: "after_dark_guide",
    ink: "sable",
    initial: "v",
    subtitle: "after-dark",
  },
  user: {
    name: "You",
    role: "user",
    ink: "pencil",
    initial: "u",
    subtitle: "reader",
  },
};

const AFTER_DARK_PERSONAS: Record<string, Pick<AgentVoice, "name" | "initial">> = {
  woman: { name: "Sable", initial: "v" },
  gay_man: { name: "Lucian", initial: "L" },
  trans_woman: { name: "Vesper", initial: "V" },
};

const AGENT_VOICE_MAP: Record<string, string> = {
  facilitator: "nova",
  close_reader: "shimmer",
  skeptic: "echo",
  after_dark_guide: "fable",
};

function getAgent(role: string, preferences?: SessionPreferences | null): AgentVoice {
  const base = BASE_AGENTS[role as AgentRole];
  if (!base) {
    return {
      name: role,
      role: "user",
      ink: "pencil",
      initial: role.slice(0, 1).toUpperCase() || "·",
      subtitle: "",
    };
  }
  if (role === "after_dark_guide" && preferences?.desire_lens) {
    const persona = AFTER_DARK_PERSONAS[preferences.desire_lens];
    if (persona) {
      return { ...base, ...persona };
    }
  }
  return base;
}

// ── Citation underline rendering ─────────────────────────────────────────────

interface CitationSpan {
  chunkId: string;
  start: number;
  end: number;
  ink: LamplightInk;
  agentName: string;
  citation: CitationData;
}

function buildCitationIndex(
  messages: Message[],
  preferences?: SessionPreferences | null
): Map<string, CitationSpan[]> {
  const index = new Map<string, CitationSpan[]>();
  for (const message of messages) {
    if (!message.citations?.length) continue;
    const agent = getAgent(message.role, preferences);
    if (agent.role === "user") continue;
    for (const citation of message.citations) {
      if (
        !citation.verified ||
        citation.char_start == null ||
        citation.char_end == null ||
        citation.char_end <= citation.char_start
      ) {
        continue;
      }
      const span: CitationSpan = {
        chunkId: citation.chunk_id,
        start: citation.char_start,
        end: citation.char_end,
        ink: agent.ink,
        agentName: agent.name,
        citation,
      };
      const list = index.get(citation.chunk_id);
      if (list) {
        list.push(span);
      } else {
        index.set(citation.chunk_id, [span]);
      }
    }
  }
  return index;
}

/** Split text into a list of segments tagged with the ink colors that cite them.
 *
 * Citations may overlap. We walk through every distinct boundary (start/end of
 * every span) and emit a segment for each interval, attaching the set of inks
 * that cover that interval. Two or more inks → `.cite-stack` styling. */
function renderCitedText(
  text: string,
  spans: CitationSpan[],
  onClick?: (span: CitationSpan) => void
): Array<ReactNode> {
  if (!spans.length) return [text];
  const chars = Array.from(text);
  // Server offsets count Unicode code points, not JavaScript code units.
  // Clamp + sort by start
  const clean = spans
    .map((span) => ({
      ...span,
      start: Math.max(0, Math.min(span.start, chars.length)),
      end: Math.max(0, Math.min(span.end, chars.length)),
    }))
    .filter((span) => span.end > span.start)
    .sort((a, b) => a.start - b.start);
  if (!clean.length) return [text];

  // Collect every distinct boundary
  const boundaries = new Set<number>();
  boundaries.add(0);
  boundaries.add(chars.length);
  for (const span of clean) {
    boundaries.add(span.start);
    boundaries.add(span.end);
  }
  const sorted = Array.from(boundaries).sort((a, b) => a - b);

  const out: Array<ReactNode> = [];
  for (let i = 0; i < sorted.length - 1; i++) {
    const start = sorted[i];
    const end = sorted[i + 1];
    if (end <= start) continue;
    const slice = chars.slice(start, end).join("");
    if (!slice) continue;
    const covering = clean.filter((span) => span.start <= start && span.end >= end);
    if (!covering.length) {
      out.push(slice);
      continue;
    }
    const inks = Array.from(new Set(covering.map((span) => span.ink)));
    const className = inks.length > 1 ? "cite cite-stack" : `cite cite-${covering[0].ink}`;
    const title = covering
      .map((span) => `${span.agentName}: ${span.citation.text || "cited"}`)
      .join("\n");
    out.push(
      <span
        key={`cite-${start}-${end}`}
        className={className}
        title={title}
        data-selected={covering.some((span) => span.agentName === "selected") || undefined}
        onClick={onClick ? () => onClick(covering[0]) : undefined}
      >
        {slice}
      </span>
    );
  }
  return out;
}

// ── Conversation invitation copy ─────────────────────────────────────────────

function buildRoomInvitation(
  session: import("@/types/api").SessionData | null,
  activeSectionTitle: string | null
) {
  if (!session) {
    return "A reading room that can move from delight to argument without losing the page.";
  }
  const style = session.preferences?.discussion_style;
  const sectionLabel = activeSectionTitle ? ` around ${activeSectionTitle}` : "";
  if (style === "sexy") {
    const persona =
      AFTER_DARK_PERSONAS[session.preferences?.desire_lens || ""]?.name || "the after-dark guide";
    const focus = session.preferences?.erotic_focus?.replace(/_/g, " ") || "desire";
    const intensity = session.preferences?.adult_intensity?.replace(/_/g, " ") || "frank";
    return `${persona} joins Sam, Ellis, and Kit for a ${intensity} after-dark close reading${sectionLabel}. Expect real critical pressure, real appetite, and a slow look at where ${focus} becomes impossible to ignore.`;
  }
  return `Sam follows the conversation, Ellis looks closely at the language, and Kit offers another way of seeing${sectionLabel}. Take your time.`;
}

function buildSparkDeck(
  session: import("@/types/api").SessionData | null,
  activeSectionTitle: string | null
) {
  const sectionNoun = activeSectionTitle || "this section";
  if (session?.preferences?.discussion_style === "sexy") {
    return [
      `Where is the erotic voltage in ${sectionNoun}: gaze, delay, clothes, power, or something else?`,
      `Give me the hottest reading of ${sectionNoun}, then have Kit pressure-test it with evidence.`,
      `What makes ${sectionNoun} feel dangerous, tender, or impossible to skim?`,
    ];
  }
  return [
    `What is the one detail in ${sectionNoun} that a first-time reader is most likely to miss?`,
    `Give me one close-reading insight, one skeptical challenge, and one question worth carrying forward.`,
    `Push the room past summary — what on the page is doing the real work here?`,
  ];
}

function citationLabel(citation: CitationData): string {
  if (citation.verified === false) return "unverified";
  switch (citation.match_type) {
    case "exact":
      return "exact";
    case "normalized":
      return "normalized";
    case "fuzzy":
      return "fuzzy";
    default:
      return "unchecked";
  }
}

function formatTime(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${mins}:${secs.toString().padStart(2, "0")}`;
}

// ── Manuscript turn ──────────────────────────────────────────────────────────

interface ManuscriptTurnProps {
  message: Message;
  agent: AgentVoice;
  showRoleLabel: boolean;
  isStreaming: boolean;
  citationsHere: CitationData[];
  onSpeakAgain: () => void;
  onCiteBracketClick: (citation: CitationData) => void;
  feedback: "up" | "down" | null;
  onFeedback: (value: "up" | "down" | null) => void;
}

function ManuscriptTurn({
  message,
  agent,
  showRoleLabel,
  isStreaming,
  citationsHere,
  onSpeakAgain,
  onCiteBracketClick,
  feedback,
  onFeedback,
}: ManuscriptTurnProps) {
  const isUser = agent.role === "user";
  return (
    <div className="manuscript-turn">
      {/* Marginalia rail content: citation brackets aligned to this paragraph */}
      <div className="turn-rail">
        {citationsHere.map((citation, idx) => {
          return (
            <button
              key={`${message.id}-${citation.chunk_id}-${idx}`}
              type="button"
              className="cite-bracket"
              onClick={() => onCiteBracketClick(citation)}
              title={`${agent.name} · ${citation.text}`}
              disabled={!citation.verified || citation.char_start == null}
            >
              <span className="bracket-mark">⌈</span>
              <span className="bracket-meta">
                {citation.verified ? `Passage ${idx + 1}` : "Unverified"}
              </span>
              <span className="bracket-mark">⌉</span>
              <span
                className={cn(
                  "bracket-dot",
                  citation.verified === false && "is-unverified",
                  citation.match_type === "fuzzy" && "is-fuzzy"
                )}
                aria-hidden="true"
              />
            </button>
          );
        })}
      </div>

      <div className={cn("turn-body", `ink-${agent.ink}`, isUser && "is-user")}>
        <AgentSeal initial={agent.initial} ink={agent.ink} className="turn-sigil" />
        {showRoleLabel ? (
          <span className="turn-role">
            <span className="turn-name">{agent.name}</span>
            {agent.subtitle ? <span className="turn-subtitle">— {agent.subtitle}</span> : null}
          </span>
        ) : null}
        {message.content ? (
          <div className="turn-prose">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                a: ({ href, children }) => (
                  <a href={href} target="_blank" rel="noopener noreferrer" className="turn-link">
                    {children}
                  </a>
                ),
              }}
            >
              {message.content}
            </ReactMarkdown>
            {isStreaming ? <InkNib className="turn-nib" /> : null}
          </div>
        ) : (
          <em className="turn-thinking">composing…</em>
        )}
      </div>

      {!isUser && message.content ? (
        <div className="turn-actions" aria-label="agent actions">
          <button
            type="button"
            className="turn-action"
            onClick={onSpeakAgain}
            title="Speak this turn again"
          >
            voice
          </button>
          <button
            type="button"
            className={cn("turn-action", feedback === "up" && "is-on")}
            onClick={() => onFeedback(feedback === "up" ? null : "up")}
            title="This landed"
          >
            ↑
          </button>
          <button
            type="button"
            className={cn("turn-action", feedback === "down" && "is-off")}
            onClick={() => onFeedback(feedback === "down" ? null : "down")}
            title="This missed"
          >
            ↓
          </button>
        </div>
      ) : null}
    </div>
  );
}

// ── Open book reading panel ──────────────────────────────────────────────────

interface OpenBookPanelProps {
  explore: ExplorePayload | null;
  loading: boolean;
  readerSectionId: string | null;
  onSelectSection: (sectionId: string) => void;
  citationIndex: Map<string, CitationSpan[]>;
  highlightSpan: CitationData | null;
  highlightRef: React.RefObject<HTMLElement | null>;
  onMarkProgress: (status: "in_progress" | "completed") => void;
  progressSaving: "in_progress" | "completed" | null;
  audioMatches: import("@/types/api").AudiobookMatch[];
  bookTitle: string;
  bookAuthor?: string | null;
}

function OpenBookPanel({
  explore,
  loading,
  readerSectionId,
  onSelectSection,
  citationIndex,
  highlightSpan,
  highlightRef,
  onMarkProgress,
  progressSaving,
  audioMatches,
  bookTitle,
  bookAuthor,
}: OpenBookPanelProps) {
  const active = explore?.active_section;
  const sectionText = active?.text || "";
  const allSpans = useMemo<CitationSpan[]>(() => {
    const chars = Array.from(sectionText);
    return (active?.chunks || []).flatMap((chunk) => {
      const source = [...(citationIndex.get(chunk.chunk_id) || [])];
      if (highlightSpan?.chunk_id === chunk.chunk_id && highlightSpan.char_start != null && highlightSpan.char_end != null) {
        source.push({ chunkId: chunk.chunk_id, start: highlightSpan.char_start, end: highlightSpan.char_end, ink: "pencil", agentName: "selected", citation: highlightSpan });
      }
      return source.map((span) => ({ ...span, start: chunk.char_start + span.start, end: chunk.char_start + span.end }))
        .filter((span) => span.start >= chunk.char_start && span.end <= chunk.char_end && chars.slice(span.start, span.end).join("") === span.citation.text);
    });
  }, [active?.chunks, citationIndex, highlightSpan, sectionText]);

  const rendered = useMemo(
    () => renderCitedText(sectionText, allSpans),
    [allSpans, sectionText]
  );

  const progressPct = explore?.progress?.reading_progress_pct ?? null;
  const pairedAudiobook = audioMatches[0];

  return (
    <aside className="open-book" aria-label="open book reader">
      <header className="open-book-head">
        <p className="eyebrow">Beside the conversation</p>
        <h2 className="open-book-title">
          {active?.title || "Pick a section to open the text here."}
        </h2>
        <nav className="open-book-sections" aria-label="sections">
          {explore?.sections.map((section) => (
            <button
              key={section.id}
              type="button"
              onClick={() => onSelectSection(section.id)}
              className={cn(
                "section-chip",
                readerSectionId === section.id && "is-active"
              )}
            >
              {section.title || `Section ${section.order_index + 1}`}
            </button>
          ))}
        </nav>
      </header>

      <div className="open-book-spread">
        {progressPct != null ? (
          <RibbonBookmark percent={progressPct} className="open-book-ribbon" />
        ) : null}
        <div className="open-book-pages">
          {loading ? (
            <div className="open-book-loading">
              <Loader2 className="h-5 w-5 animate-spin" aria-hidden="true" />
              <span>Turning to the page…</span>
            </div>
          ) : sectionText ? (
            <p
              ref={highlightRef as React.RefObject<HTMLParagraphElement>}
              className="open-book-prose"
            >
              {rendered}
            </p>
          ) : (
            <p className="open-book-empty">
              The book is on the desk. Tap a section to open it.
            </p>
          )}
        </div>
        {pairedAudiobook ? (
          <div className="open-book-phonograph">
            <Phonograph spinning className="phonograph-icon" />
            <LocalAudiobookPlayer
              match={pairedAudiobook}
              bookTitle={bookTitle}
              bookAuthor={bookAuthor || undefined}
              compact
            />
          </div>
        ) : null}
      </div>

      <footer className="open-book-foot">
        <button
          type="button"
          className="folio-stamp"
          disabled={progressSaving !== null}
          onClick={() => onMarkProgress("in_progress")}
        >
          {progressSaving === "in_progress" ? "saving…" : "save place"}
        </button>
        <button
          type="button"
          className="folio-stamp folio-stamp-done"
          disabled={progressSaving !== null}
          onClick={() => onMarkProgress("completed")}
        >
          {progressSaving === "completed" ? "stamping…" : "mark read"}
        </button>
      </footer>
    </aside>
  );
}

// ── Discussion Stage ─────────────────────────────────────────────────────────

export function DiscussionStage({ sessionId, onBack }: DiscussionStageProps) {
  const [input, setInput] = useState("");
  const [isListening, setIsListening] = useState(false);
  const [selectedCitation, setSelectedCitation] = useState<CitationData | null>(null);
  const [experienceMode, setExperienceMode] = useState<ExperienceMode>("text");
  const [readerSectionId, setReaderSectionId] = useState<string | null>(null);
  const [explore, setExplore] = useState<ExplorePayload | null>(null);
  const [exploreLoading, setExploreLoading] = useState(false);
  const [bookDrawerOpen, setBookDrawerOpen] = useState(false);
  const [highlightSpan, setHighlightSpan] = useState<CitationData | null>(null);
  const [mobile, setMobile] = useState(false);
  const [exploreError, setExploreError] = useState<string | null>(null);
  const exploreRequest = useRef<AbortController | null>(null);
  const [messageFeedback, setMessageFeedback] = useState<Record<string, "up" | "down" | null>>({});
  const [progressSaving, setProgressSaving] = useState<"in_progress" | "completed" | null>(null);

  const manuscriptRef = useRef<HTMLElement>(null);
  const followRef = useRef(true);
  const highlightRef = useRef<HTMLElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const { playingAudio, speakingAgent, stopAudio, enqueueSpeech } = useAudioPlayback();

  const handleSentenceReady = useCallback(
    (params: { sentence: string; role: string; voice: string }) => {
      enqueueSpeech(params.sentence, params.role, params.voice);
    },
    [enqueueSpeech]
  );

  const {
    session,
    setSession,
    bookTitle,
    messages,
    loading,
    sending,
    activeAgent,
    activeMessageId,
    error,
    loadSession,
    sessionTime,
    submitMessage: rawSubmitMessage,
  } = useDiscussionSession({
    sessionId,
    experienceMode,
    onSentenceReady: handleSentenceReady,
  });

  useEffect(() => {
    if (session) {
      setExperienceMode(session.preferences?.experience_mode || "text");
      setReaderSectionId((prev) => prev || session.sections?.[0]?.id || null);
    }
  }, [session]);

  const isAfterDark = session?.preferences?.discussion_style === "sexy";
  const preferences = session?.preferences || null;
  const activeSectionTitle =
    explore?.active_section?.title || session?.sections?.[0]?.title || null;
  const roomInvitation = useMemo(
    () => buildRoomInvitation(session, activeSectionTitle),
    [activeSectionTitle, session]
  );
  const sparkDeck = useMemo(
    () => buildSparkDeck(session, activeSectionTitle),
    [activeSectionTitle, session]
  );

  const visibleRoles: AgentRole[] = useMemo(() => {
    const baseRoles: AgentRole[] = ["facilitator", "close_reader", "skeptic"];
    if (isAfterDark) baseRoles.push("after_dark_guide");
    return baseRoles;
  }, [isAfterDark]);

  const citationIndex = useMemo(
    () => buildCitationIndex(messages, preferences),
    [messages, preferences]
  );

  // Per-message citation lookup so each manuscript turn shows brackets for ITS
  // citations in the rail.
  const citationsByMessage = useMemo<Record<string, CitationData[]>>(() => {
    const map: Record<string, CitationData[]> = {};
    for (const message of messages) {
      if (message.citations?.length) {
        map[message.id] = message.citations;
      }
    }
    return map;
  }, [messages]);

  useEffect(() => {
    const media = matchMedia("(max-width: 1100px)");
    const sync = () => setMobile(media.matches);
    sync(); media.addEventListener("change", sync);
    return () => media.removeEventListener("change", sync);
  }, []);
  useEffect(() => {
    if (followRef.current && manuscriptRef.current) manuscriptRef.current.scrollTop = manuscriptRef.current.scrollHeight;
  }, [messages]);

  const sendFeedback = useCallback(
    async (messageId: string, feedback: "up" | "down" | null) => {
      setMessageFeedback((prev) => ({ ...prev, [messageId]: feedback }));
      try {
        const response = await fetch(`${API_BASE}/v1/sessions/${sessionId}/messages/${messageId}/feedback`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ feedback }),
        });
        if (!response.ok) throw new Error("feedback");
      } catch {
        setMessageFeedback((prev) => ({ ...prev, [messageId]: null }));
      }
    },
    [sessionId]
  );

  const loadExplore = useCallback(async () => {
    if (!session?.book_id || !readerSectionId) return;
    exploreRequest.current?.abort();
    const controller = new AbortController();
    exploreRequest.current = controller;
    setExploreLoading(true); setExploreError(null);
    try {
      const params = new URLSearchParams({ section_id: readerSectionId });
      const res = await fetch(`${API_BASE}/v1/books/${session.book_id}/explore?${params}`, { signal: controller.signal });
      if (!res.ok) throw new Error("section");
      const data = await res.json();
      if (!controller.signal.aborted) setExplore(data);
    } catch {
      if (!controller.signal.aborted) setExploreError("The reading section couldn’t be opened.");
    } finally {
      if (!controller.signal.aborted) setExploreLoading(false);
    }
  }, [readerSectionId, session?.book_id]);
  useEffect(() => { void loadExplore(); return () => exploreRequest.current?.abort(); }, [loadExplore]);
  useEffect(() => {
    if (!exploreLoading && highlightSpan) highlightRef.current?.querySelector('[data-selected="true"]')?.scrollIntoView({ block: "nearest" });
  }, [highlightSpan, explore, exploreLoading, bookDrawerOpen]);

  const handleCiteBracketClick = useCallback(async (citation: CitationData) => {
    setSelectedCitation(citation);
    if (!citation.verified || citation.char_start == null || !session?.book_id) return;
    try {
      const params = new URLSearchParams({ chunk_id: citation.chunk_id, char_start: String(citation.char_start) });
      const res = await fetch(`${API_BASE}/v1/books/${session.book_id}/reader-location?${params}`);
      if (!res.ok) throw new Error("location");
      const location = await res.json();
      setReaderSectionId(location.section_id);
      setHighlightSpan(citation);
      setBookDrawerOpen(true);
    } catch { toast.error("That passage couldn’t be opened. Please try again."); }
  }, [session?.book_id]);

  const updateReadingProgress = useCallback(
    async (status: "in_progress" | "completed") => {
      if (!session?.book_id || !readerSectionId || progressSaving) {
        return;
      }
      setProgressSaving(status);
      try {
        const response = await fetch(
          `${API_BASE}/v1/memory/books/${session.book_id}/sections/${readerSectionId}/progress`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ status }),
          }
        );
        if (!response.ok) {
          const error = await response.json().catch(() => ({ detail: "Progress update failed" }));
          throw new Error(error.detail || `HTTP ${response.status}`);
        }
        await loadExplore();
        toast.success(
          status === "completed" ? "Marked this stretch read" : "Saved your place"
        );
      } catch (error) {
        console.error("Failed to update reading progress:", error);
        toast.error(error instanceof Error ? error.message : "Could not update progress");
      } finally {
        setProgressSaving(null);
      }
    },
    [loadExplore, progressSaving, readerSectionId, session?.book_id]
  );

  useEffect(() => () => stopAudio(), [stopAudio]);

  async function updateExperienceMode(nextMode: ExperienceMode) {
    setExperienceMode(nextMode);
    if (nextMode === "text") {
      stopAudio();
    }
    try {
      const response = await fetch(`${API_BASE}/v1/sessions/${sessionId}/preferences`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ experience_mode: nextMode }),
      });
      if (!response.ok) throw new Error("preferences");
      setSession((prev) =>
        prev
          ? {
              ...prev,
              preferences: { ...(prev.preferences || {}), experience_mode: nextMode },
            }
          : prev
      );
    } catch (error) {
      setExperienceMode(session?.preferences?.experience_mode || "text");
      toast.error("That preference couldn’t be saved.");
    }
  }

  function submitMessage(prompt: string) {
    followRef.current = true;
    return rawSubmitMessage(prompt, {
      stopAudioBeforeSend: playingAudio ? stopAudio : undefined,
    });
  }

  function handleVoiceTranscript(text: string) {
    setInput((prev) => (prev ? `${prev} ${text}` : text));
    inputRef.current?.focus();
  }

  async function sendMessage() {
    const messageText = input.trim();
    if (!messageText) return;
    if (await submitMessage(messageText)) setInput("");
  }

  if (loading) {
    return (
      <div className="lamplight-room flex h-full items-center justify-center">
        <div className="text-center">
          <Loader2 className="mx-auto mb-4 h-8 w-8 animate-spin" aria-hidden="true" />
          <p className="text-[var(--cream)]/60 font-display">Opening the conversation…</p>
        </div>
      </div>
    );
  }

  if (!session) return <div className="reading-unavailable" role="alert"><h1>We couldn’t open this conversation.</h1><p>{error}</p><button className="reading-button" onClick={() => void loadSession()}>Try again</button><button className="text-link" onClick={onBack}>Back to the book</button></div>;
  const bookPanel = <OpenBookPanel explore={explore} loading={exploreLoading} readerSectionId={readerSectionId} onSelectSection={(id) => { setHighlightSpan(null); setReaderSectionId(id); }} citationIndex={citationIndex} highlightSpan={highlightSpan} highlightRef={highlightRef} onMarkProgress={updateReadingProgress} progressSaving={progressSaving} audioMatches={explore?.audiobook_matches || []} bookTitle={bookTitle} bookAuthor={explore?.author} />;

  return (
    <div className={cn("lamplight-room", isAfterDark && "after-dark")}>
      {/* ── Room header ─────────────────────────────────────────────────── */}
      <header className="room-header">
        <button type="button" onClick={onBack} className="room-back" aria-label="Back to the book">
          <ArrowLeft className="h-4 w-4" aria-hidden="true" />
          <span>Back to the book</span>
        </button>
        <div className="room-title">
          <p className="eyebrow">
            {session?.mode.replace(/_/g, " ")} ·{" "}
            {session?.preferences?.discussion_style?.replace(/_/g, " ") || "open"}
          </p>
          <h1 className="room-headline">
            {bookTitle || "Reading session"}
            {activeSectionTitle ? (
              <>
                <span className="room-headline-sep"> — </span>
                <span className="room-headline-section">{activeSectionTitle}</span>
              </>
            ) : null}
          </h1>
        </div>
        <div className="room-status">
          <span className="room-clock" aria-label="session length">
            {formatTime(sessionTime)}
          </span>
          <div className="room-mode-toggle" role="group" aria-label="experience mode">
            <button
              type="button"
              onClick={() => updateExperienceMode("text")}
              className={cn("room-mode", experienceMode === "text" && "is-active")}
              aria-pressed={experienceMode === "text"}
            >
              text
            </button>
            <button
              type="button"
              onClick={() => updateExperienceMode("audio")}
              className={cn("room-mode", experienceMode === "audio" && "is-active")}
              aria-pressed={experienceMode === "audio"}
            >
              voice
            </button>
          </div>
          {playingAudio ? (
            <button type="button" className="room-stop" onClick={stopAudio}>
              hush
            </button>
          ) : null}
        </div>
      </header>

      {/* ── Cast line ──────────────────────────────────────────────────── */}
      <section className="cast-line" aria-label="tonight's cast">
        <span className="cast-prefix">Your book club</span>
        {visibleRoles.map((role) => {
          const agent = getAgent(role, preferences);
          const isSpeaking = activeAgent === role || speakingAgent === role;
          return (
            <span
              key={role}
              className={cn(
                "cast-voice",
                `cast-voice-${agent.ink}`,
                `ink-${agent.ink}`,
                isSpeaking && "is-speaking"
              )}
            >
              <AgentSeal initial={agent.initial} ink={agent.ink} className="cast-sigil" />
              <span className="cast-name">{agent.name}</span>
              <span className="cast-subtitle">{agent.subtitle}</span>
            </span>
          );
        })}
      </section>

      {isAfterDark ? (
        <p className="after-dark-dedication" aria-label="after-dark dedication">
          — and one more set of eyes tonight.
        </p>
      ) : null}

      {/* ── Main: rail + manuscript + book ─────────────────────────────── */}
      <div className="room-main">
        <article className="manuscript" aria-label="Discussion" ref={manuscriptRef} onScroll={() => { const el = manuscriptRef.current; if (el) followRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 100; }}>
          {/* Invitation as a hand-set epigraph */}
          <div className="manuscript-epigraph">
            <RuleOrnament />
            <p>{roomInvitation}</p>
          </div>

          {messages.map((message) => {
            const agent = getAgent(message.role, preferences);
            const isStreaming = activeMessageId === message.id && sending;
            const messageCites = citationsByMessage[message.id] || [];
            return (
              <ManuscriptTurn
                key={message.id}
                message={message}
                agent={agent}
                showRoleLabel
                isStreaming={isStreaming}
                citationsHere={messageCites}
                onSpeakAgain={() =>
                  enqueueSpeech(
                    message.content,
                    message.role,
                    AGENT_VOICE_MAP[message.role] || "nova"
                  )
                }
                onCiteBracketClick={handleCiteBracketClick}
                feedback={messageFeedback[message.id] ?? null}
                onFeedback={(value) => sendFeedback(message.id, value)}
              />
            );
          })}

          {activeAgent && !activeMessageId ? (
            <p className="manuscript-typing">
              <AgentSeal
                initial={getAgent(activeAgent, preferences).initial}
                ink={getAgent(activeAgent, preferences).ink}
                className="turn-sigil"
              />
              <span className={cn("ink", `ink-${getAgent(activeAgent, preferences).ink}`)}>
                {getAgent(activeAgent, preferences).name} is writing…
              </span>
            </p>
          ) : null}

          {error ? <div className="companion-error" role="alert"><p>{error}</p><button disabled={sending} onClick={() => void loadSession()}>Refresh conversation</button></div> : null}

          {/* Spark deck — appears at end so user can hand the room a prompt */}
          {messages.length > 0 && messages.length < 3 && !sending ? (
            <div className="manuscript-sparks" aria-label="conversation sparks">
              <p className="eyebrow">Open prompts</p>
              <ul>
                {sparkDeck.map((prompt) => (
                  <li key={prompt}>
                    <button
                      type="button"
                      disabled={sending}
                      onClick={() => void submitMessage(prompt)}
                      className="spark"
                    >
                      {prompt}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </article>

        {!mobile ? <div className="club-book-column">{bookPanel}{exploreError ? <div className="companion-error" role="alert">{exploreError}<button onClick={() => void loadExplore()}>Try again</button></div> : null}<Link href={`/books/${session.book_id}/read`} className="text-link club-reading-link">Return to reading →</Link></div> : null}
      </div>

      {/* ── Inkwell input ──────────────────────────────────────────────── */}
      <footer className="inkwell">
        <form
          onSubmit={(event) => {
            event.preventDefault();
            void sendMessage();
          }}
          className="inkwell-form"
        >
          <VoiceInput
            onTranscript={handleVoiceTranscript}
            onListeningChange={setIsListening}
            disabled={sending || !session?.is_active}
          />
          <div className="inkwell-input-wrap">
            <span className="inkwell-nib" aria-hidden="true">
              <AntiqueMicrophone className="inkwell-mic" />
            </span>
            <textarea
              ref={inputRef}
              aria-label="Share a thought with the book club"
              rows={2}
              maxLength={8000}
              onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); void sendMessage(); } }}
              value={input}
              onChange={(event) => setInput(event.target.value)}
              placeholder={
                isAfterDark
                  ? "what does the room want you to say"
                  : experienceMode === "audio"
                    ? "speak or write into the room"
                    : "Share a thought, or ask the room a question…"
              }
              disabled={sending || !session?.is_active}
              className="inkwell-input"
            />
            {input.trim().length > 0 ? <InkNib className="inkwell-cursor" /> : null}
          </div>
          <button
            type="submit"
            disabled={sending || !input.trim()}
            className="inkwell-send"
            aria-label="Send to the book club"
          >
            <ArrowUp size={18} />
            <span className="inkwell-send-label">Send</span>
          </button>
          <button
            type="button"
            onClick={() => setBookDrawerOpen((open) => !open)}
            className="inkwell-drawer-toggle"
            aria-label="toggle book panel"
          >
            book
          </button>
        </form>
        <p className={cn("inkwell-status", isListening && "is-listening")}>
          {isListening
            ? "listening — the room hears you"
            : selectedCitation
              ? `↥ ${selectedCitation.text.slice(0, 80)}${selectedCitation.text.length > 80 ? "…" : ""}  ·  ${citationLabel(selectedCitation)}`
              : "Select a passage beside a reply to find it in the book."}
        </p>
      </footer>

      {/* ── Mobile drawer for the book panel ──────────────────────────── */}
      <Dialog.Root open={mobile && bookDrawerOpen} onOpenChange={setBookDrawerOpen}>
        <Dialog.Portal><Dialog.Overlay className="reading-dialog-scrim" /><Dialog.Content className="club-book-drawer" aria-describedby={undefined}>
          <Dialog.Title className="sr-only">The book beside our conversation</Dialog.Title>
          <Dialog.Close className="club-drawer-close" aria-label="Close book panel"><X size={20} /></Dialog.Close>
          {bookPanel}
          {exploreError ? <div className="companion-error" role="alert">{exploreError}<button onClick={() => void loadExplore()}>Try again</button></div> : null}
        </Dialog.Content></Dialog.Portal>
      </Dialog.Root>
    </div>
  );
}
