"use client";

import { useCallback, useEffect, useState } from "react";
import { Constellation } from "./constellation";
import { Dusk } from "./dusk";
import { Lab } from "./lab";
import { SHELF_BOOKS, Shelf } from "./shelf";
import { Spread } from "./spread";
import { Threshold } from "./threshold";
import type {
  CursorMode,
  LiteraryState,
  ShelfBook,
  Tweaks,
} from "./types";

const STATES: LiteraryState[] = [
  "dusk",
  "shelf",
  "threshold",
  "spread",
  "lab",
  "after-dark",
  "constellation",
];

const STATE_LABELS: Record<LiteraryState, string> = {
  dusk: "01 · dusk",
  shelf: "02 · shelf",
  threshold: "03 · threshold",
  spread: "04 · spread",
  lab: "05 · lab",
  "after-dark": "06 · after dark",
  constellation: "07 · constellation",
};

const HOSTILE: Record<LiteraryState, { q: string; a: string }> = {
  dusk: {
    q: "What if it's the user's first visit?",
    a: 'The whisper-strip is silent; the book is closed; "Step in" reads "Begin."',
  },
  shelf: {
    q: "What if BOOKS_DIR is empty?",
    a: "Empty shelf appears as a planed bare board with a quiet drop-zone; the room is patient.",
  },
  threshold: {
    q: "What if the user picks style:sexy but isn't 18+?",
    a: "The door is visible but unmoving. Server-side gate; no amount of client clicking opens it.",
  },
  spread: {
    q: "What if the book has no chapter structure?",
    a: "The slice falls back to char-range with a generated anchor phrase. The margins still speak to the page, not the chapter.",
  },
  lab: {
    q: "What if the user interrupts mid-aura?",
    a: "Aura dims on tap; turn is suspended, not killed. Agents hold their next sentence in a translucent footnote until you resume.",
  },
  "after-dark": {
    q: "How is this not just a palette swap?",
    a: "Spring damping increases, line-height tightens, type metrics shift, aura attack slows 2.2×. The room has different physics.",
  },
  constellation: {
    q: "What if the user has read one book, once?",
    a: "One bright star at center; three faint motif nodes orbiting. The sky is sparse on purpose — it grows.",
  },
};

const TWEAK_DEFAULTS: Tweaks = {
  skin: "footnote",
  density: "novice",
  reduceMotion: false,
};

