"use client";

/**
 * BindingInterstitial — the 30-90s state a user watches after clicking
 * "stage this volume". Replaces the generic loading spinner with a
 * bookbinder's half-title that maps to the actual ingestion pipeline.
 *
 * Driven by `stage` (one of i..v), `elapsedSeconds`, and the volume's
 * title/author. The cast whisper rotates by a hash of the title so the
 * same book always whispers the same line.
 */

import { useEffect, useState } from "react";
import { AgentSeal } from "@/components/lamplight";
import { cn } from "@/lib/utils";

export type BindingStage = "i" | "ii" | "iii" | "iv" | "v";

interface BindingInterstitialProps {
  bookTitle: string;
  author?: string | null;
  stage: BindingStage;
  elapsedSeconds: number;
  /** Optional override of expected-window copy. Defaults to "30–90s" range. */
  expectedRange?: string;
  /** When the user dismisses the overlay (e.g. back to shelf). */
  onDismiss?: () => void;
}

const STAGES: Array<{
  id: BindingStage;
  index: number;
  name: string;
  subtitle: string;
  glyph: React.ReactNode;
}> = [
  {
    id: "i",
    index: 1,
    name: "Extracting",
    subtitle: "paper to text",
    glyph: (
      <svg viewBox="0 0 40 40" width="38" height="38" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round">
        <path d="M10 8 L26 8 L30 12 L30 32 L10 32 Z" />
        <path d="M26 8 L26 12 L30 12" />
        <path d="M14 18 L26 18 M14 22 L26 22 M14 26 L22 26" />
      </svg>
    ),
  },
  {
    id: "ii",
    index: 2,
    name: "Setting Type",
    subtitle: "text to paragraphs",
    glyph: (
      <svg viewBox="0 0 40 40" width="38" height="38" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round">
        <rect x="9" y="10" width="22" height="22" />
        <path d="M9 16 L31 16 M16 16 L16 32 M24 16 L24 32 M9 24 L31 24" />
      </svg>
    ),
  },
  {
    id: "iii",
    index: 3,
    name: "Sewing the Gatherings",
    subtitle: "paragraphs to sections",
    glyph: (
      <svg viewBox="0 0 40 40" width="40" height="40" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round">
        <path d="M8 12 C 14 8, 26 8, 32 12" />
        <path d="M8 20 C 14 16, 26 16, 32 20" />
        <path d="M8 28 C 14 24, 26 24, 32 28" />
        <path d="M12 10 L12 30 M20 8 L20 30 M28 10 L28 30" strokeDasharray="1 3" />
        <circle cx="34" cy="14" r="1.2" fill="currentColor" />
      </svg>
    ),
  },
  {
    id: "iv",
    index: 4,
    name: "Embedding the Voice",
    subtitle: "sections to vectors",
    glyph: (
      <svg viewBox="0 0 40 40" width="38" height="38" fill="none" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round">
        <circle cx="20" cy="20" r="11" />
        <circle cx="20" cy="20" r="6" />
        <circle cx="20" cy="20" r="1.6" fill="currentColor" />
        <path d="M20 6 L20 9 M20 31 L20 34 M6 20 L9 20 M31 20 L34 20" />
      </svg>
    ),
  },
  {
    id: "v",
    index: 5,
    name: "Drying the Glue",
    subtitle: "final commit",
    glyph: (
      <svg viewBox="0 0 40 40" width="38" height="38" fill="none" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round">
        <path d="M11 10 L29 10 L29 30 L11 30 Z" />
        <path d="M11 14 L29 14" />
        <path d="M16 22 C 17 19, 19 19, 20 22 C 21 25, 23 25, 24 22" />
      </svg>
    ),
  },
];

