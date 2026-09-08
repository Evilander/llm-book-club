"use client";

/**
 * BinderyFloor — bulk ingestion progress panel.
 *
 * Lives at the top of the home shelf when there's an active queue. Shows
 * the volumes currently in flight with per-book stage indicator, a typographic
 * throughput line, a separate "needs another look" section for failures, and
 * a "shelved tonight" footer of the most recent completions.
 */

import { useMemo } from "react";
import type { BindingStage } from "@/components/binding-interstitial";
import { cn } from "@/lib/utils";

export interface BinderyVolume {
  id: string;
  title: string;
  stage: BindingStage;
  elapsedSeconds: number;
}

export interface BinderyFailure {
  id: string;
  title: string;
  reason: string;
  /** Called when user clicks RETRY on this volume. */
  onRetry?: () => void;
}

export interface BinderyShelved {
  id: string;
  title: string;
}

export interface BinderyFloorProps {
  /** Volumes currently in the bindery (queued or processing). */
  inFlight: BinderyVolume[];
  /** Volumes that failed and need attention. */
  failed?: BinderyFailure[];
  /** Most recent completions, newest first. */
  shelvedTonight?: BinderyShelved[];
  /** Optional: book category context, shown in the header. */
  categoryContext?: { name: string; totalVolumes: number; queuedTonight: number };
  /** Toggle bindery pause (rate-limits worker). */
  paused?: boolean;
  onTogglePause?: () => void;
  /** Cap on visible in-flight rows; the rest collapse to "+N more waiting at the door". */
  visibleRows?: number;
  /** Cap on visible shelved-tonight entries. */
  visibleShelved?: number;
}

const STAGE_LABELS: Record<BindingStage, string> = {
  i: "Extracting",
  ii: "Setting the Type",
  iii: "Sewing the Gatherings",
  iv: "Embedding the Voice",
  v: "Drying the Glue",
};

const STAGE_GLYPHS: Record<BindingStage, React.ReactNode> = {
  i: (
    <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round">
      <path d="M6 4 L16 4 L18 6 L18 20 L6 20 Z" />
      <path d="M16 4 L16 6 L18 6" />
      <path d="M9 10 L15 10 M9 13 L15 13 M9 16 L13 16" />
    </svg>
  ),
  ii: (
    <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round">
      <rect x="5" y="6" width="14" height="14" />
      <path d="M5 10 L19 10 M9 10 L9 20 M15 10 L15 20 M5 15 L19 15" />
    </svg>
  ),
  iii: (
    <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round">
      <path d="M5 8 C 9 5, 15 5, 19 8" />
      <path d="M5 13 C 9 10, 15 10, 19 13" />
      <path d="M5 18 C 9 15, 15 15, 19 18" />
      <path d="M8 6 L8 20 M12 5 L12 20 M16 6 L16 20" strokeDasharray="1 2.5" />
    </svg>
  ),
  iv: (
    <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round">
      <circle cx="12" cy="12" r="7" />
      <circle cx="12" cy="12" r="3.5" />
      <circle cx="12" cy="12" r="1" fill="currentColor" />
    </svg>
  ),
  v: (
    <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round">
      <path d="M6 5 L18 5 L18 19 L6 19 Z" />
      <path d="M6 8 L18 8" />
      <path d="M9 13 C 10 11, 11 11, 12 13 C 13 15, 14 15, 15 13" />
    </svg>
  ),
};

function formatElapsed(seconds: number) {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
}

function throughputSentence(inFlight: BinderyVolume[]) {
  const total = inFlight.length;
  const onPress = inFlight.filter((volume) => volume.stage === "iv" || volume.stage === "v").length;
  if (total === 0) {
    return "The bindery is quiet.";
  }
  const left = `${total === 1 ? "One" : numberWord(total)} in the bindery.`;
  if (onPress === 0) {
    return `${left} Nothing yet on the press.`;
  }
  return `${left} ${onPress === 1 ? "One" : numberWord(onPress)} on the press. About four volumes a minute.`;
}

function numberWord(n: number) {
  const words = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve"];
  return words[n] ?? String(n);
}