export function LiteraryApp() {
  const [state, setState] = useState<LiteraryState>("dusk");
  const [book, setBook] = useState<ShelfBook | null>(null);
  const [afterDark, setAfterDark] = useState(false);
  const [showLab, setShowLab] = useState(false);
  const [cursorMode, setCursorMode] = useState<CursorMode>("reader");
  const [turning, setTurning] = useState<"fwd" | "rev" | null>(null);
  const [tweaks, setTweaks] = useState<Tweaks>(TWEAK_DEFAULTS);
  const [tweaksOpen, setTweaksOpen] = useState(false);

  // Restore last state from localStorage on first client render
  useEffect(() => {
    const saved = window.localStorage.getItem("lbc_state") as LiteraryState | null;
    if (saved && STATES.includes(saved)) setState(saved);
  }, []);

  useEffect(() => {
    window.localStorage.setItem("lbc_state", state);
  }, [state]);

  const goState = useCallback(
    (next: LiteraryState) => {
      setState((prev) => {
        if (next === prev) return prev;
        if (tweaks.reduceMotion) return next;
        const dir: "fwd" | "rev" =
          STATES.indexOf(next) >= STATES.indexOf(prev) ? "fwd" : "rev";
        setTurning(dir);
        window.setTimeout(() => setState(next), 420);
        window.setTimeout(() => setTurning(null), 1120);
        return prev;
      });
    },
    [tweaks.reduceMotion],
  );

  const handleNavClick = useCallback(
    (target: LiteraryState) => {
      if (target === "lab") {
        setShowLab(true);
        goState("lab");
      } else if (target === "after-dark") {
        setAfterDark(true);
        setShowLab(false);
        goState("after-dark");
      } else if (target === "spread") {
        setAfterDark(false);
        setShowLab(false);
        goState("spread");
      } else {
        setShowLab(false);
        goState(target);
      }
    },
    [goState],
  );

  const setTweak = useCallback(
    <K extends keyof Tweaks>(key: K, value: Tweaks[K]) => {
      setTweaks((t) => ({ ...t, [key]: value }));
    },
    [],
  );

  const worldCls = [
    "world",
    afterDark ? "after-dark" : "",
    `cursor-${cursorMode}`,
    tweaks.reduceMotion ? "reduce-motion" : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div className="literary-root">
      <div className={worldCls} data-screen-label={STATE_LABELS[state]}>
        <div className="room-backdrop" />

        <div className="atelier">
          {STATES.map((s) => (
            <button
              key={s}
              type="button"
              className={state === s ? "active" : ""}
              onClick={() => handleNavClick(s)}
            >
              {STATE_LABELS[s]}
            </button>
          ))}
        </div>

        {turning && (
          <div className="page-turn-overlay">
            <div
              className={`page-turn-shadow ${turning === "rev" ? "reverse" : ""}`}
            />
            <div
              className={`page-turn-leaf ${turning === "rev" ? "reverse" : ""}`}
            />
          </div>
        )}

        {state === "dusk" && <Dusk onEnter={() => goState("shelf")} />}
        {state === "shelf" && (
          <Shelf
            onPick={(b) => {
              setBook(b);
              goState("threshold");
            }}
          />
        )}
        {state === "threshold" && (
          <Threshold
            book={book ?? SHELF_BOOKS[0]}
            setAfterDark={setAfterDark}
            onEnter={() => goState("spread")}
          />
        )}
        {(state === "spread" ||
          state === "lab" ||
          state === "after-dark") && (
          <Spread
            afterDark={afterDark || state === "after-dark"}
            skin={tweaks.skin}
            density={tweaks.density}
          />
        )}
        {state === "constellation" && <Constellation />}

        {showLab && (state === "spread" || state === "lab") && (
          <Lab
            onClose={() => {
              setShowLab(false);
              goState("spread");
            }}
            cursorMode={cursorMode}
            setCursorMode={setCursorMode}
          />
        )}

        <div className="hostile-note">
          <div
            style={{
              color: "rgba(245,235,210,0.35)",
              marginBottom: 4,
            }}
          >
            hostile question
          </div>
          <div className="q">? {HOSTILE[state].q}</div>
          <div style={{ marginTop: 4 }}>→ {HOSTILE[state].a}</div>
        </div>

        <button
          type="button"
          onClick={() => setTweaksOpen((v) => !v)}
          style={{
            position: "fixed",
            bottom: 20,
            right: 20,
            zIndex: 119,
            background: "rgba(12,10,9,0.72)",
            border: "1px solid rgba(255,255,255,0.08)",
            color: "rgba(245,235,210,0.7)",
            fontFamily: "JetBrains Mono, monospace",
            fontSize: 10,
            letterSpacing: "0.18em",
            textTransform: "uppercase",
            padding: "10px 14px",
            borderRadius: 100,
            cursor: "pointer",
            backdropFilter: "blur(14px)",
            display: tweaksOpen ? "none" : "block",
          }}
        >
          tweaks
        </button>

        {tweaksOpen && (
          <div className="tweaks">
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "baseline",
              }}
            >
              <h4>tweaks</h4>
              <button
                type="button"
                onClick={() => setTweaksOpen(false)}
                style={{
                  background: "transparent",
                  border: "none",
                  color: "rgba(245,235,210,0.5)",
                  cursor: "pointer",
                  fontFamily: "JetBrains Mono, monospace",
                  fontSize: 10,
                  letterSpacing: "0.18em",
                }}
              >
                close ✕
              </button>
            </div>
            <div className="tweak-row">
              <label>book skin</label>
              <div className="options">
                {(["footnote", "noir", "poetry"] as const).map((s) => (
                  <button
                    key={s}
                    type="button"
                    className={tweaks.skin === s ? "on" : ""}
                    onClick={() => setTweak("skin", s)}
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
            <div className="tweak-row">
              <label>reader</label>
              <div className="options">
                {(["novice", "expert"] as const).map((s) => (
                  <button
                    key={s}
                    type="button"
                    className={tweaks.density === s ? "on" : ""}
                    onClick={() => setTweak("density", s)}
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
            <div className="tweak-row">
              <label>prefers-reduced-motion</label>
              <div className="options">
                <button
                  type="button"
                  className={!tweaks.reduceMotion ? "on" : ""}
                  onClick={() => setTweak("reduceMotion", false)}
                >
                  full
                </button>
                <button
                  type="button"
                  className={tweaks.reduceMotion ? "on" : ""}
                  onClick={() => setTweak("reduceMotion", true)}
                >
                  reduced
                </button>
              </div>
            </div>
            <div className="tweak-row">
              <label>after-dark</label>
              <div className="options">
                <button
                  type="button"
                  className={!afterDark ? "on" : ""}
                  onClick={() => setAfterDark(false)}
                >
                  standard
                </button>
                <button
                  type="button"
                  className={afterDark ? "on" : ""}
                  onClick={() => setAfterDark(true)}
                >
                  after-dark
                </button>
              </div>
            </div>
            <div
              style={{
                fontFamily: "Literata, serif",
                fontStyle: "italic",
                fontSize: 11,
                lineHeight: 1.55,
                color: "rgba(245,235,210,0.45)",
                marginTop: 14,
                paddingTop: 14,
                borderTop: "1px solid rgba(255,255,255,0.08)",
              }}
            >
              The book skins the room. Noir gets colder paper and sharper
              serifs; poetry gets airier line-height.
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
