"use client";

import { type ReactNode, useState } from "react";
import type { ShelfBook, ThresholdChoice } from "./types";

interface ThresholdProps {
  book: ShelfBook;
  setAfterDark: (v: boolean) => void;
  onEnter: (choice: ThresholdChoice) => void;
}

export function Threshold({ book, onEnter, setAfterDark }: ThresholdProps) {
  const [slice, setSlice] = useState("chapter-3");
  const [style, setStyle] = useState("thoughtful");
  const [goal, setGoal] = useState("close-read");
  const [disposition, setDisposition] = useState(0.5);
  const [adult, setAdult] = useState(false);
  const [confirmAge, setConfirmAge] = useState(false);

  const canEnter = style !== "sexy" || (adult && confirmAge);
  const dispositionLabel =
    disposition < 0.35
      ? "gentle"
      : disposition < 0.65
        ? "firm"
        : "adversarial";

  return (
    <div className="stage fade-in">
      <div
        style={{
          width: "min(92vw, 960px)",
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: 32,
        }}
      >
        <div
          style={{
            background: "rgba(20,16,14,0.6)",
            border: "1px solid rgba(245,235,210,0.1)",
            borderRadius: 2,
            padding: 36,
            color: "rgba(245,235,210,0.9)",
          }}
        >
          <div
            className="label"
            style={{ color: "rgba(245,235,210,0.45)", marginBottom: 6 }}
          >
            book
          </div>
          <div
            style={{
              fontFamily: "Literata, serif",
              fontSize: 22,
              fontWeight: 500,
              marginBottom: 4,
            }}
          >
            {book.title}
          </div>
          <div
            style={{
              fontFamily: "Literata, serif",
              fontStyle: "italic",
              fontSize: 13,
              color: "rgba(245,235,210,0.55)",
              marginBottom: 28,
            }}
          >
            {book.author}
          </div>

          <Field label="slice">
            <Choice
              v={slice}
              set={setSlice}
              opts={[
                ["chapter-3", "Ch. 3"],
                ["pp-72-94", "pp. 72–94"],
                ["marked", "your marks"],
                ["last", "where we left off"],
              ]}
            />
          </Field>

          <Field label="style">
            <Choice
              v={style}
              set={(v) => {
                setStyle(v);
                setAfterDark(v === "sexy");
              }}
              opts={[
                ["thoughtful", "thoughtful"],
                ["rigorous", "rigorous"],
                ["playful", "playful"],
                ["sexy", "after-dark"],
              ]}
            />
          </Field>

          <Field label="goal">
            <Choice
              v={goal}
              set={setGoal}
              opts={[
                ["close-read", "close-read"],
                ["argue", "argue"],
                ["orient", "orient"],
                ["memorize", "memorize"],
              ]}
            />
          </Field>

          <Field label={`kit's disposition · ${dispositionLabel}`}>
            <input
              type="range"
              min="0"
              max="1"
              step="0.01"
              value={disposition}
              onChange={(e) => setDisposition(parseFloat(e.target.value))}
              style={{ width: "100%", accentColor: "var(--rose)" }}
            />
          </Field>

          {style === "sexy" && (
            <div
              style={{
                marginTop: 20,
                padding: 16,
                background: "rgba(197,70,104,0.08)",
                border: "1px solid rgba(197,70,104,0.25)",
                borderRadius: 2,
              }}
            >
              <div className="label" style={{ color: "var(--rose)" }}>
                the door · 18+
              </div>
              <p
                style={{
                  fontFamily: "Literata, serif",
                  fontSize: 13,
                  fontStyle: "italic",
                  color: "rgba(245,235,210,0.75)",
                  lineHeight: 1.55,
                  margin: "8px 0 12px",
                }}
              >
                The room on the other side has different architecture. Warmer
                light, slower pendulum, closer air.
              </p>
              <label
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 10,
                  fontSize: 12,
                  marginBottom: 6,
                }}
              >
                <input
                  type="checkbox"
                  checked={confirmAge}
                  onChange={(e) => setConfirmAge(e.target.checked)}
                />
                I am 18 or older.
              </label>
              <label
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 10,
                  fontSize: 12,
                }}
              >
                <input
                  type="checkbox"
                  checked={adult}
                  onChange={(e) => setAdult(e.target.checked)}
                />
                Open the after-dark room.
              </label>
            </div>
          )}

          <button
            type="button"
            disabled={!canEnter}
            onClick={() =>
              onEnter({ slice, style, goal, disposition, adult })
            }
            style={{
              marginTop: 28,
              width: "100%",
              background: canEnter
                ? style === "sexy"
                  ? "rgba(197,70,104,0.25)"
                  : "rgba(200,134,31,0.22)"
                : "rgba(120,110,90,0.12)",
              border: `1px solid ${
                canEnter
                  ? style === "sexy"
                    ? "var(--rose)"
                    : "var(--amber)"
                  : "rgba(245,235,210,0.12)"
              }`,
              color: canEnter
                ? "rgba(250,240,220,0.95)"
                : "rgba(245,235,210,0.35)",
              padding: "14px",
              fontFamily: "JetBrains Mono, monospace",
              fontSize: 11,
              letterSpacing: "0.22em",
              textTransform: "uppercase",
              cursor: canEnter ? "pointer" : "not-allowed",
              borderRadius: 2,
              transition: "all 300ms ease",
            }}
          >
            Cross the threshold →
          </button>
        </div>

        <div style={{ position: "relative" }}>
          <div
            className="label"
            style={{ color: "rgba(245,235,210,0.4)", marginBottom: 10 }}
          >
            the room, assembling
          </div>
          <div
            style={{
              position: "relative",
              height: 440,
              background:
                style === "sexy"
                  ? "linear-gradient(140deg, #2a1620 0%, #180a12 100%)"
                  : "linear-gradient(140deg, #efe8da 0%, #d9d1c0 100%)",
              borderRadius: 2,
              padding: 26,
              transition: "all 800ms var(--spring-paper)",
              color: style === "sexy" ? "rgba(245,235,210,0.85)" : "var(--ink)",
              overflow: "hidden",
            }}
          >
            <div
              className="label"
              style={{
                color: style === "sexy" ? "var(--fuchsia)" : "var(--amber)",
              }}
            >
              {slice.replace("-", " · ")}
            </div>
            <p
              style={{
                fontFamily: "Literata, serif",
                fontSize: style === "sexy" ? 14 : 15,
                lineHeight: style === "sexy" ? 1.55 : 1.75,
                marginTop: 16,
                letterSpacing: style === "sexy" ? "-0.005em" : 0,
              }}
            >
              {style === "sexy" ? (
                <em>
                  Her hand hovered a half-inch above his sleeve. She did not
                  touch him. The room listened for the touch anyway.
                </em>
              ) : (
                "Year of the Depend Adult Undergarment. The tennis academy windows were glazed in that particular early-November light that makes everything look slightly borrowed."
              )}
            </p>
            <div
              style={{
                marginTop: 22,
                display: "flex",
                gap: 8,
                flexWrap: "wrap",
              }}
            >
              <Chip color="var(--amber)">Sam · guide</Chip>
              <Chip color="var(--teal)">Ellis · close read</Chip>
              <Chip color="var(--rose)">Kit · {dispositionLabel}</Chip>
              {style === "sexy" && adult && (
                <Chip color="var(--fuchsia)">Sable · after-dark</Chip>
              )}
            </div>

            <div
              style={{
                position: "absolute",
                bottom: 22,
                left: 26,
                right: 26,
                fontFamily: "Literata, serif",
                fontStyle: "italic",
                fontSize: 12,
                color:
                  style === "sexy"
                    ? "rgba(245,235,210,0.5)"
                    : "var(--ink-mute)",
                lineHeight: 1.55,
              }}
            >
              {style === "sexy"
                ? "— tighter line-height, warmer grain, slower spring physics. the pendulum slows when the door opens."
                : "— editorial restraint, calm motion, generous margins. the book opens onto the same room you sat in last night."}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <div style={{ marginBottom: 18 }}>
      <div
        className="label"
        style={{ color: "rgba(245,235,210,0.5)", marginBottom: 8 }}
      >
        {label}
      </div>
      {children}
    </div>
  );
}

