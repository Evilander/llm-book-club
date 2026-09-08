"use client";

import { useEffect, useMemo, useState } from "react";
import { ArrowLeft, Clock, Headphones, Loader2 } from "lucide-react";
import { toast } from "sonner";
import {
  AgentSeal,
  AntiqueMicrophone,
  Manicule,
  RibbonBookmark,
  SectionMark,
  WaxSeal,
} from "@/components/lamplight";
import { LocalAudiobookPlayer } from "@/components/local-audiobook-player";
import { API_BASE, cn, formatReadingTime } from "@/lib/utils";
import type { ExplorePayload } from "@/types/api";

interface SessionSetupProps {
  bookId: string;
  onBack: () => void;
  onStartSession: (sessionId: string) => void;
}

const MODES = [
  {
    id: "conversation",
    name: "Open Conversation",
    description: "Loose, companionable discussion that follows your curiosity.",
  },
  {
    id: "deep_dive",
    name: "Close Reading",
    description: "Zoom in on language, structure, and craft decisions.",
  },
  {
    id: "big_picture",
    name: "Themes and Meaning",
    description: "Map motifs, ideas, and what the reading slice is really doing.",
  },
  {
    id: "first_time",
    name: "First-Time Friendly",
    description: "Make difficult books feel welcoming without flattening them.",
  },
];

const STYLE_OPTIONS = [
  {
    id: "critical_analysis",
    label: "Critical analysis",
    description: "Sharper pushback, more evidence, more argument.",
  },
  {
    id: "fun",
    label: "Fun",
    description: "Livelier banter and more delight without losing the text.",
  },
  {
    id: "socratic",
    label: "Socratic",
    description: "Layered questions that help you think your way through it.",
  },
  {
    id: "sexy",
    label: "Sexy",
    description: "Tasteful flirtation and sensual energy when the text invites it.",
  },
  {
    id: "cozy",
    label: "Cozy",
    description: "Warm, restorative company for a daily reading ritual.",
  },
];

const READER_GOALS = [
  "Notice the craft",
  "Stay emotionally engaged",
  "Track themes and symbols",
  "Understand difficult passages",
  "Talk like a real book club",
];

const VOICE_PROFILES = [
  "Warm studio host",
  "Late-night radio companion",
  "Quiet library guide",
];

const DESIRE_LENSES = [
  {
    id: "woman",
    label: "Sexy woman",
    description: "Reads adult material through glamour, feminine confidence, and chemistry.",
  },
  {
    id: "gay_man",
    label: "Sexy gay man",
    description: "Reads adult material through masculine beauty, style, wit, and tension.",
  },
  {
    id: "trans_woman",
    label: "Sexy trans woman",
    description: "Reads adult material through trans feminine glamour, confidence, and desire.",
  },
];

const ADULT_INTENSITIES = [
  {
    id: "suggestive",
    label: "Suggestive",
    description: "Erotic, flirty, and clearly adult, but mostly implied rather than blunt.",
  },
  {
    id: "frank",
    label: "Frank",
    description: "More candid about lust, chemistry, and erotic intent while staying non-graphic.",
  },
];

const EROTIC_FOCUSES = [
  {
    id: "longing",
    label: "Longing",
    description: "Slow ache, withheld touch, and all the charged almosts.",
  },
  {
    id: "glamour",
    label: "Glamour",
    description: "Beauty, ritual, style, and the erotic force of presentation.",
  },
  {
    id: "power",
    label: "Power",
    description: "Control, surrender, bargaining, and who sets the terms of heat.",
  },
  {
    id: "tenderness",
    label: "Tenderness",
    description: "Softness, care, vulnerability, and erotic safety.",
  },
  {
    id: "transgression",
    label: "Transgression",
    description: "Secrets, danger, taboo, and the thrill of crossing a line.",
  },
];

const EXPERIENCE_MODES = [
  {
    id: "audio",
    label: "Conversational audio",
    description: "Agent turns speak automatically so the room feels like a live salon.",
  },
  {
    id: "text",
    label: "Text",
    description: "Classic chat reading with optional manual audio playback.",
  },
];

const AUTONOMY_LEVELS = [
  {
    id: "guided",
    label: "Guided",
    description: "Agents pause after each turn for your input before continuing.",
  },
  {
    id: "conversational",
    label: "Conversational",
    description: "Agents take 2-3 turns between your prompts. The default balance.",
  },
  {
    id: "salon",
    label: "Salon",
    description: "Agents discuss freely for 5-8 turns. You can interrupt anytime.",
  },
];

const TIME_OPTIONS = [10, 15, 20, 30, 45, 60];

type ExperienceMode = "audio" | "text";

type SessionPreset = {
  id: string;
  label: string;
  description: string;
  mode: string;
  style: string;
  experienceMode: ExperienceMode;
  autonomyLevel: string;
  timeBudget: number;
  readerGoal: string;
};

type SessionPreferencesDraft = {
  discussion_style: string;
  vibes: string[];
  voice_profile: string;
  reader_goal: string;
  experience_mode: ExperienceMode;
  desire_lens: string | null;
  adult_intensity: string | null;
  erotic_focus: string | null;
};

type SessionDraft = {
  mode: string;
  time_budget_min: number;
  section_ids: string[] | null;
  preferences: SessionPreferencesDraft;
  autonomy_level: string;
};

type StartSessionPayload = {
  book_id: string;
  mode: string;
  time_budget_min: number;
  section_ids: string[] | null;
  discussion_style: string;
  vibes: string[];
  voice_profile: string;
  reader_goal: string;
  experience_mode: ExperienceMode;
  autonomy_level: string;
  desire_lens: string | null;
  adult_intensity: string | null;
  erotic_focus: string | null;
};

const SESSION_PRESETS: SessionPreset[] = [
  {
    id: "daily_read",
    label: "Daily read",
    description: "Open the text, save progress, and keep the room calm.",
    mode: "conversation",
    style: "cozy",
    experienceMode: "text",
    autonomyLevel: "guided",
    timeBudget: 15,
    readerGoal: "Stay emotionally engaged",
  },
  {
    id: "audio_walk",
    label: "Audio walk",
    description: "Let the agents speak while you listen and interrupt when needed.",
    mode: "conversation",
    style: "fun",
    experienceMode: "audio",
    autonomyLevel: "conversational",
    timeBudget: 30,
    readerGoal: "Talk like a real book club",
  },
  {
    id: "close_read",
    label: "Close read",
    description: "Slow down for craft, citations, and sharp disagreement.",
    mode: "deep_dive",
    style: "critical_analysis",
    experienceMode: "text",
    autonomyLevel: "guided",
    timeBudget: 20,
    readerGoal: "Notice the craft",
  },
  {
    id: "after_dark",
    label: "After dark",
    description: "Candid adult interpretation with the text still in charge.",
    mode: "conversation",
    style: "sexy",
    experienceMode: "audio",
    autonomyLevel: "conversational",
    timeBudget: 20,
    readerGoal: "Stay emotionally engaged",
  },
];