const WHISPERS: Array<{ ink: "sam" | "ellis" | "kit" | "sable"; initial: string; role: string; line: string }> = [
  {
    ink: "ellis",
    initial: "E",
    role: "Ellis · close reader",
    line: "Already underlining the language that earns its place.",
  },
  {
    ink: "sam",
    initial: "S",
    role: "Sam · facilitator",
    line: "I'm laying out the chapters now. Ready when you are.",
  },
  {
    ink: "kit",
    initial: "K",
    role: "Kit · skeptic",
    line: "Reserving my objections until I see the whole thing.",
  },
  {
    ink: "sable",
    initial: "v",
    role: "Sable · after-dark",
    line: "I'll read the rest of you when the glue is dry.",
  },
];

function whisperForTitle(title: string) {
  let hash = 0;
  for (let i = 0; i < title.length; i++) {
    hash = (hash * 31 + title.charCodeAt(i)) >>> 0;
  }
  return WHISPERS[hash % WHISPERS.length];
}

function formatElapsed(seconds: number) {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
}

export function BindingInterstitial({
  bookTitle,
  author,
  stage,
  elapsedSeconds,
  expectedRange = "30–90s for a volume this size",
  onDismiss,
}: BindingInterstitialProps) {
  const [tick, setTick] = useState(elapsedSeconds);

  // Tick locally between server polls so the clock never freezes — the
  // parent will reset us with a fresh elapsedSeconds when its poll lands.
  useEffect(() => {
    setTick(elapsedSeconds);
    const handle = window.setInterval(() => setTick((value) => value + 1), 1000);
    return () => window.clearInterval(handle);
  }, [elapsedSeconds]);

  const activeIndex = STAGES.findIndex((entry) => entry.id === stage);
  const whisper = whisperForTitle(bookTitle);

  return (
    <div className="binding-scrim" role="dialog" aria-label="Binding the volume">
      <section className="binding-halftitle" aria-live="polite">
        <p className="binding-eyebrow">
          <span aria-hidden="true">§</span>
          &nbsp;&nbsp;at the press · binding in progress
        </p>

        <h1 className="binding-title">{bookTitle}</h1>
        {author ? (
          <p className="binding-author">
            <em>by</em>
            {author}
          </p>
        ) : null}

        <div className="binding-rule" aria-hidden="true">
          <span className="binding-rule-line" />
          <span className="binding-rule-orn">❦</span>
          <span className="binding-rule-line" />
        </div>

        <p className="binding-panel-label">the bindery — instrument panel</p>

        <div className="bindery-stages" role="list">
          {STAGES.map((entry, idx) => {
            const isDone = idx < activeIndex;
            const isActive = idx === activeIndex;
            const isFuture = idx > activeIndex;
            return (
              <div
                key={entry.id}
                role="listitem"
                aria-current={isActive ? "step" : undefined}
                className={cn(
                  "bindery-stage",
                  isDone && "is-done",
                  isActive && "is-active",
                  isFuture && "is-future"
                )}
              >
                {isDone ? (
                  <span className="bindery-tick" aria-label="completed">
                    ✓
                  </span>
                ) : null}
                <div className="bindery-glyph" aria-hidden="true">
                  {entry.glyph}
                </div>
                <div className="bindery-roman">{entry.id}.</div>
                <div className="bindery-name">
                  {entry.name}
                  <em>{entry.subtitle}</em>
                </div>
              </div>
            );
          })}
        </div>

        <div className="binding-clock" aria-label="elapsed time and expected window">
          <span className="binding-elapsed">{formatElapsed(tick)} elapsed</span>
          <span className="binding-clock-divider" aria-hidden="true" />
          <span className="binding-range">≈ {expectedRange}</span>
        </div>

        <div className="binding-whisper">
          <AgentSeal initial={whisper.initial} ink={whisper.ink} className="binding-whisper-seal" />
          <p className={`ink-${whisper.ink}`}>
            “{whisper.line}”
            <span className="binding-whisper-attrib">
              <span aria-hidden="true">†</span>
              &nbsp;&nbsp;{whisper.role}
            </span>
          </p>
        </div>

        {onDismiss ? (
          <button type="button" className="binding-back" onClick={onDismiss}>
            <span className="binding-manicule" aria-hidden="true">
              ☜
            </span>
            back to the shelf
          </button>
        ) : null}
      </section>
    </div>
  );
}
