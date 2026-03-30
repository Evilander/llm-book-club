"use client";

import { useEffect, useMemo, useState } from "react";
import {
  ArrowLeft,
  BookOpen,
  Clock,
  Headphones,
  Loader2,
  Mic2,
  Play,
  Quote,
  Sparkles,
  Wand2,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { API_BASE, cn, formatReadingTime } from "@/lib/utils";

interface ExploreSection {
  id: string;
  title: string | null;
  section_type: string;
  order_index: number;
  reading_time_min: number | null;
  page_start: number | null;
  page_end: number | null;
  preview_text: string;
}

interface ActiveSection extends ExploreSection {
  text: string;
  chunk_count: number;
  source_refs: string[];
}

interface AudiobookMatch {
  path: string;
  filename: string;
  extension: string;
  size_bytes: number;
  title_guess: string;
  parent_folder: string | null;
  match_score: number | null;
  match_reason: string | null;
}

interface ExplorePayload {
  book_id: string;
  title: string;
  author: string | null;
  filename: string;
  file_type: string;
  total_chars: number | null;
  source_path: string | null;
  sections: ExploreSection[];
  active_section: ActiveSection | null;
  audiobook_matches: AudiobookMatch[];
  has_local_audiobook: boolean;
  audiobooks_dir: string | null;
}

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

const TIME_OPTIONS = [10, 15, 20, 30, 45, 60];

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

function buildEroticInvitation(
  lens: string,
  intensity: string,
  focus: string
) {
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
    const focusLabel = EROTIC_FOCUSES.find((item) => item.id === focus)?.label.toLowerCase() || "desire";
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

export function SessionSetup({ bookId, onBack, onStartSession }: SessionSetupProps) {
  const [explore, setExplore] = useState<ExplorePayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [starting, setStarting] = useState(false);
  const [selectedMode, setSelectedMode] = useState("conversation");
  const [selectedStyle, setSelectedStyle] = useState("critical_analysis");
  const [readerGoal, setReaderGoal] = useState(READER_GOALS[0]);
  const [voiceProfile, setVoiceProfile] = useState(VOICE_PROFILES[0]);
  const [experienceMode, setExperienceMode] = useState<"audio" | "text">("audio");
  const [desireLens, setDesireLens] = useState("woman");
  const [adultIntensity, setAdultIntensity] = useState("frank");
  const [eroticFocus, setEroticFocus] = useState("longing");
  const [adultConfirmed, setAdultConfirmed] = useState(false);
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
        const res = await fetch(
          `${API_BASE}/v1/books/${bookId}/explore${params.toString() ? `?${params}` : ""}`
        );
        const data = await res.json();
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

    loadExplore(previewSectionId);
  }, [bookId, previewSectionId]);

  const totalSelectedTime = useMemo(() => {
    if (!explore || selectedSections.length === 0) {
      return null;
    }
    return explore.sections
      .filter((section) => selectedSections.includes(section.id))
      .reduce((total, section) => total + (section.reading_time_min || 5), 0);
  }, [explore, selectedSections]);

  function toggleSection(sectionId: string) {
    setPreviewSectionId(sectionId);
    setSelectedSections((prev) =>
      prev.includes(sectionId)
        ? prev.filter((id) => id !== sectionId)
        : [...prev, sectionId]
    );
  }

  async function startSession() {
    setStarting(true);
    try {
      const res = await fetch(`${API_BASE}/v1/sessions/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          book_id: bookId,
          mode: selectedMode,
          time_budget_min: timeBudget,
          section_ids: selectedSections.length > 0 ? selectedSections : null,
          discussion_style: selectedStyle,
          reader_goal: readerGoal,
          voice_profile: voiceProfile,
          vibes: [selectedStyle, readerGoal],
          experience_mode: experienceMode,
          desire_lens: selectedStyle === "sexy" ? desireLens : null,
          adult_intensity: selectedStyle === "sexy" ? adultIntensity : null,
          erotic_focus: selectedStyle === "sexy" ? eroticFocus : null,
        }),
      });
      const data = await res.json();
      if (data.session_id) {
        onStartSession(data.session_id);
      }
    } catch (error) {
      console.error("Failed to start session:", error);
    } finally {
      setStarting(false);
    }
  }

  const topAudiobook = explore?.audiobook_matches?.[0] ?? null;
  const eroticInvitation = buildEroticInvitation(desireLens, adultIntensity, eroticFocus);
  const previewSection =
    explore?.sections.find((section) => section.id === previewSectionId) ||
    explore?.active_section ||
    null;
  const afterDarkPersona = AFTER_DARK_PERSONAS[desireLens] || AFTER_DARK_PERSONAS.woman;
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

  return (
    <div className={cn("space-y-8", selectedStyle === "sexy" && "after-dark")}>
      <div className="flex items-center gap-4">
        <Button variant="ghost" size="icon" onClick={onBack} className="shrink-0">
          <ArrowLeft className="w-5 h-5" />
        </Button>
        <div>
          <h2 className="text-2xl font-bold font-serif">Build tonight&apos;s reading room</h2>
          <p className="text-sm text-muted-foreground">
            Pick the energy, preview the slice, then open the conversation.
          </p>
        </div>
      </div>

      <Card glass className="overflow-hidden">
        <CardContent className="p-0">
          <div className="grid gap-0 md:grid-cols-[1.1fr_0.9fr]">
            <div className="p-6">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="text-xs uppercase tracking-[0.25em] text-primary/80 font-label">
                    Now staging
                  </p>
                  <h3 className="mt-2 text-2xl font-semibold">
                    {explore?.title || "Loading book..."}
                  </h3>
                  {explore?.author && (
                    <p className="mt-1 text-sm text-muted-foreground">{explore.author}</p>
                  )}
                </div>
                <Badge variant="outline" className="shrink-0">
                  {explore?.file_type?.toUpperCase() || "BOOK"}
                </Badge>
              </div>

              <div className="mt-4 flex flex-wrap gap-2">
                <Badge variant="secondary" className="gap-1">
                  <BookOpen className="w-3 h-3" />
                  {explore?.sections?.length || 0} sections
                </Badge>
                <Badge variant="secondary" className="gap-1">
                  <Clock className="w-3 h-3" />
                  {formatReadingTime(timeBudget)}
                </Badge>
                <Badge
                  variant={topAudiobook ? "success" : "outline"}
                  className="gap-1"
                >
                  <Headphones className="w-3 h-3" />
                  {topAudiobook ? "Audiobook matched" : "No local audiobook yet"}
                </Badge>
              </div>

              <div className="mt-6 rounded-2xl border border-white/10 bg-black/20 p-4">
                <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-[0.2em] text-muted-foreground">
                  <Quote className="w-3.5 h-3.5" />
                  Preview
                </div>
                {loading ? (
                  <div className="py-8 text-center text-sm text-muted-foreground">
                    <Loader2 className="mx-auto mb-3 h-5 w-5 animate-spin text-primary" />
                    Loading section preview...
                  </div>
                ) : (
                  <>
                    <p className="mt-3 text-sm leading-7 text-foreground/90 font-serif">
                      {explore?.active_section?.text?.slice(0, 900) ||
                        "Pick a section to preview the text here."}
                      {explore?.active_section?.text &&
                        explore.active_section.text.length > 900 &&
                        " ..."}
                    </p>
                    {explore?.active_section?.source_refs?.length ? (
                      <div className="mt-3 flex flex-wrap gap-2">
                        {explore.active_section.source_refs.slice(0, 3).map((ref) => (
                          <Badge key={ref} variant="outline">
                            {ref}
                          </Badge>
                        ))}
                      </div>
                    ) : null}
                  </>
                )}
              </div>
            </div>

            <div className="border-t border-white/10 bg-white/[0.02] p-6 md:border-l md:border-t-0">
              <div className="flex items-center gap-2 text-sm font-medium">
                <Headphones className="h-4 w-4 text-primary" />
                Audio pairing
              </div>
              {topAudiobook ? (
                <div className="mt-4 rounded-2xl border border-emerald-500/20 bg-emerald-500/5 p-4">
                  <p className="font-medium">{topAudiobook.title_guess}</p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {topAudiobook.match_reason || "Strong local match"}
                  </p>
                  <p className="mt-3 text-xs text-muted-foreground">
                    {topAudiobook.parent_folder || topAudiobook.filename}
                  </p>
                </div>
              ) : (
                <div className="mt-4 rounded-2xl border border-dashed border-white/10 bg-black/10 p-4 text-sm text-muted-foreground">
                  No strong local audiobook match surfaced from your configured audio
                  library. I left the shelf ready for local pairing, but not for tracker
                  automation.
                </div>
              )}

              <div className="mt-6">
                <p className="text-sm font-medium">Narration mood</p>
                <div className="mt-3 space-y-2">
                  {VOICE_PROFILES.map((profile) => (
                    <button
                      key={profile}
                      type="button"
                      onClick={() => setVoiceProfile(profile)}
                      className={cn(
                        "flex w-full items-center justify-between rounded-xl border px-3 py-2 text-left text-sm transition-colors",
                        voiceProfile === profile
                          ? "border-primary/50 bg-primary/10"
                          : "border-white/10 bg-black/10 hover:border-primary/30"
                      )}
                    >
                      <span>{profile}</span>
                      <Mic2 className="h-4 w-4 text-muted-foreground" />
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {selectedStyle === "sexy" ? (
        <Card className="overflow-hidden border-rose-500/20 bg-[radial-gradient(circle_at_top_left,rgba(244,63,94,0.18),transparent_40%),radial-gradient(circle_at_bottom_right,rgba(251,191,36,0.16),transparent_35%),rgba(15,15,20,0.92)]">
          <CardContent className="grid gap-6 p-6 lg:grid-cols-[1.15fr_0.85fr]">
            <div>
              <p className="text-xs uppercase tracking-[0.28em] text-rose-200/80 font-label">
                After-Dark Reading Room
              </p>
              <h3 className="mt-2 text-2xl font-semibold text-white font-serif">
                Build a book conversation with real erotic voltage
              </h3>
              <p className="mt-3 max-w-2xl text-sm leading-7 text-rose-50/85">
                {eroticInvitation}
              </p>
              <div className="mt-4 rounded-2xl border border-white/10 bg-black/20 p-4">
                <p className="text-sm font-medium text-white">
                  {afterDarkPersona.name} enters this room for {afterDarkPersona.angle}.
                </p>
                <p className="mt-2 text-sm leading-6 text-rose-50/75">
                  The point is not generic dirty talk. It is to make the page feel hotter, stranger,
                  more vulnerable, and more alive by naming what the text is already doing.
                </p>
              </div>
              <div className="mt-4 flex flex-wrap gap-2">
                <Badge variant="secondary">{DESIRE_LENSES.find((item) => item.id === desireLens)?.label}</Badge>
                <Badge variant="secondary">{ADULT_INTENSITIES.find((item) => item.id === adultIntensity)?.label}</Badge>
                <Badge variant="secondary">{EROTIC_FOCUSES.find((item) => item.id === eroticFocus)?.label}</Badge>
              </div>
            </div>

            <div className="rounded-3xl border border-white/10 bg-black/25 p-5">
              <p className="text-sm font-medium text-white">18+ room gate</p>
              <p className="mt-2 text-sm leading-6 text-rose-50/75">
                This mode is for adult readers discussing erotic material in candid,
                age-restricted language. It still avoids graphic sexual detail.
              </p>
              <label className="mt-4 flex cursor-pointer items-start gap-3 rounded-2xl border border-white/10 bg-white/[0.04] p-4">
                <input
                  type="checkbox"
                  checked={adultConfirmed}
                  onChange={(event) => setAdultConfirmed(event.target.checked)}
                  className="mt-1 h-4 w-4 rounded border-white/20 bg-transparent text-primary"
                />
                <span className="text-sm leading-6 text-rose-50/85">
                  I understand this opens an adult-only reading room with erotic framing,
                  candid desire talk, and sensual atmosphere intended for mature readers.
                </span>
              </label>
            </div>
          </CardContent>
        </Card>
      ) : null}

      <div>
        <h3 className="mb-4 flex items-center gap-2 text-lg font-semibold">
          <Sparkles className="h-5 w-5 text-primary" />
          Conversation shape
        </h3>
        <div className="grid gap-3 md:grid-cols-2">
          {MODES.map((mode) => (
            <Card
              key={mode.id}
              className={cn(
                "cursor-pointer border-white/10 bg-card/80 transition-all hover:-translate-y-0.5 hover:border-primary/40",
                selectedMode === mode.id && "border-primary/60 bg-primary/5 shadow-glow"
              )}
              onClick={() => setSelectedMode(mode.id)}
            >
              <CardContent className="p-4">
                <p className="font-medium">{mode.name}</p>
                <p className="mt-1 text-sm text-muted-foreground">{mode.description}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>

      <div>
        <h3 className="mb-4 flex items-center gap-2 text-lg font-semibold">
          <Wand2 className="h-5 w-5 text-primary" />
          Social tone
        </h3>
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {STYLE_OPTIONS.map((option) => (
            <button
              key={option.id}
              type="button"
              onClick={() => setSelectedStyle(option.id)}
              className={cn(
                "rounded-2xl border px-4 py-4 text-left transition-all",
                selectedStyle === option.id
                  ? "border-primary/60 bg-primary/10"
                  : "border-white/10 bg-black/10 hover:border-primary/30"
              )}
            >
              <p className="font-medium">{option.label}</p>
              <p className="mt-1 text-sm text-muted-foreground">{option.description}</p>
            </button>
          ))}
        </div>
      </div>

      <Card className="overflow-hidden border-white/10 bg-[radial-gradient(circle_at_top_left,rgba(249,115,22,0.16),transparent_30%),rgba(10,10,14,0.9)]">
        <CardContent className="grid gap-6 p-6 lg:grid-cols-[1.1fr_0.9fr]">
          <div>
            <p className="text-xs uppercase tracking-[0.28em] text-primary/80 font-label">
              Why This Session Will Work
            </p>
            <h3 className="mt-2 text-2xl font-semibold text-white font-serif">
              A room built to make reading harder to abandon
            </h3>
            <p className="mt-3 max-w-2xl text-sm leading-7 text-white/80">
              {roomPromise}
            </p>
            <div className="mt-4 flex flex-wrap gap-2">
              <Badge variant="secondary">{MODES.find((mode) => mode.id === selectedMode)?.name}</Badge>
              <Badge variant="secondary">{STYLE_OPTIONS.find((style) => style.id === selectedStyle)?.label}</Badge>
              <Badge variant="secondary">{readerGoal}</Badge>
              <Badge variant="secondary">{experienceMode === "audio" ? "Live audio room" : "Text room"}</Badge>
            </div>
          </div>

          <div className="rounded-3xl border border-white/10 bg-black/25 p-5">
            <p className="text-sm font-medium text-white">First questions worth asking</p>
            <div className="mt-4 space-y-3">
              {starterQuestions.map((question) => (
                <div
                  key={question}
                  className="rounded-2xl border border-white/10 bg-white/[0.04] px-4 py-3 text-sm leading-6 text-white/85"
                >
                  {question}
                </div>
              ))}
            </div>
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-6 lg:grid-cols-[1.2fr_0.8fr]">
        <Card className="border-white/10 bg-card/80">
          <CardContent className="p-5">
            <div className="flex items-center justify-between gap-4">
              <h3 className="flex items-center gap-2 text-lg font-semibold">
                <BookOpen className="h-5 w-5 text-primary" />
                Choose the slice
              </h3>
              <Badge variant="outline">
                {selectedSections.length === 0
                  ? "Auto-select from time budget"
                  : `${selectedSections.length} selected${
                      totalSelectedTime ? ` (${formatReadingTime(totalSelectedTime)})` : ""
                    }`}
              </Badge>
            </div>

            <div className="mt-4 grid max-h-[420px] gap-2 overflow-y-auto pr-1">
              {explore?.sections?.map((section) => {
                const active = previewSectionId === section.id;
                const selected = selectedSections.includes(section.id);
                return (
                  <button
                    key={section.id}
                    type="button"
                    onClick={() => toggleSection(section.id)}
                    className={cn(
                      "rounded-2xl border px-4 py-3 text-left transition-all",
                      active || selected
                        ? "border-primary/50 bg-primary/8"
                        : "border-white/10 bg-black/10 hover:border-primary/30"
                    )}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="font-medium">
                          {section.title || `Section ${section.order_index + 1}`}
                        </p>
                        <p className="mt-1 text-xs uppercase tracking-wide text-muted-foreground">
                          {section.section_type}
                        </p>
                        <p className="mt-2 text-sm text-muted-foreground">
                          {section.preview_text || "No preview available yet."}
                        </p>
                      </div>
                      <Badge variant={selected ? "default" : "outline"}>
                        {formatReadingTime(section.reading_time_min || 5)}
                      </Badge>
                    </div>
                  </button>
                );
              })}
            </div>
          </CardContent>
        </Card>

        <div className="space-y-6">
          {selectedStyle === "sexy" ? (
            <Card className="border-white/10 bg-card/80">
              <CardContent className="p-5">
                <h3 className="text-lg font-semibold">Desire lens</h3>
                <p className="mt-2 text-sm text-muted-foreground">
                  For erotic or adult material, steer the sensual commentary through one
                  of these characterful points of view. The conversation stays tasteful,
                  consensual, and citation-grounded.
                </p>
                <div className="mt-3 rounded-2xl border border-primary/20 bg-primary/5 px-4 py-3">
                  <p className="text-sm font-medium text-foreground">{afterDarkPersona.name}</p>
                  <p className="mt-1 text-sm leading-6 text-muted-foreground">
                    Current angle: {afterDarkPersona.angle}.
                  </p>
                </div>
                <div className="mt-4 space-y-2">
                  {DESIRE_LENSES.map((lens) => (
                    <button
                      key={lens.id}
                      type="button"
                      onClick={() => setDesireLens(lens.id)}
                      className={cn(
                        "w-full rounded-2xl border px-4 py-3 text-left transition-colors",
                        desireLens === lens.id
                          ? "border-primary/50 bg-primary/10"
                          : "border-white/10 bg-black/10 hover:border-primary/30"
                      )}
                    >
                      <p className="font-medium">{lens.label}</p>
                      <p className="mt-1 text-sm text-muted-foreground">{lens.description}</p>
                    </button>
                  ))}
                </div>
              </CardContent>
            </Card>
          ) : null}

          {selectedStyle === "sexy" ? (
            <Card className="border-white/10 bg-card/80">
              <CardContent className="p-5">
                <h3 className="text-lg font-semibold">Adult intensity</h3>
                <p className="mt-2 text-sm text-muted-foreground">
                  This room can be age-restricted and openly erotic in tone. It stays
                  on the candid side of adult conversation without turning into graphic
                  explicit detail.
                </p>
                <div className="mt-4 space-y-2">
                  {ADULT_INTENSITIES.map((intensity) => (
                    <button
                      key={intensity.id}
                      type="button"
                      onClick={() => setAdultIntensity(intensity.id)}
                      className={cn(
                        "w-full rounded-2xl border px-4 py-3 text-left transition-colors",
                        adultIntensity === intensity.id
                          ? "border-primary/50 bg-primary/10"
                          : "border-white/10 bg-black/10 hover:border-primary/30"
                      )}
                    >
                      <p className="font-medium">{intensity.label}</p>
                      <p className="mt-1 text-sm text-muted-foreground">
                        {intensity.description}
                      </p>
                    </button>
                  ))}
                </div>
              </CardContent>
            </Card>
          ) : null}

          {selectedStyle === "sexy" ? (
            <Card className="border-white/10 bg-card/80">
              <CardContent className="p-5">
                <h3 className="text-lg font-semibold">Erotic focus</h3>
                <p className="mt-2 text-sm text-muted-foreground">
                  Choose what kind of arousal and anticipation the room should keep
                  returning to as it reads.
                </p>
                <div className="mt-4 space-y-2">
                  {EROTIC_FOCUSES.map((focus) => (
                    <button
                      key={focus.id}
                      type="button"
                      onClick={() => setEroticFocus(focus.id)}
                      className={cn(
                        "w-full rounded-2xl border px-4 py-3 text-left transition-colors",
                        eroticFocus === focus.id
                          ? "border-primary/50 bg-primary/10"
                          : "border-white/10 bg-black/10 hover:border-primary/30"
                      )}
                    >
                      <p className="font-medium">{focus.label}</p>
                      <p className="mt-1 text-sm text-muted-foreground">{focus.description}</p>
                    </button>
                  ))}
                </div>
              </CardContent>
            </Card>
          ) : null}

          <Card className="border-white/10 bg-card/80">
            <CardContent className="p-5">
              <h3 className="flex items-center gap-2 text-lg font-semibold">
                <Clock className="h-5 w-5 text-primary" />
                Time budget
              </h3>
              <div className="mt-4 flex flex-wrap gap-2">
                {TIME_OPTIONS.map((time) => (
                  <Button
                    key={time}
                    variant={timeBudget === time ? "default" : "outline"}
                    size="sm"
                    onClick={() => setTimeBudget(time)}
                  >
                    {formatReadingTime(time)}
                  </Button>
                ))}
              </div>
            </CardContent>
          </Card>

          <Card className="border-white/10 bg-card/80">
            <CardContent className="p-5">
              <h3 className="text-lg font-semibold">Reader goal</h3>
              <div className="mt-4 flex flex-wrap gap-2">
                {READER_GOALS.map((goal) => (
                  <Button
                    key={goal}
                    variant={readerGoal === goal ? "default" : "outline"}
                    size="sm"
                    onClick={() => setReaderGoal(goal)}
                  >
                    {goal}
                  </Button>
                ))}
              </div>
            </CardContent>
          </Card>

          <Card className="border-white/10 bg-card/80">
            <CardContent className="p-5">
              <h3 className="text-lg font-semibold">Experience mode</h3>
              <div className="mt-4 space-y-2">
                {EXPERIENCE_MODES.map((mode) => (
                  <button
                    key={mode.id}
                    type="button"
                    onClick={() => setExperienceMode(mode.id as "audio" | "text")}
                    className={cn(
                      "w-full rounded-2xl border px-4 py-3 text-left transition-colors",
                      experienceMode === mode.id
                        ? "border-primary/50 bg-primary/10"
                        : "border-white/10 bg-black/10 hover:border-primary/30"
                    )}
                  >
                    <p className="font-medium">{mode.label}</p>
                    <p className="mt-1 text-sm text-muted-foreground">
                      {mode.description}
                    </p>
                  </button>
                ))}
              </div>
            </CardContent>
          </Card>

          <Card className="border-white/10 bg-gradient-to-br from-primary/10 to-transparent">
            <CardContent className="p-5">
              <p className="text-sm font-medium text-primary">Tonight&apos;s mix</p>
              <div className="mt-3 flex flex-wrap gap-2">
                <Badge variant="default">{selectedStyle.replace("_", " ")}</Badge>
                {selectedStyle === "sexy" ? (
                  <Badge variant="secondary">
                    {DESIRE_LENSES.find((lens) => lens.id === desireLens)?.label || "Sexy lens"}
                  </Badge>
                ) : null}
                {selectedStyle === "sexy" ? (
                  <Badge variant="secondary">
                    {ADULT_INTENSITIES.find((intensity) => intensity.id === adultIntensity)?.label ||
                      "Adult"}
                  </Badge>
                ) : null}
                {selectedStyle === "sexy" ? (
                  <Badge variant="secondary">
                    {EROTIC_FOCUSES.find((focus) => focus.id === eroticFocus)?.label || "Focus"}
                  </Badge>
                ) : null}
                <Badge variant="secondary">{readerGoal}</Badge>
                <Badge variant="secondary">{voiceProfile}</Badge>
                <Badge variant="secondary">{experienceMode}</Badge>
              </div>
              <p className="mt-4 text-sm text-muted-foreground">
                The discussion stays grounded in citations, but the room can feel
                rigorous, playful, sensual, or calm depending on the tone you pick.
              </p>
            </CardContent>
          </Card>
        </div>
      </div>

      <div className="flex items-center justify-between border-t border-white/10 pt-4">
        <p className="text-sm text-muted-foreground">
          Local audiobook pairing is supported. OAuth-based OpenAI/Claude API access is
          not wired here because those providers still authenticate this stack with API
          credentials rather than end-user OAuth.
        </p>
        <Button
          size="lg"
          variant="gradient"
          onClick={startSession}
          disabled={starting || loading || (selectedStyle === "sexy" && !adultConfirmed)}
          className="gap-2"
        >
          {starting ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              Opening room...
            </>
          ) : (
            <>
              <Play className="h-4 w-4" />
              {selectedStyle === "sexy" ? "Open after-dark room" : "Start reading session"}
            </>
          )}
        </Button>
      </div>
    </div>
  );
}