const AFTER_DARK_PERSONAS: Record<string, { name: string; angle: string }> = {
  woman: {
    name: "Sable",
    angle: "glamour, feminine confidence, and the erotic precision of being watched",
  },
  gay_man: {
    name: "Lucian",
    angle: "style, masculine beauty, wit, and charged social chemistry",
  },
  trans_woman: {
    name: "Vesper",
    angle: "embodiment, self-fashioning, vulnerability, confidence, and becoming",
  },
};

const MODE_INVITATIONS: Record<string, string> = {
  conversation: "A live salon that follows your curiosity without getting sloppy.",
  deep_dive: "A tighter room that lingers over language, pattern, and craft pressure.",
  big_picture: "A room that keeps one eye on the page and one on the book's larger architecture.",
  first_time: "A welcoming room that helps difficult books open up without flattening them.",
};

const STYLE_INVITATIONS: Record<string, string> = {
  critical_analysis: "Expect sharper claims, cleaner evidence, and more satisfying disagreement.",
  fun: "Expect energy, wit, and a feeling that reading well can still be playful.",
  socratic: "Expect questions that keep opening the page instead of closing it too quickly.",
  sexy: "Expect a reading room that can admit desire, tension, and appetite without leaving the text behind.",
  cozy: "Expect warmth, steadiness, and a room you will want to come back to tomorrow night.",
};

function buildEroticInvitation(lens: string, intensity: string, focus: string) {
  const lensLabel =
    DESIRE_LENSES.find((item) => item.id === lens)?.label.toLowerCase() || "sexy lens";
  const intensityLabel =
    ADULT_INTENSITIES.find((item) => item.id === intensity)?.label.toLowerCase() || "adult";
  const focusLabel =
    EROTIC_FOCUSES.find((item) => item.id === focus)?.label.toLowerCase() || "desire";

  return `This room opens the book through a ${lensLabel} perspective with a ${intensityLabel} adult tone, tuned to ${focusLabel}. The goal is not crude shock. It is the kind of charged reading that makes glances, pauses, clothes, power, and confession feel impossible to skim.`;
}

function buildRoomPromise({
  mode,
  style,
  lens,
  focus,
  sectionTitle,
}: {
  mode: string;
  style: string;
  lens: string;
  focus: string;
  sectionTitle: string | null;
}) {
  const sectionLead = sectionTitle ? `Tonight's room is anchored in ${sectionTitle}. ` : "";
  const modeInvitation = MODE_INVITATIONS[mode] || MODE_INVITATIONS.conversation;
  const styleInvitation = STYLE_INVITATIONS[style] || STYLE_INVITATIONS.critical_analysis;

  if (style === "sexy") {
    const persona = AFTER_DARK_PERSONAS[lens]?.name || "the after-dark guide";
    const focusLabel =
      EROTIC_FOCUSES.find((item) => item.id === focus)?.label.toLowerCase() || "desire";
    return `${sectionLead}${modeInvitation} ${styleInvitation} ${persona} joins the room to track ${focusLabel}, chemistry, and self-presentation with a hotter but still citation-grounded sensibility.`;
  }

  return `${sectionLead}${modeInvitation} ${styleInvitation}`;
}

function buildStarterQuestions({
  style,
  sectionTitle,
  lens,
}: {
  style: string;
  sectionTitle: string | null;
  lens: string;
}) {
  const sectionLead = sectionTitle || "this slice";

  if (style === "sexy") {
    const persona = AFTER_DARK_PERSONAS[lens]?.name || "the after-dark guide";
    return [
      `Ask why ${sectionLead} feels charged instead of merely descriptive.`,
      `Let ${persona} trace how glamour, posture, clothes, or delay turn into desire.`,
      `Make the skeptic test whether the erotic reading is genuinely earned by the page.`,
    ];
  }

  return [
    `Ask what detail in ${sectionLead} a casual reader is most likely to miss.`,
    `Ask Ellis for a close reading and Kit for the strongest objection.`,
    `Ask what this slice wants you to feel before it tells you what it means.`,
  ];
}

function buildSlipSerial(bookId: string) {
  const cleaned = bookId.replace(/[^a-z0-9]/gi, "").toUpperCase();
  return cleaned.slice(0, 6).padEnd(6, "X");
}

function buildMonogram(title: string | undefined) {
  if (!title) {
    return "LB";
  }
  const letters = title
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() || "")
    .join("");
  return letters || "LB";
}

function numeralFor(index: number) {
  return ["I", "II", "III", "IV", "V", "VI", "VII", "VIII"][index] || `${index + 1}`;
}

function SectionHeading({ numeral, title }: { numeral: string; title: string }) {
  return (
    <div className="flex items-center gap-4 text-[10px] uppercase tracking-[0.22em] text-foxed font-label">
      <span>{`${numeral} · ${title}`}</span>
      <div className="h-px flex-1 bg-foxed/45" />
    </div>
  );
}

function StampButton({
  active,
  children,
  className,
  disabled,
  onClick,
}: {
  active?: boolean;
  children: React.ReactNode;
  className?: string;
  disabled?: boolean;
  onClick?: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={cn(
        "stamp transition-all duration-200",
        active
          ? "bg-[rgba(42,14,16,0.04)] shadow-[inset_0_0_0_1px_currentColor] hover:brightness-95"
          : "border-foxed/65 text-foxed/80 hover:border-brass hover:text-[var(--ink)]",
        disabled && "cursor-not-allowed opacity-45 hover:border-foxed/65 hover:text-foxed/80",
        className
      )}
      aria-pressed={active}
    >
      {children}
    </button>
  );
}