export function BinderyFloor({
  inFlight,
  failed = [],
  shelvedTonight = [],
  categoryContext,
  paused = false,
  onTogglePause,
  visibleRows = 5,
  visibleShelved = 3,
}: BinderyFloorProps) {
  const visible = inFlight.slice(0, visibleRows);
  const remaining = Math.max(0, inFlight.length - visible.length);
  const sentence = useMemo(() => throughputSentence(inFlight), [inFlight]);
  const linecost = inFlight.length * 18; // ~18s per book average; calibrate later
  const clearMins = Math.max(1, Math.round(linecost / 60));

  if (inFlight.length === 0 && failed.length === 0 && shelvedTonight.length === 0) {
    return null;
  }

  const now = new Date();
  const dateLine = now.toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long" });
  const timeLine = now.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });

  return (
    <aside className="bindery-floor" aria-label="bulk ingestion progress">
      <header className="bindery-floor-head">
        <p className="eyebrow">
          The Bindery <span className="bindery-divider" aria-hidden="true">│</span>{" "}
          {inFlight.length === 0 ? "Quiet for now" : `${inFlight.length} in flight`}
        </p>
        <p className="eyebrow bindery-floor-clock">
          Floor · {dateLine} · {timeLine}
        </p>
      </header>

      <h2 className="bindery-floor-sentence">{sentence}</h2>

      <div className="bindery-floor-meta">
        {inFlight.length > 0 ? (
          <span className="bindery-floor-mins">
            ≈ <strong>{clearMins} min</strong> to clear the line
          </span>
        ) : null}
        {categoryContext ? (
          <span className="bindery-floor-category">
            <span className="bindery-floor-category-name">{categoryContext.name}</span>
            <span className="bindery-floor-category-count">
              {categoryContext.totalVolumes.toLocaleString()} volumes · {categoryContext.queuedTonight} queued tonight
            </span>
          </span>
        ) : null}
        {onTogglePause ? (
          <button
            type="button"
            onClick={onTogglePause}
            className={cn("bindery-floor-pause", paused && "is-paused")}
          >
            {paused ? "resume the bindery" : "pause the bindery"}
          </button>
        ) : null}
      </div>

      {inFlight.length > 0 ? (
        <>
          <p className="bindery-floor-subhead">In the bindery</p>
          <ul className="bindery-floor-rows" role="list">
            {visible.map((volume) => (
              <li key={volume.id} className="bindery-floor-row">
                <span className="bindery-floor-spine" aria-hidden="true" />
                <span className="bindery-floor-title">{volume.title}</span>
                <span className="bindery-floor-stage" aria-label={`Stage ${volume.stage}`}>
                  <span className="bindery-floor-glyph" aria-hidden="true">
                    {STAGE_GLYPHS[volume.stage]}
                  </span>
                  <span className="bindery-floor-stage-label">
                    <em>{volume.stage}.</em> {STAGE_LABELS[volume.stage]}
                  </span>
                </span>
                <span className="bindery-floor-elapsed">{formatElapsed(volume.elapsedSeconds)}</span>
              </li>
            ))}
          </ul>
          {remaining > 0 ? (
            <p className="bindery-floor-overflow">
              <span aria-hidden="true">¶ </span>
              {remaining} more waiting at the door
            </p>
          ) : null}
        </>
      ) : null}

      {failed.length > 0 ? (
        <>
          <p className="bindery-floor-subhead">needs another look</p>
          <ul className="bindery-floor-failures" role="list">
            {failed.map((volume) => (
              <li key={volume.id} className="bindery-floor-failure">
                <span className="bindery-floor-spine bindery-floor-spine-failed" aria-hidden="true" />
                <span className="bindery-floor-failure-title">{volume.title}</span>
                <span className="bindery-floor-failure-reason">{volume.reason}</span>
                {volume.onRetry ? (
                  <button type="button" className="stamp bindery-floor-retry" onClick={volume.onRetry}>
                    retry
                  </button>
                ) : null}
              </li>
            ))}
          </ul>
        </>
      ) : null}

      {shelvedTonight.length > 0 ? (
        <footer className="bindery-floor-shelved">
          <span className="bindery-floor-shelved-label">Shelved tonight</span>
          {shelvedTonight.slice(0, visibleShelved).map((volume, idx) => (
            <span key={volume.id} className="bindery-floor-shelved-item">
              <span className="bindery-floor-spine" aria-hidden="true" />
              <span className="bindery-floor-shelved-title">{volume.title}</span>
              <span className="bindery-floor-shelved-tick" aria-hidden="true">
                ✓
              </span>
              {idx < Math.min(visibleShelved, shelvedTonight.length) - 1 ? (
                <span className="bindery-floor-shelved-sep" aria-hidden="true">
                  ·
                </span>
              ) : null}
            </span>
          ))}
          {shelvedTonight.length > visibleShelved ? (
            <span className="bindery-floor-shelved-more">
              + {shelvedTonight.length - visibleShelved} more on the cart
            </span>
          ) : null}
        </footer>
      ) : null}
    </aside>
  );
}