function Choice({
  v,
  set,
  opts,
}: {
  v: string;
  set: (val: string) => void;
  opts: Array<[string, string]>;
}) {
  return (
    <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
      {opts.map(([val, lab]) => (
        <button
          key={val}
          type="button"
          onClick={() => set(val)}
          style={{
            flex: "1 1 auto",
            background:
              v === val
                ? "rgba(200,134,31,0.22)"
                : "rgba(245,235,210,0.04)",
            border: `1px solid ${v === val ? "var(--amber)" : "rgba(245,235,210,0.12)"}`,
            color:
              v === val
                ? "rgba(250,240,220,0.95)"
                : "rgba(245,235,210,0.7)",
            padding: "8px 12px",
            fontFamily: "Literata, serif",
            fontSize: 13,
            cursor: "pointer",
            borderRadius: 2,
            transition: "all 200ms ease",
          }}
        >
          {lab}
        </button>
      ))}
    </div>
  );
}

function Chip({ color, children }: { color: string; children: ReactNode }) {
  return (
    <div
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        padding: "4px 10px",
        border: `1px solid ${color}`,
        borderRadius: 20,
        fontFamily: "JetBrains Mono, monospace",
        fontSize: 10,
        letterSpacing: "0.12em",
        textTransform: "uppercase",
        color,
        background: `${color}11`,
      }}
    >
      <span
        style={{
          width: 5,
          height: 5,
          borderRadius: "50%",
          background: color,
        }}
      />
      {children}
    </div>
  );
}