function AdultOptionCard({
  label,
  value,
  alt,
  disabled,
  options,
  selectedValue,
  onSelect,
}: {
  label: string;
  value: string;
  alt: string;
  disabled: boolean;
  options: { id: string; label: string }[];
  selectedValue: string;
  onSelect: (value: string) => void;
}) {
  return (
    <div
      className={cn(
        "border border-[rgba(91,26,42,0.35)] bg-cream px-4 py-4 transition-opacity",
        disabled && "opacity-55"
      )}
    >
      <p className="text-[9px] uppercase tracking-[0.18em] text-foxed font-label">{label}</p>
      <p className="mt-2 font-serif text-[28px] italic leading-none text-ink-sable">{value}</p>
      <p className="mt-3 text-[11px] leading-5 text-ink-pencil font-mono">{alt}</p>
      <div className="mt-4 flex flex-wrap gap-2">
        {options.map((option) => (
          <button
            key={option.id}
            type="button"
            onClick={() => onSelect(option.id)}
            disabled={disabled}
            className={cn(
              "rounded-[2px] border px-2.5 py-1.5 text-[10px] uppercase tracking-[0.18em] transition-colors font-label",
              selectedValue === option.id
                ? "border-[var(--ink-sable)] bg-[rgba(91,26,42,0.08)] text-ink-sable"
                : "border-foxed/40 text-ink-pencil hover:border-[var(--ink-sable)] hover:text-ink-sable",
              disabled &&
                "cursor-not-allowed border-foxed/30 text-ink-pencil/70 hover:border-foxed/30 hover:text-ink-pencil/70"
            )}
          >
            {option.label}
          </button>
        ))}
      </div>
    </div>
  );
}

