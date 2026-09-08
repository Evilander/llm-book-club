"use client";

import { useEffect, useMemo, useState } from "react";
import { AgentSeal, type LamplightInk } from "@/components/lamplight";

interface SessionOpenerProps {
  bookTitle: string;
  mode: string;
  style?: string | null;
  sectionTitle?: string | null;
  isAfterDark?: boolean;
  desireLens?: string | null;
  onComplete: () => void;
}

interface CastMember {
  role: string;
  roleLabel: string;
  name: string;
  initial: string;
  ink: LamplightInk;
  line: string;
  phase: number;
}

const CORE_CAST: CastMember[] = [
  {
    role: "facilitator",
    roleLabel: "facilitator",
    name: "Sam",
    initial: "S",
    ink: "sam",
    line: "I'll keep the room moving and the questions sharp.",
    phase: 3,
  },
  {
    role: "close_reader",
    roleLabel: "close reader",
    name: "Ellis",
    initial: "E",
    ink: "ellis",
    line: "I'll slow down for the language that matters.",
    phase: 4,
  },
  {
    role: "skeptic",
    roleLabel: "skeptic",
    name: "Kit",
    initial: "K",
    ink: "kit",
    line: "I'll make sure every claim earns its place.",
    phase: 5,
  },
];

const AFTER_DARK_PERSONAS = {
  woman: { name: "Sable", initial: "v" },
  gay_man: { name: "Lucian", initial: "L" },
  trans_woman: { name: "Vesper", initial: "V" },
} as const;

type DesireLens = keyof typeof AFTER_DARK_PERSONAS;

const AFTER_DARK_LINE =
  "I'll trace what the page makes you feel before it tells you why.";

const PHASE_TIMERS = [
  { phase: 1, delay: 400 },
  { phase: 2, delay: 1200 },
  { phase: 3, delay: 2000 },
  { phase: 4, delay: 2800 },
  { phase: 5, delay: 3600 },
  { phase: 6, delay: 4200 },
] as const;

const COMPLETE_DELAY = 4800;

function usePrefersReducedMotion() {
  const [prefersReducedMotion, setPrefersReducedMotion] = useState(false);

  useEffect(() => {
    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    setPrefersReducedMotion(media.matches);

    const handleChange = () => setPrefersReducedMotion(media.matches);
    media.addEventListener("change", handleChange);
    return () => media.removeEventListener("change", handleChange);
  }, []);

  return prefersReducedMotion;
}

function getAfterDarkPersona(desireLens?: string | null) {
  if (desireLens && desireLens in AFTER_DARK_PERSONAS) {
    return AFTER_DARK_PERSONAS[desireLens as DesireLens];
  }
  return AFTER_DARK_PERSONAS.woman;
}

export function SessionOpener({
  bookTitle,
  mode,
  style,
  sectionTitle,
  isAfterDark,
  desireLens,
  onComplete,
}: SessionOpenerProps) {
  const [phase, setPhase] = useState(0);
  const prefersReducedMotion = usePrefersReducedMotion();
  const roomLabel = isAfterDark ? "After-dark room" : "Opening room";
  const sliceTitle = sectionTitle || "the selected passage";
  const sessionMode = style || mode;

  const cast = useMemo(() => {
    if (!isAfterDark) {
      return CORE_CAST;
    }

    const persona = getAfterDarkPersona(desireLens);
    return [
      ...CORE_CAST,
      {
        role: "after_dark_guide",
        roleLabel: "after-dark",
        name: persona.name,
        initial: persona.initial,
        ink: "sable" as const,
        line: AFTER_DARK_LINE,
        phase: 5,
      },
    ];
  }, [desireLens, isAfterDark]);

  useEffect(() => {
    if (prefersReducedMotion) {
      setPhase(6);
      const completeTimer = setTimeout(onComplete, 4200);
      return () => clearTimeout(completeTimer);
    }

    setPhase(0);
    const timers = [
      ...PHASE_TIMERS.map(({ phase: nextPhase, delay }) =>
        setTimeout(() => setPhase(nextPhase), delay)
      ),
      setTimeout(onComplete, COMPLETE_DELAY),
    ];
    return () => timers.forEach(clearTimeout);
  }, [onComplete, prefersReducedMotion]);

  return (
    <div className="opener-frame" aria-label={`${roomLabel} for ${bookTitle} in ${sessionMode} mode`}>
      <section aria-live="polite">
        {phase >= 0 ? (
          <>
            <div className="opener-rule opener-reveal">
              <span>FOLIO · §</span>
            </div>

            <p className="opener-eyebrow opener-reveal" aria-label={roomLabel}>
              <span aria-hidden="true">†</span>
              <span>{roomLabel}</span>
              <span aria-hidden="true">§</span>
            </p>
          </>
        ) : null}

        {phase >= 1 ? (
          <h1 className="opener-title opener-reveal">
            <span>A reading of</span>
            {bookTitle}
          </h1>
        ) : null}

        {phase >= 2 ? (
          <>
            <p className="opener-slice opener-reveal">
              Tonight&apos;s slice — <em>{sliceTitle}</em>
            </p>
            <div className="opener-asterism opener-reveal" aria-hidden="true">
              ⁂
            </div>
          </>
        ) : null}

        <ol className="opener-cast" aria-label="Tonight's cast">
          {cast.map((member) =>
            phase >= member.phase ? (
              <li
                key={member.role}
                className="opener-cast-line opener-reveal"
                data-agent={member.ink}
              >
                <span className="opener-cast-disc" aria-hidden="true">
                  <AgentSeal
                    initial={member.initial}
                    ink={member.ink}
                    className="h-10 w-10"
                  />
                </span>
                <p>
                  <span className="opener-cast-name">{member.name}</span>
                  <span className="opener-cast-role">, {member.roleLabel}</span>
                  <span aria-hidden="true"> — </span>
                  <span className="opener-cast-quote">"{member.line}"</span>
                </p>
              </li>
            ) : null
          )}
        </ol>

        {phase >= 6 ? (
          <p className="opener-finale opener-reveal">
            Entering the room <span aria-hidden="true">· · ·</span>
          </p>
        ) : null}

        <span className="opener-press">PRESS · MMXXVI</span>
      </section>
    </div>
  );
}