export function SessionSetup({ bookId, onBack, onStartSession }: SessionSetupProps) {
  const [explore, setExplore] = useState<ExplorePayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [starting, setStarting] = useState(false);
  const [resumeApplied, setResumeApplied] = useState(false);
  const [selectedMode, setSelectedMode] = useState("conversation");
  const [selectedStyle, setSelectedStyle] = useState("critical_analysis");
  const [readerGoal, setReaderGoal] = useState(READER_GOALS[0]);
  const [voiceProfile, setVoiceProfile] = useState(VOICE_PROFILES[0]);
  const [experienceMode, setExperienceMode] = useState<ExperienceMode>("audio");
  const [desireLens, setDesireLens] = useState("woman");
  const [adultIntensity, setAdultIntensity] = useState("frank");
  const [eroticFocus, setEroticFocus] = useState("longing");
  const [adultConfirmed, setAdultConfirmed] = useState(false);
  const [autonomyLevel, setAutonomyLevel] = useState("conversational");
  const [timeBudget, setTimeBudget] = useState(20);
  const [selectedSections, setSelectedSections] = useState<string[]>([]);
  const [previewSectionId, setPreviewSectionId] = useState<string | null>(null);

  useEffect(() => {
    async function loadExplore(sectionId?: string | null) {
      setLoading(true);
      try {
        const params = new URLSearchParams();
        if (sectionId) {
          params.set("section_id", sectionId);
        }
        const response = await fetch(
          `${API_BASE}/v1/books/${bookId}/explore${params.toString() ? `?${params}` : ""}`
        );
        if (!response.ok) {
          throw new Error(`Explore request failed: ${response.status}`);
        }
        const data = (await response.json()) as ExplorePayload;
        setExplore(data);
        if (!previewSectionId && data.active_section?.id) {
          setPreviewSectionId(data.active_section.id);
        }
      } catch (error) {
        console.error("Failed to load book explorer:", error);
      } finally {
        setLoading(false);
      }
    }

    void loadExplore(previewSectionId);
  }, [bookId, previewSectionId]);

  useEffect(() => {
    const resumeSectionId = explore?.progress?.resume_section_id;
    if (!resumeApplied && resumeSectionId) {
      setPreviewSectionId(resumeSectionId);
      setSelectedSections((current) => (current.length > 0 ? current : [resumeSectionId]));
      setResumeApplied(true);
    }
  }, [explore?.progress?.resume_section_id, resumeApplied]);

  const slipIssuedAt = useMemo(() => new Date(), []);
  const slipDate = useMemo(
    () =>
      new Intl.DateTimeFormat("en-US", {
        day: "2-digit",
        month: "short",
        year: "numeric",
      }).format(slipIssuedAt),
    [slipIssuedAt]
  );
  const slipTime = useMemo(
    () =>
      new Intl.DateTimeFormat("en-US", {
        hour: "2-digit",
        minute: "2-digit",
      }).format(slipIssuedAt),
    [slipIssuedAt]
  );
  const slipSerial = useMemo(() => buildSlipSerial(bookId), [bookId]);

  const activeMode = MODES.find((mode) => mode.id === selectedMode) ?? MODES[0];
  const activeStyle = STYLE_OPTIONS.find((style) => style.id === selectedStyle) ?? STYLE_OPTIONS[0];
  const activeExperience =
    EXPERIENCE_MODES.find((mode) => mode.id === experienceMode) ?? EXPERIENCE_MODES[0];
  const activeAutonomy =
    AUTONOMY_LEVELS.find((level) => level.id === autonomyLevel) ?? AUTONOMY_LEVELS[0];
  const afterDarkPersona = AFTER_DARK_PERSONAS[desireLens] ?? AFTER_DARK_PERSONAS.woman;
  const topAudiobook = explore?.audiobook_matches?.[0] ?? null;
  const progress = explore?.progress ?? null;
  const previewSection =
    explore?.sections.find((section) => section.id === previewSectionId) ||
    explore?.active_section ||
    null;
  const totalSelectedTime = useMemo(() => {
    if (!explore || selectedSections.length === 0) {
      return null;
    }
    return explore.sections
      .filter((section) => selectedSections.includes(section.id))
      .reduce((total, section) => total + (section.reading_time_min || 5), 0);
  }, [explore, selectedSections]);
  const selectedSectionLabel =
    selectedSections.length === 0
      ? "Auto-select from the time budget"
      : `${selectedSections.length} section${selectedSections.length === 1 ? "" : "s"} selected`;
  const eroticInvitation = buildEroticInvitation(desireLens, adultIntensity, eroticFocus);
  const roomPromise = useMemo(
    () =>
      buildRoomPromise({
        mode: selectedMode,
        style: selectedStyle,
        lens: desireLens,
        focus: eroticFocus,
        sectionTitle: previewSection?.title || null,
      }),
    [desireLens, eroticFocus, previewSection?.title, selectedMode, selectedStyle]
  );
  const starterQuestions = useMemo(
    () =>
      buildStarterQuestions({
        style: selectedStyle,
        sectionTitle: previewSection?.title || null,
        lens: desireLens,
      }),
    [desireLens, previewSection?.title, selectedStyle]
  );
  const slipProgressPercent = progress?.reading_progress_pct ?? 0;
  const bookMonogram = buildMonogram(explore?.title);
  const adultDrawerRequested = selectedStyle === "sexy";
  const adultDrawerUnlocked = adultDrawerRequested && adultConfirmed;
  const adultControlsDisabled = !adultDrawerUnlocked;
  const draft: SessionDraft = {
    mode: selectedMode,
    time_budget_min: timeBudget,
    section_ids: selectedSections.length > 0 ? selectedSections : null,
    autonomy_level: autonomyLevel,
    preferences: {
      discussion_style: selectedStyle,
      vibes: [selectedStyle, readerGoal],
      voice_profile: voiceProfile,
      reader_goal: readerGoal,
      experience_mode: experienceMode,
      desire_lens: adultDrawerRequested ? desireLens : null,
      adult_intensity: adultDrawerRequested ? adultIntensity : null,
      erotic_focus: adultDrawerRequested ? eroticFocus : null,
    },
  };

  function toggleSection(sectionId: string) {
    setPreviewSectionId(sectionId);
    setSelectedSections((current) =>
      current.includes(sectionId)
        ? current.filter((id) => id !== sectionId)
        : [...current, sectionId]
    );
  }

  function applyPreset(preset: SessionPreset) {
    setSelectedMode(preset.mode);
    setSelectedStyle(preset.style);
    setExperienceMode(preset.experienceMode);
    setAutonomyLevel(preset.autonomyLevel);
    setTimeBudget(preset.timeBudget);
    setReaderGoal(preset.readerGoal);
  }

  function buildStartPayload(nextDraft: SessionDraft): StartSessionPayload {
    return {
      book_id: bookId,
      mode: nextDraft.mode,
      time_budget_min: nextDraft.time_budget_min,
      section_ids: nextDraft.section_ids,
      autonomy_level: nextDraft.autonomy_level,
      discussion_style: nextDraft.preferences.discussion_style,
      vibes: nextDraft.preferences.vibes,
      voice_profile: nextDraft.preferences.voice_profile,
      reader_goal: nextDraft.preferences.reader_goal,
      experience_mode: nextDraft.preferences.experience_mode,
      desire_lens: nextDraft.preferences.desire_lens,
      adult_intensity: nextDraft.preferences.adult_intensity,
      erotic_focus: nextDraft.preferences.erotic_focus,
    };
  }

  async function startSession(overrides?: Partial<SessionPreset>) {
    const nextStyle = overrides?.style ?? draft.preferences.discussion_style;
    const nextDraft: SessionDraft = {
      mode: overrides?.mode ?? draft.mode,
      time_budget_min: overrides?.timeBudget ?? draft.time_budget_min,
      section_ids: draft.section_ids,
      autonomy_level: overrides?.autonomyLevel ?? draft.autonomy_level,
      preferences: {
        discussion_style: nextStyle,
        vibes: [nextStyle, overrides?.readerGoal ?? draft.preferences.reader_goal],
        voice_profile: draft.preferences.voice_profile,
        reader_goal: overrides?.readerGoal ?? draft.preferences.reader_goal,
        experience_mode: overrides?.experienceMode ?? draft.preferences.experience_mode,
        desire_lens: nextStyle === "sexy" ? draft.preferences.desire_lens : null,
        adult_intensity: nextStyle === "sexy" ? draft.preferences.adult_intensity : null,
        erotic_focus: nextStyle === "sexy" ? draft.preferences.erotic_focus : null,
      },
    };

    setStarting(true);
    try {
      const response = await fetch(`${API_BASE}/v1/sessions/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(buildStartPayload(nextDraft)),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(
          data && typeof data.detail === "string" ? data.detail : `HTTP ${response.status}`
        );
      }
      if (!data.session_id) {
        throw new Error("Session start response did not include a session id.");
      }
      toast.success(
        nextStyle === "sexy" ? "After-dark room opening..." : "Opening your reading room..."
      );
      onStartSession(data.session_id as string);
    } catch (error) {
      console.error("Failed to start session:", error);
      toast.error(error instanceof Error ? error.message : "Failed to open room. Try again.");
    } finally {
      setStarting(false);
    }
  }

  const estimatedMinTurns = Math.ceil(timeBudget / 3);
  const estimatedMaxTurns = Math.ceil(timeBudget / 1.5);
  const estimatedMinCost = (estimatedMinTurns * 0.03).toFixed(2);
  const estimatedMaxCost = (estimatedMaxTurns * 0.06).toFixed(2);

  return (
    <div className={cn("space-y-4", adultDrawerRequested && "after-dark")}>
      <div className="flex flex-wrap items-center justify-between gap-3 text-[10px] uppercase tracking-[0.18em] text-foxed font-label">
        <button
          type="button"
          onClick={onBack}
          className="inline-flex items-center gap-2 text-left text-foxed transition-colors hover:text-cream"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          Return to the shelf
        </button>
        <div className="flex flex-wrap items-center justify-end gap-x-4 gap-y-1">
          <span>Lamplight Members&apos; Library</span>
          <span>{`Slip No. ${slipSerial}`}</span>
          <span>{`${slipDate} · ${slipTime}`}</span>
        </div>
      </div>

      <article className="relative overflow-hidden rounded-[2px] border border-[rgba(155,123,79,0.35)] bg-cream text-ink shadow-lamp-high">
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_18%_12%,rgba(155,123,79,.18),transparent_40%),radial-gradient(ellipse_at_82%_78%,rgba(155,123,79,.14),transparent_45%),radial-gradient(circle_at_30%_60%,rgba(110,80,40,.08)_0_2px,transparent_3px),radial-gradient(circle_at_70%_25%,rgba(110,80,40,.07)_0_1.5px,transparent_2.5px)]" />
        <div className="absolute right-6 top-0 sm:right-10">
          <RibbonBookmark percent={slipProgressPercent} className="h-24 w-7" />
        </div>

        <div className="relative p-6 sm:p-8 md:p-10">
          <header className="border-b border-foxed/65 pb-5 pr-12">
            <div className="flex flex-col gap-5 md:flex-row md:items-start md:justify-between">
              <div>
                <h2 className="font-serif text-[clamp(2rem,4vw,3.25rem)] italic leading-none text-ink">
                  Reading Room Checkout
                </h2>
                <p className="mt-4 max-w-2xl text-lg text-ink-pencil">
                  Mark the slip, choose the slice, and open the room.
                </p>
              </div>
              <div className="text-right text-[11px] uppercase tracking-[0.18em] text-foxed font-label">
                <p>{`Card · ${slipSerial}`}</p>
                <p className="mt-2">{`Issued · ${slipDate}`}</p>
                <p className="mt-2">{`Reader · Private Desk`}</p>
              </div>
            </div>
          </header>

          <div className="mt-8 space-y-10">
            <section className="space-y-5">
              <SectionHeading numeral="I" title="Volume & Slice" />

              <div className="grid gap-6 lg:grid-cols-[0.98fr_1.02fr]">
                <div className="space-y-5">
                  <div className="flex items-start gap-5">
                    <div className="flex h-28 w-16 shrink-0 items-center justify-center border border-[rgba(26,20,16,0.85)] bg-[linear-gradient(180deg,#3a1a1d,#1b0608)] shadow-[inset_-3px_0_0_rgba(196,154,74,.4),inset_3px_0_0_rgba(0,0,0,.4)]">
                      <span className="font-serif text-2xl tracking-[0.1em] text-brass">{bookMonogram}</span>
                    </div>

                    <div className="min-w-0 flex-1">
                      <p className="font-serif text-[clamp(1.9rem,3vw,2.75rem)] italic leading-tight text-ink">
                        {explore?.title || "Loading volume..."}
                      </p>
                      {explore?.author ? (
                        <p className="mt-2 text-base text-ink-pencil">{`- ${explore.author}`}</p>
                      ) : null}
                      <div className="mt-5 flex flex-wrap items-center gap-x-4 gap-y-2 text-[11px] uppercase tracking-[0.18em] text-ink-pencil font-label">
                        <span>{`${explore?.sections?.length || 0} sections`}</span>
                        <span>{`Issued for ${formatReadingTime(timeBudget)}`}</span>
                        <span>{explore?.file_type?.toUpperCase() || "BOOK"}</span>
                      </div>
                    </div>
                  </div>

                  <div className="space-y-2 border-t border-dotted border-foxed/80 pt-4">
                    <p className="text-[11px] uppercase tracking-[0.18em] text-ink-pencil font-label">Slice</p>
                    <p className="font-serif text-[clamp(1.5rem,2.5vw,2.2rem)] italic text-ink">
                      {previewSection?.title || "Pick a section to stage tonight's room."}
                    </p>
                    <div className="flex flex-wrap items-center gap-x-3 gap-y-2 text-[11px] uppercase tracking-[0.18em] text-ink-pencil font-label">
                      <span>{selectedSectionLabel}</span>
                      {totalSelectedTime ? <span>{formatReadingTime(totalSelectedTime)}</span> : null}
                      {progress?.resume_section_title ? (
                        <span>{`Resume point · ${progress.resume_section_title}`}</span>
                      ) : null}
                    </div>
                  </div>

                  {progress && (progress.total_units ?? 0) > 0 ? (
                    <div className="rounded-[2px] border border-foxed/40 bg-[rgba(196,154,74,0.08)] px-4 py-4">
                      <p className="text-[11px] uppercase tracking-[0.18em] text-foxed font-label">
                        Continue where you left off
                      </p>
                      <p className="mt-3 font-serif text-2xl italic text-ink">
                        {`${Math.round(progress.reading_progress_pct || 0)}% complete`}
                      </p>
                      <p className="mt-2 text-sm leading-6 text-ink-pencil">
                        {progress.current_unit_title
                          ? `Last marked stretch: ${progress.current_unit_title}.`
                          : "The current unit is already being tracked for you."}
                        {progress.resume_section_title
                          ? ` Resume will land on ${progress.resume_section_title}.`
                          : ""}
                      </p>
                    </div>
                  ) : null}

                  <div className="card-paper px-5 py-5">
                    <div className="flex items-center justify-between gap-3">
                      <p className="eyebrow text-foxed">Preview</p>
                      {explore?.active_section?.source_refs?.[0] ? (
                        <span className="text-[11px] uppercase tracking-[0.16em] text-ink-pencil font-label">
                          {explore.active_section.source_refs[0]}
                        </span>
                      ) : null}
                    </div>
                    {loading ? (
                      <div className="py-10 text-center text-sm text-ink-pencil">
                        <Loader2 className="mx-auto mb-3 h-5 w-5 animate-spin text-brass" />
                        Loading section preview...
                      </div>
                    ) : (
                      <p className="mt-4 whitespace-pre-wrap font-body text-[17px] leading-8 text-ink/90">
                        {explore?.active_section?.text?.slice(0, 900) ||
                          "Select a section on the right to see the active reading slice."}
                        {explore?.active_section?.text &&
                        explore.active_section.text.length > 900
                          ? " ..."
                          : ""}
                      </p>
                    )}
                  </div>

                  <div className="rounded-[2px] border border-foxed/35 bg-[rgba(26,20,16,0.04)] px-4 py-4">
                    <div className="flex items-center gap-3">
                      <Headphones className="h-4 w-4 text-[var(--ink-sam)]" />
                      <p className="text-[11px] uppercase tracking-[0.18em] text-foxed font-label">
                        Audio pairing
                      </p>
                    </div>
                    {topAudiobook ? (
                      <div className="mt-4">
                        <LocalAudiobookPlayer
                          match={topAudiobook}
                          bookTitle={explore?.title}
                          bookAuthor={explore?.author}
                          compact
                        />
                      </div>
                    ) : (
                      <p className="mt-4 text-sm leading-6 text-ink-pencil">
                        No strong local audiobook match is staged yet. Text mode is ready,
                        and the shelf will pick up audio automatically when a local match appears.
                      </p>
                    )}
                  </div>
                </div>

                <div className="space-y-4">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <p className="text-[11px] uppercase tracking-[0.18em] text-foxed font-label">
                      Available sections
                    </p>
                    <p className="text-[11px] uppercase tracking-[0.18em] text-ink-pencil font-label">
                      {selectedSections.length === 0
                        ? "Auto-select on launch"
                        : totalSelectedTime
                          ? `${formatReadingTime(totalSelectedTime)} selected`
                          : "Selection staged"}
                    </p>
                  </div>

                  <div className="max-h-[39rem] space-y-2 overflow-y-auto pr-1">
                    {explore?.sections?.map((section, index) => {
                      const active = previewSectionId === section.id;
                      const selected = selectedSections.includes(section.id);
                      return (
                        <button
                          key={section.id}
                          type="button"
                          onClick={() => toggleSection(section.id)}
                          className={cn(
                            "w-full rounded-[2px] border px-4 py-4 text-left transition-all duration-200",
                            active || selected
                              ? "border-[var(--ink-sam)] bg-[rgba(160,81,42,0.08)] shadow-[inset_0_0_0_1px_rgba(160,81,42,0.12)]"
                              : "border-foxed/35 bg-[rgba(255,255,255,0.22)] hover:border-brass/75 hover:bg-[rgba(196,154,74,0.08)]"
                          )}
                        >
                          <div className="flex items-start justify-between gap-3">
                            <div className="min-w-0 flex-1">
                              <div className="flex flex-wrap items-center gap-2">
                                <span className="text-[10px] uppercase tracking-[0.18em] text-foxed font-label">
                                  {numeralFor(index)}
                                </span>
                                <span className="text-[10px] uppercase tracking-[0.18em] text-ink-pencil font-label">
                                  {section.section_type}
                                </span>
                              </div>
                              <p className="mt-2 font-serif text-2xl italic leading-tight text-ink">
                                {section.title || `Section ${section.order_index + 1}`}
                              </p>
                              <p className="mt-2 line-clamp-3 text-sm leading-6 text-ink-pencil">
                                {section.preview_text || "No preview available yet."}
                              </p>
                            </div>
                            <div className="shrink-0 text-right">
                              <p className="text-[10px] uppercase tracking-[0.16em] text-ink-pencil font-label">
                                {formatReadingTime(section.reading_time_min || 5)}
                              </p>
                              <p
                                className={cn(
                                  "mt-2 text-[11px] uppercase tracking-[0.18em] font-label",
                                  selected ? "text-[var(--ink-sam)]" : "text-foxed"
                                )}
                              >
                                {selected ? "Selected" : active ? "Previewing" : "Stage"}
                              </p>
                            </div>
                          </div>
                        </button>
                      );
                    })}
                  </div>
                </div>
              </div>
            </section>

            <section className="space-y-5">
              <SectionHeading numeral="II" title="Mode & Style — Affix Stamps" />

              <div className="grid gap-5 lg:grid-cols-[0.95fr_1.05fr]">
                <div className="min-h-[10rem] rounded-[2px] border border-foxed/35 bg-[rgba(255,255,255,0.16)] px-4 py-4">
                  <p className="text-[10px] uppercase tracking-[0.18em] text-foxed font-label">
                    Current marks
                  </p>
                  <div className="mt-4 flex flex-wrap gap-3">
                    <StampButton active className="text-[var(--ink-ellis)]">
                      {activeMode.name}
                    </StampButton>
                    <StampButton
                      active
                      className={cn(
                        selectedStyle === "sexy"
                          ? "rotate-[2deg] text-[var(--ink-sable)]"
                          : "text-[var(--ink-ellis)]"
                      )}
                    >
                      {activeStyle.label}
                    </StampButton>
                    <StampButton
                      active
                      className={cn(
                        experienceMode === "audio"
                          ? "rotate-[-1.5deg] text-[var(--ink-sam)]"
                          : "text-[var(--ink-ellis)]"
                      )}
                    >
                      {activeExperience.label}
                    </StampButton>
                  </div>

                  <div className="mt-6 border-t border-dashed border-foxed/40 pt-4">
                    <p className="text-[10px] uppercase tracking-[0.18em] text-foxed font-label">
                      Prepared slips
                    </p>
                    <div className="mt-3 flex flex-wrap gap-2">
                      {SESSION_PRESETS.map((preset) => (
                        <StampButton
                          key={preset.id}
                          onClick={() => applyPreset(preset)}
                          active={
                            selectedMode === preset.mode &&
                            selectedStyle === preset.style &&
                            experienceMode === preset.experienceMode &&
                            autonomyLevel === preset.autonomyLevel &&
                            timeBudget === preset.timeBudget &&
                            readerGoal === preset.readerGoal
                          }
                          className={cn(
                            "text-[11px]",
                            preset.id === "after_dark" && "text-[var(--ink-sable)]"
                          )}
                        >
                          {preset.label}
                        </StampButton>
                      ))}
                    </div>
                  </div>
                </div>

                <div className="grid gap-4 sm:grid-cols-3">
                  <div className="border-l border-dashed border-foxed/50 pl-4 sm:col-span-1">
                    <p className="text-[10px] uppercase tracking-[0.18em] text-foxed font-label">
                      In the tray · mode
                    </p>
                    <div className="mt-3 flex flex-wrap gap-2">
                      {MODES.map((mode) => (
                        <StampButton
                          key={mode.id}
                          active={selectedMode === mode.id}
                          onClick={() => setSelectedMode(mode.id)}
                          className="text-[11px] text-ink-pencil"
                        >
                          {mode.name}
                        </StampButton>
                      ))}
                    </div>
                  </div>

                  <div className="border-l border-dashed border-foxed/50 pl-4 sm:col-span-1">
                    <p className="text-[10px] uppercase tracking-[0.18em] text-foxed font-label">
                      In the tray · tone
                    </p>
                    <div className="mt-3 flex flex-wrap gap-2">
                      {STYLE_OPTIONS.map((style) => (
                        <StampButton
                          key={style.id}
                          active={selectedStyle === style.id}
                          onClick={() => setSelectedStyle(style.id)}
                          className={cn(
                            "text-[11px]",
                            style.id === "sexy" ? "text-[var(--ink-sable)]" : "text-ink-pencil"
                          )}
                        >
                          {style.label}
                        </StampButton>
                      ))}
                    </div>
                  </div>

                  <div className="border-l border-dashed border-foxed/50 pl-4 sm:col-span-1">
                    <p className="text-[10px] uppercase tracking-[0.18em] text-foxed font-label">
                      In the tray · delivery
                    </p>
                    <div className="mt-3 flex flex-wrap gap-2">
                      {EXPERIENCE_MODES.map((mode) => (
                        <StampButton
                          key={mode.id}
                          active={experienceMode === mode.id}
                          onClick={() => setExperienceMode(mode.id as ExperienceMode)}
                          className={cn(
                            "text-[11px]",
                            mode.id === "audio" ? "text-[var(--ink-sam)]" : "text-ink-pencil"
                          )}
                        >
                          {mode.label}
                        </StampButton>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            </section>

            <section className="space-y-5">
              <SectionHeading numeral="III" title="After Dark — Sealed Compartment" />

              <div className="relative overflow-hidden rounded-[2px] border border-[rgba(91,26,42,0.48)] bg-[#efe1c4] px-5 pb-5 pt-8 shadow-[inset_0_0_0_6px_#efe1c4,inset_0_0_0_7px_rgba(91,26,42,.25)]">
                <div className="absolute inset-x-0 top-0 h-12 border-b border-foxed/35 bg-[linear-gradient(180deg,#e3d3b0,#efe1c4)] [clip-path:polygon(0_0,100%_0,50%_100%)]" />
                <div className="relative mx-auto flex h-20 w-20 items-center justify-center">
                  <WaxSeal sealed={!adultDrawerUnlocked} className="h-20 w-20" />
                </div>

                <div className="text-center">
                  <p className="text-[11px] uppercase tracking-[0.22em] text-ink-sable font-label">
                    {adultDrawerUnlocked
                      ? "Seal broken · 18+ confirmed"
                      : adultDrawerRequested
                        ? "Adult room requested · break the seal"
                        : "Compartment sealed · after-dark not selected"}
                  </p>
                  <p className="mt-3 font-serif text-2xl italic text-ink-sable">
                    {adultDrawerUnlocked
                      ? `${afterDarkPersona.name} joins the table.`
                      : adultDrawerRequested
                        ? "Late-room overlay waiting behind the wax."
                        : "Select the Sexy stamp if you want the sealed drawer."}
                  </p>
                  <p className="mx-auto mt-3 max-w-3xl text-sm leading-7 text-ink-pencil">
                    {adultDrawerRequested
                      ? eroticInvitation
                      : "This compartment holds adult-only framing for erotic material. Lens, intensity, and focus stay inactive until the Sexy stamp is chosen and the wax seal is deliberately broken."}
                  </p>
                </div>

                <div className="mt-5 flex flex-col gap-3 rounded-[2px] border border-[rgba(91,26,42,0.2)] bg-[rgba(255,255,255,0.36)] px-4 py-4 sm:flex-row sm:items-center sm:justify-between">
                  <div>
                    <p className="text-[11px] uppercase tracking-[0.18em] text-ink-sable font-label">
                      Reader acknowledgment
                    </p>
                    <p className="mt-2 text-sm leading-6 text-ink-pencil">
                      Adult mode is restricted to mature readers and unlocks candid erotic framing only when you intentionally break the seal.
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => adultDrawerRequested && setAdultConfirmed((current) => !current)}
                    disabled={!adultDrawerRequested}
                    className={cn(
                      "shrink-0 rounded-[2px] border px-4 py-3 text-[11px] uppercase tracking-[0.22em] transition-colors font-label",
                      adultDrawerUnlocked
                        ? "border-[var(--ink-sable)] bg-[rgba(91,26,42,0.08)] text-ink-sable hover:bg-[rgba(91,26,42,0.12)]"
                        : adultDrawerRequested
                          ? "border-[var(--ink-sable)] bg-transparent text-ink-sable hover:bg-[rgba(91,26,42,0.08)]"
                          : "cursor-not-allowed border-foxed/35 text-foxed/75"
                    )}
                  >
                    {adultDrawerUnlocked ? "Reseal compartment" : "Break the wax seal"}
                  </button>
                </div>

                <div className="mt-5 grid gap-4 lg:grid-cols-3">
                  <AdultOptionCard
                    label="Desire lens"
                    value={afterDarkPersona.name}
                    alt="Also available: Lucian · Vesper"
                    disabled={adultControlsDisabled}
                    options={DESIRE_LENSES.map((lens) => ({ id: lens.id, label: lens.label }))}
                    selectedValue={desireLens}
                    onSelect={setDesireLens}
                  />
                  <AdultOptionCard
                    label="Intensity"
                    value={ADULT_INTENSITIES.find((item) => item.id === adultIntensity)?.label || "Adult"}
                    alt="Also available: Suggestive"
                    disabled={adultControlsDisabled}
                    options={ADULT_INTENSITIES.map((item) => ({ id: item.id, label: item.label }))}
                    selectedValue={adultIntensity}
                    onSelect={setAdultIntensity}
                  />
                  <AdultOptionCard
                    label="Erotic focus"
                    value={EROTIC_FOCUSES.find((item) => item.id === eroticFocus)?.label || "Desire"}
                    alt="Also available: Longing · Power · Tenderness · Transgression"
                    disabled={adultControlsDisabled}
                    options={EROTIC_FOCUSES.map((item) => ({ id: item.id, label: item.label }))}
                    selectedValue={eroticFocus}
                    onSelect={setEroticFocus}
                  />
                </div>
              </div>
            </section>

            <section className="space-y-5">
              <SectionHeading numeral="IV" title="Reader&apos;s Hand" />

              <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
                <div>
                  <p className="text-[10px] uppercase tracking-[0.18em] text-foxed font-label">Reader goal</p>
                  <p className="mt-3 font-serif text-[30px] italic leading-tight text-ink">{readerGoal}</p>
                </div>
                <div>
                  <p className="text-[10px] uppercase tracking-[0.18em] text-foxed font-label">Voice profile</p>
                  <p className="mt-3 font-serif text-[30px] italic leading-tight text-ink">{voiceProfile}</p>
                </div>
                <div>
                  <p className="text-[10px] uppercase tracking-[0.18em] text-foxed font-label">Autonomy</p>
                  <p className="mt-3 font-serif text-[30px] italic leading-tight text-ink">
                    {activeAutonomy.label}
                  </p>
                  <p className="mt-2 text-sm text-ink-pencil">{activeAutonomy.description}</p>
                </div>
                <div>
                  <p className="text-[10px] uppercase tracking-[0.18em] text-foxed font-label">Time budget</p>
                  <p className="mt-3 font-serif text-[30px] italic leading-tight text-ink">
                    {formatReadingTime(timeBudget)}
                  </p>
                  <p className="mt-2 text-sm text-ink-pencil">{activeExperience.label}</p>
                </div>
              </div>

              <div className="grid gap-4 lg:grid-cols-2">
                <div className="rounded-[2px] border border-foxed/35 bg-[rgba(255,255,255,0.18)] px-4 py-4">
                  <p className="text-[10px] uppercase tracking-[0.18em] text-foxed font-label">
                    Reader goal
                  </p>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {READER_GOALS.map((goal) => (
                      <button
                        key={goal}
                        type="button"
                        onClick={() => setReaderGoal(goal)}
                        className={cn(
                          "rounded-[2px] border px-3 py-2 text-left text-[11px] uppercase tracking-[0.16em] transition-colors font-label",
                          readerGoal === goal
                            ? "border-[var(--ink-ellis)] bg-[rgba(42,14,16,0.04)] text-ink"
                            : "border-foxed/35 text-ink-pencil hover:border-brass hover:text-ink"
                        )}
                      >
                        {goal}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="rounded-[2px] border border-foxed/35 bg-[rgba(255,255,255,0.18)] px-4 py-4">
                  <div className="flex items-center gap-3">
                    <AntiqueMicrophone className="h-5 w-5 text-[var(--ink-sam)]" />
                    <p className="text-[10px] uppercase tracking-[0.18em] text-foxed font-label">
                      Voice profile
                    </p>
                  </div>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {VOICE_PROFILES.map((profile) => (
                      <button
                        key={profile}
                        type="button"
                        onClick={() => setVoiceProfile(profile)}
                        className={cn(
                          "rounded-[2px] border px-3 py-2 text-left text-[11px] uppercase tracking-[0.16em] transition-colors font-label",
                          voiceProfile === profile
                            ? "border-[var(--ink-sam)] bg-[rgba(160,81,42,0.08)] text-[var(--ink-sam)]"
                            : "border-foxed/35 text-ink-pencil hover:border-brass hover:text-ink"
                        )}
                      >
                        {profile}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="rounded-[2px] border border-foxed/35 bg-[rgba(255,255,255,0.18)] px-4 py-4">
                  <p className="text-[10px] uppercase tracking-[0.18em] text-foxed font-label">Autonomy</p>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {AUTONOMY_LEVELS.map((level) => (
                      <button
                        key={level.id}
                        type="button"
                        onClick={() => setAutonomyLevel(level.id)}
                        className={cn(
                          "rounded-[2px] border px-3 py-2 text-left text-[11px] uppercase tracking-[0.16em] transition-colors font-label",
                          autonomyLevel === level.id
                            ? "border-[var(--ink-ellis)] bg-[rgba(42,14,16,0.04)] text-ink"
                            : "border-foxed/35 text-ink-pencil hover:border-brass hover:text-ink"
                        )}
                      >
                        {level.label}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="rounded-[2px] border border-foxed/35 bg-[rgba(255,255,255,0.18)] px-4 py-4">
                  <div className="flex items-center gap-3">
                    <Clock className="h-4 w-4 text-brass" />
                    <p className="text-[10px] uppercase tracking-[0.18em] text-foxed font-label">
                      Time budget
                    </p>
                  </div>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {TIME_OPTIONS.map((time) => (
                      <button
                        key={time}
                        type="button"
                        onClick={() => setTimeBudget(time)}
                        className={cn(
                          "rounded-[2px] border px-3 py-2 text-left text-[11px] uppercase tracking-[0.16em] transition-colors font-label",
                          timeBudget === time
                            ? "border-brass bg-[rgba(196,154,74,0.12)] text-ink"
                            : "border-foxed/35 text-ink-pencil hover:border-brass hover:text-ink"
                        )}
                      >
                        {formatReadingTime(time)}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            </section>

            <section className="space-y-5">
              <SectionHeading numeral="V" title="Queries to Carry In" />

              <div className="grid gap-6 lg:grid-cols-[0.88fr_1.12fr]">
                <div className="card-paper px-5 py-5">
                  <p className="eyebrow text-foxed">First questions worth asking</p>
                  <div className="mt-4 space-y-3">
                    {starterQuestions.map((question) => (
                      <div
                        key={question}
                        className="border-l border-foxed/45 pl-4 text-sm leading-7 text-ink-pencil"
                      >
                        {question}
                      </div>
                    ))}
                  </div>
                </div>

                <div className="border-t border-foxed/65 px-2 pt-5">
                  <div className="flex flex-wrap items-center gap-3">
                    <AgentSeal initial="S" ink="sam" className="h-8 w-8" />
                    <span className="text-xl text-ink-pencil font-mono">Sam</span>
                    <AgentSeal initial="E" ink="ellis" className="h-8 w-8" />
                    <span className="text-xl text-ink-pencil font-mono">Ellis</span>
                    <AgentSeal initial="K" ink="kit" className="h-8 w-8" />
                    <span className="text-xl text-ink-pencil font-mono">Kit</span>
                    {adultDrawerRequested ? (
                      <>
                        <AgentSeal
                          initial={afterDarkPersona.name.slice(0, 1)}
                          ink="sable"
                          className="h-8 w-8"
                        />
                        <span className="text-xl text-[var(--ink-sable)] font-mono">
                          {afterDarkPersona.name}
                        </span>
                      </>
                    ) : null}
                  </div>

                  <div className="mt-6 flex gap-4">
                    <SectionMark className="mt-1 h-6 w-6 shrink-0 text-brass" />
                    <div>
                      <p className="font-serif text-[clamp(1.6rem,2.9vw,3.2rem)] italic leading-[1.45] text-[var(--ink-sable)]">
                        {roomPromise}
                      </p>
                      <p className="mt-4 font-serif text-lg italic text-ink-pencil">
                        - endorsed by the night librarian, in wine ink
                      </p>
                    </div>
                  </div>
                </div>
              </div>
            </section>
          </div>

          <footer className="mt-8 border-t border-foxed/65 pt-6">
            <div className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
              <div className="space-y-4">
                <div className="inline-flex rotate-[-4deg] border-2 border-[var(--ink-ellis)] px-4 py-2 font-serif text-lg font-semibold uppercase tracking-[0.14em] text-[var(--ink-ellis)]">
                  {`Checked Out · ${slipDate}`}
                </div>
                <div className="space-y-1 text-[11px] uppercase tracking-[0.18em] text-ink-pencil font-label">
                  <p>{`Est. cost per turn · approx $0.02-$0.08`}</p>
                  <p>{`${timeBudget} min session · ${estimatedMinTurns}-${estimatedMaxTurns} turns · approx $${estimatedMinCost}-$${estimatedMaxCost}`}</p>
                </div>
              </div>

              <button
                type="button"
                onClick={() => void startSession()}
                disabled={starting || loading || (adultDrawerRequested && !adultConfirmed)}
                className={cn(
                  "inline-flex min-h-16 items-center justify-center gap-3 rounded-[2px] px-6 py-4 text-center font-serif text-xl uppercase tracking-[0.14em] text-[#2a1a08] shadow-[inset_0_1px_0_rgba(255,235,190,.7),inset_0_-2px_0_rgba(60,40,10,.4),0_2px_0_#5a3f10,0_8px_18px_rgba(0,0,0,.35)] transition-all",
                  "bg-[linear-gradient(180deg,#e8be72,#c49a4a_55%,#8e6a26)] hover:brightness-[1.03] disabled:cursor-not-allowed disabled:opacity-60 disabled:hover:brightness-100"
                )}
              >
                {starting ? (
                  <>
                    <Loader2 className="h-5 w-5 animate-spin" />
                    Opening the room...
                  </>
                ) : (
                  <>
                    Open the room
                    <Manicule className="h-5 w-5 text-[#2a1a08]" />
                  </>
                )}
              </button>
            </div>
          </footer>
        </div>
      </article>
    </div>
  );
}
