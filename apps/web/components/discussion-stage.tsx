"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowLeft,
  BookOpen,
  Eye,
  Flame,
  Headphones,
  LibraryBig,
  Loader2,
  MessageCircle,
  PanelRightOpen,
  Quote,
  Send,
  Sparkles,
  StopCircle,
  Timer,
  User,
  Volume2,
  VolumeX,
  X,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { VoiceInput } from "@/components/voice-input";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { API_BASE, cn } from "@/lib/utils";

interface CitationData {
  chunk_id: string;
  text: string;
  char_start?: number | null;
  char_end?: number | null;
  verified?: boolean;
  match_type?: "exact" | "normalized" | "fuzzy" | null;
}

interface Message {
  id: string;
  role: string;
  content: string;
  citations: CitationData[] | null;
  created_at: string;
}

interface Section {
  id: string;
  title: string | null;
  section_type: string;
  order_index: number;
  reading_time_min: number | null;
}

interface SessionPreferences {
  discussion_style?: string | null;
  vibes?: string[];
  voice_profile?: string | null;
  reader_goal?: string | null;
  experience_mode?: "audio" | "text";
  desire_lens?: string | null;
  adult_intensity?: string | null;
  erotic_focus?: string | null;
}

interface SessionData {
  session_id: string;
  book_id: string;
  mode: string;
  current_phase: string;
  sections: Section[];
  is_active: boolean;
  preferences?: SessionPreferences | null;
}

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
  title: string;
  author: string | null;
  sections: ExploreSection[];
  active_section: ActiveSection | null;
  audiobook_matches: AudiobookMatch[];
  has_local_audiobook: boolean;
}

interface DiscussionStageProps {
  sessionId: string;
  onBack: () => void;
}

type SidebarView = "club" | "reader" | "audio";
type ExperienceMode = "audio" | "text";
type AgentRole =
  | "facilitator"
  | "close_reader"
  | "skeptic"
  | "after_dark_guide"
  | "user";

const agentConfig: Record<
  AgentRole,
  {
    name: string;
    subtitle: string;
    icon: React.ElementType;
    color: string;
    bgColor: string;
    borderColor: string;
  }
> = {
  user: {
    name: "You",
    subtitle: "",
    icon: User,
    color: "text-blue-400",
    bgColor: "bg-blue-500/10",
    borderColor: "border-blue-500/30",
  },
  facilitator: {
    name: "Sam",
    subtitle: "guide",
    icon: Sparkles,
    color: "text-amber-400",
    bgColor: "bg-amber-500/10",
    borderColor: "border-amber-500/30",
  },
  close_reader: {
    name: "Ellis",
    subtitle: "close reader",
    icon: Eye,
    color: "text-teal-400",
    bgColor: "bg-teal-500/10",
    borderColor: "border-teal-500/30",
  },
  skeptic: {
    name: "Kit",
    subtitle: "skeptic",
    icon: Flame,
    color: "text-rose-400",
    bgColor: "bg-rose-500/10",
    borderColor: "border-rose-500/30",
  },
  after_dark_guide: {
    name: "After dark",
    subtitle: "erotic lens",
    icon: Sparkles,
    color: "text-fuchsia-300",
    bgColor: "bg-fuchsia-500/10",
    borderColor: "border-fuchsia-500/30",
  },
};

const eroticFocusNotes: Record<string, string> = {
  longing: "Look for almost-touch, delayed confession, and the ache of what is wanted but not yet allowed.",
  glamour: "Look for beauty rituals, clothes, entrances, mirrors, and scenes where presentation becomes seduction.",
  power: "Look for who controls the pace, who yields, and where desire is negotiated instead of simply declared.",
  tenderness: "Look for caretaking, softness, reassurance, and the warmth that makes erotic tension feel intimate.",
  transgression: "Look for secrecy, risk, taboo, and every moment where crossing the line sharpens the charge.",
};

const afterDarkPersonas: Record<string, { name: string; subtitle: string }> = {
  woman: { name: "Sable", subtitle: "after-dark guide" },
  gay_man: { name: "Lucian", subtitle: "after-dark guide" },
  trans_woman: { name: "Vesper", subtitle: "after-dark guide" },
};

const agentVoiceMap: Record<string, string> = {
  facilitator: "nova",
  close_reader: "shimmer",
  skeptic: "echo",
  after_dark_guide: "fable",
};

function formatPreferenceLabel(value: string | null | undefined) {
  return value ? value.replace(/_/g, " ") : "";
}

function getAgentConfig(role: string, preferences?: SessionPreferences | null) {
  if (role === "after_dark_guide") {
    const lens = preferences?.desire_lens || "";
    const persona = afterDarkPersonas[lens];
    return {
      ...agentConfig.after_dark_guide,
      name: persona?.name || agentConfig.after_dark_guide.name,
      subtitle: persona?.subtitle || agentConfig.after_dark_guide.subtitle,
    };
  }

  return (
    agentConfig[role as AgentRole] || {
      name: role,
      subtitle: "",
      icon: MessageCircle,
      color: "text-muted-foreground",
      bgColor: "bg-muted",
      borderColor: "border-border",
    }
  );
}

function buildRoomInvitation(
  session: SessionData | null,
  activeSectionTitle: string | null
) {
  if (!session) {
    return "A live reading room that can move from delight to argument without losing the page.";
  }

  const mode = formatPreferenceLabel(session.mode);
  const style = formatPreferenceLabel(session.preferences?.discussion_style) || "thoughtful";
  const sectionLabel = activeSectionTitle ? ` around ${activeSectionTitle}` : "";

  if (session.preferences?.discussion_style === "sexy") {
    const persona =
      afterDarkPersonas[session.preferences?.desire_lens || ""]?.name || "the after-dark guide";
    const focus = formatPreferenceLabel(session.preferences?.erotic_focus) || "desire";
    const intensity = formatPreferenceLabel(session.preferences?.adult_intensity) || "frank";
    return `${persona} joins Sam, Ellis, and Kit for a ${intensity} after-dark ${mode} that stays citation-grounded${sectionLabel}. Expect real critical pressure, real appetite, and a close read of where ${focus} becomes impossible to ignore.`;
  }

  return `This ${style} ${mode} keeps the room lively${sectionLabel}: Sam moves the conversation, Ellis slows down for craft, and Kit makes sure every strong claim actually earns its place on the page.`;
}

function buildDiscussionSparkDeck(
  session: SessionData | null,
  activeSectionTitle: string | null
) {
  const sectionNoun = activeSectionTitle || "this section";

  if (session?.preferences?.discussion_style === "sexy") {
    return [
      `Where is the erotic voltage actually coming from in ${sectionNoun}: gaze, delay, clothes, power, or something else?`,
      `Give me the hottest reading of ${sectionNoun}, then make the skeptic pressure-test it with evidence.`,
      `What makes ${sectionNoun} feel dangerous, tender, or impossible to skim?`,
      `Have the after-dark guide trace how desire and self-presentation braid together in ${sectionNoun}.`,
    ];
  }

  return [
    `What is the one detail in ${sectionNoun} that a first-time reader is most likely to miss?`,
    `Give me one close-reading insight, one skeptical challenge, and one question worth carrying forward.`,
    `What is ${sectionNoun} trying to make me feel before it tells me what to think?`,
    `Push the room past summary. What on the page is doing the real work here?`,
  ];
}

function VoiceWaves({ active }: { active: boolean }) {
  return (
    <div className="flex h-6 items-center justify-center gap-1">
      {[0, 1, 2, 3, 4].map((index) => (
        <div
          key={index}
          className={cn(
            "w-1 rounded-full bg-primary transition-all duration-200",
            active ? "voice-wave-bar" : "h-1"
          )}
          style={{ height: active ? "100%" : "4px" }}
        />
      ))}
    </div>
  );
}

function citationLabel(citation: CitationData) {
  if (citation.verified === false) {
    return "Unverified";
  }
  if (citation.match_type === "exact") {
    return "Exact";
  }
  if (citation.match_type === "normalized") {
    return "Normalized";
  }
  if (citation.match_type === "fuzzy") {
    return "Fuzzy";
  }
  return "Unchecked";
}

function extractSpeakableSegments(buffer: string) {
  const segments: string[] = [];
  let remaining = buffer;
  const sentencePattern = /(.+?[.!?](?:["')\]]+)?)(?:\s+|$)/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = sentencePattern.exec(buffer)) !== null) {
    const segment = match[1]?.trim();
    if (segment) {
      segments.push(segment);
    }
    lastIndex = sentencePattern.lastIndex;
  }

  remaining = buffer.slice(lastIndex);
  if (remaining.length > 220) {
    const pauseIndex = Math.max(remaining.lastIndexOf(", "), remaining.lastIndexOf("; "));
    if (pauseIndex > 80) {
      const chunk = remaining.slice(0, pauseIndex + 1).trim();
      if (chunk) {
        segments.push(chunk);
      }
      remaining = remaining.slice(pauseIndex + 1).trimStart();
    }
  }

  return { segments, remaining };
}

async function playStreamingAudio(
  response: Response,
  audio: HTMLAudioElement,
  onUrl: (url: string | null) => void
) {
  const body = response.body;
  if (
    !body ||
    typeof window === "undefined" ||
    typeof MediaSource === "undefined" ||
    !MediaSource.isTypeSupported("audio/mpeg")
  ) {
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    onUrl(url);
    audio.src = url;
    await audio.play();
    await new Promise<void>((resolve) => {
      audio.onended = () => resolve();
      audio.onerror = () => resolve();
    });
    return;
  }

  const mediaSource = new MediaSource();
  const mediaUrl = URL.createObjectURL(mediaSource);
  onUrl(mediaUrl);
  audio.src = mediaUrl;

  await new Promise<void>((resolve, reject) => {
    mediaSource.addEventListener("sourceopen", () => resolve(), { once: true });
    mediaSource.addEventListener("error", () => reject(new Error("media source error")), {
      once: true,
    });
  });

  const sourceBuffer = mediaSource.addSourceBuffer("audio/mpeg");
  const reader = body.getReader();
  const queue: Uint8Array[] = [];
  let streamDone = false;

  const flushQueue = () => {
    if (sourceBuffer.updating || queue.length === 0) {
      return;
    }
    sourceBuffer.appendBuffer(queue.shift() as Uint8Array);
  };

  sourceBuffer.addEventListener("updateend", () => {
    flushQueue();
    if (streamDone && queue.length === 0 && !sourceBuffer.updating && mediaSource.readyState === "open") {
      try {
        mediaSource.endOfStream();
      } catch {
        // noop
      }
    }
  });

  await audio.play().catch(() => undefined);

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      streamDone = true;
      if (queue.length === 0 && !sourceBuffer.updating && mediaSource.readyState === "open") {
        try {
          mediaSource.endOfStream();
        } catch {
          // noop
        }
      }
      break;
    }
    if (value) {
      queue.push(value);
      flushQueue();
    }
  }

  await new Promise<void>((resolve) => {
    audio.onended = () => resolve();
    audio.onerror = () => resolve();
  });
}

export function DiscussionStage({ sessionId, onBack }: DiscussionStageProps) {
  const [session, setSession] = useState<SessionData | null>(null);
  const [bookTitle, setBookTitle] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [activeAgent, setActiveAgent] = useState<string | null>(null);
  const [playingAudio, setPlayingAudio] = useState(false);
  const [speakingAgent, setSpeakingAgent] = useState<string | null>(null);
  const [isListening, setIsListening] = useState(false);
  const [sessionTime, setSessionTime] = useState(0);
  const [selectedCitation, setSelectedCitation] = useState<CitationData | null>(null);
  const [sidebarView, setSidebarView] = useState<SidebarView>("club");
  const [experienceMode, setExperienceMode] = useState<ExperienceMode>("text");
  const [readerSectionId, setReaderSectionId] = useState<string | null>(null);
  const [explore, setExplore] = useState<ExplorePayload | null>(null);
  const [exploreLoading, setExploreLoading] = useState(false);
  const [mobileSidebar, setMobileSidebar] = useState(false);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const startedRef = useRef(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const audioObjectUrlRef = useRef<string | null>(null);
  const speechQueueRef = useRef<Array<{ text: string; role: string; voice: string }>>([]);
  const speechRunningRef = useRef(false);
  const speechBuffersRef = useRef<Record<string, string>>({});
  const abortRef = useRef<AbortController | null>(null);

  const activeSectionTitle =
    explore?.active_section?.title || session?.sections?.[0]?.title || null;
  const roomInvitation = useMemo(
    () => buildRoomInvitation(session, activeSectionTitle),
    [activeSectionTitle, session]
  );
  const sparkDeck = useMemo(
    () => buildDiscussionSparkDeck(session, activeSectionTitle),
    [activeSectionTitle, session]
  );
  const visibleRoles = useMemo(
    () =>
      session?.preferences?.discussion_style === "sexy"
        ? (["facilitator", "close_reader", "after_dark_guide", "skeptic"] as const)
        : (["facilitator", "close_reader", "skeptic"] as const),
    [session?.preferences?.discussion_style]
  );

  useEffect(() => {
    if (!loading && session?.is_active) {
      const interval = setInterval(() => setSessionTime((value) => value + 1), 1000);
      return () => clearInterval(interval);
    }
  }, [loading, session?.is_active]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const cleanupAudioUrl = useCallback(() => {
    if (audioObjectUrlRef.current) {
      URL.revokeObjectURL(audioObjectUrlRef.current);
      audioObjectUrlRef.current = null;
    }
  }, []);

  const stopAudio = useCallback(() => {
    abortRef.current?.abort();
    speechQueueRef.current = [];
    speechRunningRef.current = false;
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.src = "";
      audioRef.current = null;
    }
    cleanupAudioUrl();
    setPlayingAudio(false);
    setSpeakingAgent(null);
  }, [cleanupAudioUrl]);

  const drainSpeechQueue = useCallback(async () => {
    if (speechRunningRef.current) {
      return;
    }
    speechRunningRef.current = true;

    while (speechQueueRef.current.length > 0) {
      const next = speechQueueRef.current.shift();
      if (!next) {
        continue;
      }

      const controller = new AbortController();
      abortRef.current = controller;
      setPlayingAudio(true);
      setSpeakingAgent(next.role);

      try {
        const response = await fetch(`${API_BASE}/v1/tts/stream`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text: next.text, voice: next.voice }),
          signal: controller.signal,
        });

        if (!response.ok) {
          throw new Error(`TTS request failed: ${response.status}`);
        }

        const audio = new Audio();
        audioRef.current = audio;
        cleanupAudioUrl();
        await playStreamingAudio(response, audio, (url) => {
          audioObjectUrlRef.current = url;
        });
      } catch (error) {
        if (!(error instanceof DOMException && error.name === "AbortError")) {
          console.error("Streaming TTS failed:", error);
        }
      } finally {
        abortRef.current = null;
        if (audioRef.current) {
          audioRef.current.pause();
          audioRef.current = null;
        }
        cleanupAudioUrl();
        setPlayingAudio(false);
        setSpeakingAgent(null);
      }
    }

    speechRunningRef.current = false;
  }, [cleanupAudioUrl]);

  const enqueueSpeech = useCallback(
    (text: string, role: string, voice: string = "nova") => {
      if (!text.trim()) {
        return;
      }
      speechQueueRef.current.push({ text, role, voice });
      drainSpeechQueue();
    },
    [drainSpeechQueue]
  );

  const loadSession = useCallback(async () => {
    try {
      const [sessionRes, messagesRes] = await Promise.all([
        fetch(`${API_BASE}/v1/sessions/${sessionId}`),
        fetch(`${API_BASE}/v1/sessions/${sessionId}/messages`),
      ]);
      const sessionData = await sessionRes.json();
      const messagesData = await messagesRes.json();
      setSession(sessionData);
      setExperienceMode(sessionData.preferences?.experience_mode || "text");
      setMessages(messagesData.messages || []);
      setReaderSectionId((prev) => prev || sessionData.sections?.[0]?.id || null);

      if (sessionData.book_id) {
        try {
          const bookRes = await fetch(`${API_BASE}/v1/books/${sessionData.book_id}`);
          const bookData = await bookRes.json();
          setBookTitle(bookData.title || "");
        } catch {
          // noop
        }
      }

      if ((messagesData.messages || []).length === 0 && !startedRef.current) {
        startedRef.current = true;
        setActiveAgent("facilitator");
        const res = await fetch(`${API_BASE}/v1/sessions/${sessionId}/start-discussion`, {
          method: "POST",
        });
        const data = await res.json();
        if (data.messages) {
          setMessages(
            data.messages.map((message: Message, index: number) => ({
              ...message,
              id: message.id || `start-${Date.now()}-${index}`,
              created_at: message.created_at || new Date().toISOString(),
            }))
          );
          if (sessionData.preferences?.experience_mode === "audio" && data.messages[0]?.content) {
            enqueueSpeech(data.messages[0].content, data.messages[0].role || "facilitator");
          }
        }
        setActiveAgent(null);
      }
    } catch (error) {
      console.error("Failed to load session:", error);
    } finally {
      setLoading(false);
    }
  }, [enqueueSpeech, sessionId]);

  useEffect(() => {
    loadSession();
  }, [loadSession]);

  useEffect(() => {
    async function loadExplore() {
      if (!session?.book_id || !readerSectionId) {
        return;
      }
      setExploreLoading(true);
      try {
        const params = new URLSearchParams({ section_id: readerSectionId });
        const res = await fetch(`${API_BASE}/v1/books/${session.book_id}/explore?${params}`);
        const data = await res.json();
        setExplore(data);
      } catch (error) {
        console.error("Failed to load reader explorer:", error);
      } finally {
        setExploreLoading(false);
      }
    }

    loadExplore();
  }, [readerSectionId, session?.book_id]);

  useEffect(() => () => stopAudio(), [stopAudio]);

  function formatTime(seconds: number) {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, "0")}`;
  }

  function handleVoiceTranscript(text: string) {
    setInput((prev) => (prev ? `${prev} ${text}` : text));
    inputRef.current?.focus();
  }

  async function updateExperienceMode(nextMode: ExperienceMode) {
    setExperienceMode(nextMode);
    if (nextMode === "text") {
      stopAudio();
    }
    try {
      await fetch(`${API_BASE}/v1/sessions/${sessionId}/preferences`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ experience_mode: nextMode }),
      });
      setSession((prev) =>
        prev
          ? {
              ...prev,
              preferences: { ...(prev.preferences || {}), experience_mode: nextMode },
            }
          : prev
      );
    } catch (error) {
      console.error("Failed to update session preferences:", error);
    }
  }

  async function submitMessage(rawMessage: string) {
    const messageText = rawMessage.trim();
    if (!messageText || sending) {
      return;
    }

    // Interrupt: stop any playing audio when the user sends a new message
    if (playingAudio) {
      stopAudio();
    }

    const userMessage = messageText;
    setInput("");
    setSending(true);
    setMessages((prev) => [
      ...prev,
      {
        id: `user-${Date.now()}`,
        role: "user",
        content: userMessage,
        citations: null,
        created_at: new Date().toISOString(),
      },
    ]);

    try {
      const res = await fetch(`${API_BASE}/v1/sessions/${sessionId}/message/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          content: userMessage,
          include_close_reader: true,
        }),
      });

      if (!res.ok || !res.body) {
        throw new Error(`Streaming failed: ${res.status}`);
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      const messageIds: Record<string, string> = {};
      const agentVoices: Record<string, string> = {};
      let useSentenceEvents = false;
      let buffer = "";
      let lastSeenSequence = -1;

      while (true) {
        const { done, value } = await reader.read();
        if (done) {
          break;
        }

        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split("\n\n");
        buffer = parts.pop() ?? "";

        for (const part of parts) {
          const lines = part.split("\n").map((line) => line.trim());
          const dataLine = lines.find((line) => line.startsWith("data: "));
          if (!dataLine) {
            continue;
          }

          let event: any;
          try {
            event = JSON.parse(dataLine.slice(6));
          } catch {
            continue;
          }

          const sequence = typeof event.sequence === "number" ? event.sequence : -1;
          if (sequence > 0 && sequence <= lastSeenSequence) {
            continue;
          }
          if (sequence > 0) {
            lastSeenSequence = sequence;
          }

          if (event.type === "message_start") {
            const role = String(event.role || "assistant");
            const voice = String(event.voice || "nova");
            setActiveAgent(role);
            speechBuffersRef.current[role] = "";
            // Store voice per agent for fallback client-side TTS
            agentVoices[role] = voice;
            const id = `stream-${Date.now()}-${role}`;
            messageIds[role] = id;
            setMessages((prev) => [
              ...prev,
              {
                id,
                role,
                content: "",
                citations: null,
                created_at: new Date().toISOString(),
              },
            ]);
          } else if (event.type === "message_delta") {
            const role = String(event.role || "assistant");
            const delta = String(event.delta || "");
            const id = messageIds[role];
            if (!id) {
              continue;
            }
            setMessages((prev) =>
              prev.map((message) =>
                message.id === id
                  ? { ...message, content: message.content + delta }
                  : message
              )
            );
            // NOTE: Audio is now driven by server-side sentence_ready events.
            // Client-side splitting kept as fallback for older backends.
            if (experienceMode === "audio" && !useSentenceEvents && delta) {
              const nextBuffer = `${speechBuffersRef.current[role] || ""}${delta}`;
              const { segments, remaining } = extractSpeakableSegments(nextBuffer);
              speechBuffersRef.current[role] = remaining;
              for (const segment of segments) {
                enqueueSpeech(segment, role, agentVoices[role] || "nova");
              }
            }
          } else if (event.type === "sentence_ready") {
            // Server-side sentence splitting for TTS pipelining.
            // Each event contains a complete sentence ready for TTS.
            useSentenceEvents = true;
            if (experienceMode === "audio") {
              const role = String(event.role || "assistant");
              const voice = String(event.voice || agentVoices[role] || "nova");
              const sentence = String(event.sentence || "");
              if (sentence.trim()) {
                enqueueSpeech(sentence, role, voice);
              }
            }
          } else if (event.type === "message_end") {
            const role = String(event.role || "assistant");
            const id = messageIds[role];
            const content = String(event.content || "");
            const citations = Array.isArray(event.citations) ? event.citations : null;
            if (id) {
              setMessages((prev) =>
                prev.map((message) =>
                  message.id === id
                    ? { ...message, content, citations }
                    : message
                )
              );
            }
            // Only use client-side fallback if no sentence_ready events were received
            if (experienceMode === "audio" && !useSentenceEvents) {
              const tail = (speechBuffersRef.current[role] || content).trim();
              if (tail) {
                enqueueSpeech(tail, role, agentVoices[role] || "nova");
              }
            }
            delete speechBuffersRef.current[role];
          } else if (event.type === "agent_error") {
            const role = String(event.role || "assistant");
            const id = messageIds[role];
            if (id) {
              setMessages((prev) =>
                prev.map((message) =>
                  message.id === id
                    ? {
                        ...message,
                        content: `[Agent error: ${event.error}]`,
                      }
                    : message
                )
              );
            }
          } else if (event.type === "done") {
            setActiveAgent(null);
          }
        }
      }
    } catch (error) {
      console.error("Failed to send message:", error);
    } finally {
      setSending(false);
      setActiveAgent(null);
    }
  }

  async function sendMessage() {
    await submitMessage(input);
  }

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="text-center">
          <Loader2 className="mx-auto mb-4 h-8 w-8 animate-spin text-primary" />
          <p className="text-muted-foreground">Loading discussion...</p>
        </div>
      </div>
    );
  }

  const isAfterDark = session?.preferences?.discussion_style === "sexy";

  return (
    <div className={cn("flex h-full min-w-0", isAfterDark && "after-dark")}>
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="glass border-b border-border/50 px-4 py-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <Button variant="ghost" size="icon-sm" onClick={onBack}>
                <ArrowLeft className="h-4 w-4" />
              </Button>
              <div>
                <h2 className="text-sm font-semibold">{bookTitle || "Reading session"}</h2>
                <div className="mt-1 flex flex-wrap items-center gap-2">
                  <Badge variant="secondary">{session?.mode.replace("_", " ")}</Badge>
                  {session?.preferences?.discussion_style ? (
                    <Badge variant="default">
                      {session.preferences.discussion_style.replace("_", " ")}
                    </Badge>
                  ) : null}
                  {session?.preferences?.reader_goal ? (
                    <Badge variant="outline">{session.preferences.reader_goal}</Badge>
                  ) : null}
                  {session?.preferences?.desire_lens ? (
                    <Badge variant="outline">
                      {session.preferences.desire_lens.replace("_", " ")}
                    </Badge>
                  ) : null}
                  {session?.preferences?.adult_intensity ? (
                    <Badge variant="outline">
                      {session.preferences.adult_intensity.replace("_", " ")}
                    </Badge>
                  ) : null}
                  {session?.preferences?.erotic_focus ? (
                    <Badge variant="outline">
                      {session.preferences.erotic_focus.replace("_", " ")}
                    </Badge>
                  ) : null}
                </div>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <div className="flex items-center gap-1 rounded-lg bg-secondary/50 px-2 py-1 text-xs text-muted-foreground">
                <Timer className="h-3 w-3" />
                <span className="font-mono">{formatTime(sessionTime)}</span>
              </div>

              <div className="flex items-center rounded-xl border border-white/10 bg-black/10 p-1">
                <button
                  type="button"
                  onClick={() => updateExperienceMode("audio")}
                  className={cn(
                    "rounded-lg px-3 py-1.5 text-xs transition-colors",
                    experienceMode === "audio" && "bg-primary text-primary-foreground"
                  )}
                >
                  Conversational audio
                </button>
                <button
                  type="button"
                  onClick={() => updateExperienceMode("text")}
                  className={cn(
                    "rounded-lg px-3 py-1.5 text-xs transition-colors",
                    experienceMode === "text" && "bg-primary text-primary-foreground"
                  )}
                >
                  Text
                </button>
              </div>

              {playingAudio ? (
                <Button variant="ghost" size="icon-sm" onClick={stopAudio}>
                  <StopCircle className="h-4 w-4 text-destructive" />
                </Button>
              ) : (
                <Button
                  variant="ghost"
                  size="icon-sm"
                  onClick={() => setSidebarView("audio")}
                >
                  <Headphones className="h-4 w-4" />
                </Button>
              )}
            </div>
          </div>

          {experienceMode === "audio" ? (
            <div className="mt-2 flex items-center gap-2 text-xs text-primary">
              <VoiceWaves active={playingAudio || sending} />
              <span>
                {playingAudio && speakingAgent
                  ? `${getAgentConfig(speakingAgent, session?.preferences).name} is speaking...`
                  : playingAudio
                    ? "Speaking..."
                    : "Sentence-by-sentence audio — agents speak as they think."}
              </span>
            </div>
          ) : null}

          {session?.preferences?.discussion_style === "sexy" ? (
            <div className="mt-3 rounded-2xl border border-rose-500/20 bg-[radial-gradient(circle_at_top_left,rgba(244,63,94,0.16),transparent_35%),rgba(20,16,22,0.92)] px-4 py-3 text-sm text-rose-50/90">
              <p className="font-medium text-white">After-dark reading room</p>
              <p className="mt-1 leading-6 text-rose-50/80">
                This session is tuned for adult, erotic conversation through a{" "}
                {session.preferences.desire_lens?.replace("_", " ") || "sexy"} lens with a{" "}
                {session.preferences.adult_intensity?.replace("_", " ") || "frank"} tone.
                Stay with the charged details that make the page hard to skim.
              </p>
            </div>
          ) : null}

          <div className="mt-3 grid gap-3 lg:grid-cols-[1.15fr_0.85fr]">
            <div className="rounded-2xl border border-white/10 bg-white/[0.03] px-4 py-3">
              <p className="text-[11px] uppercase tracking-[0.28em] text-primary/80 font-label">
                Live salon
              </p>
              <p className="mt-2 text-sm leading-6 text-foreground/90">{roomInvitation}</p>
              <div className="mt-3 flex flex-wrap gap-2">
                <Badge variant="secondary">{visibleRoles.length} voices live</Badge>
                <Badge variant="secondary">
                  {session?.sections?.length || 0} section
                  {session?.sections?.length === 1 ? "" : "s"}
                </Badge>
                {activeSectionTitle ? <Badge variant="outline">{activeSectionTitle}</Badge> : null}
              </div>
            </div>

            <div className="rounded-2xl border border-white/10 bg-black/15 px-4 py-3">
              <div className="flex items-center justify-between gap-3">
                <p className="text-[11px] uppercase tracking-[0.28em] text-muted-foreground font-label">
                  Conversation sparks
                </p>
                <span className="text-[11px] text-muted-foreground">
                  Tap to send now
                </span>
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                {sparkDeck.map((prompt) => (
                  <button
                    key={prompt}
                    type="button"
                    disabled={sending}
                    onClick={() => void submitMessage(prompt)}
                    className="rounded-full border border-white/10 bg-white/[0.04] px-3 py-2 text-left text-xs leading-5 text-foreground/85 transition-colors hover:border-primary/40 hover:bg-primary/10 disabled:opacity-50"
                  >
                    {prompt}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto px-4 py-5">
          <div className="mx-auto max-w-4xl space-y-4">
            {messages.map((message) => {
              const config = getAgentConfig(message.role, session?.preferences);
              const isUser = message.role === "user";
              const Icon = config.icon;
              return (
                <div key={message.id} className={cn("flex gap-3", isUser && "flex-row-reverse")}>
                  <div
                    className={cn(
                      "flex h-9 w-9 shrink-0 items-center justify-center rounded-xl",
                      config.bgColor
                    )}
                  >
                    <Icon className={cn("h-4 w-4", config.color)} />
                  </div>

                  <div
                    className={cn(
                      "max-w-[84%] rounded-3xl px-4 py-3",
                      isUser
                        ? "rounded-tr-md bg-primary text-primary-foreground"
                        : `rounded-tl-md border ${config.borderColor} ${config.bgColor}`
                    )}
                  >
                    {!isUser ? (
                      <div className="mb-1.5 flex items-center gap-2">
                        <span className={cn("text-xs font-medium", config.color)}>
                          {config.name}
                        </span>
                        <span className="text-[10px] uppercase tracking-wide text-muted-foreground">
                          {config.subtitle}
                        </span>
                        <button
                          type="button"
                          onClick={() =>
                            enqueueSpeech(
                              message.content,
                              message.role,
                              agentVoiceMap[message.role] || "nova"
                            )
                          }
                          className="opacity-60 transition-opacity hover:opacity-100"
                        >
                          <Volume2 className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    ) : null}

                    {message.content ? (
                      <div className="prose prose-sm prose-invert max-w-none text-sm leading-relaxed prose-p:my-1.5">
                        <ReactMarkdown
                          remarkPlugins={[remarkGfm]}
                          components={{
                            a: ({ href, children }) => (
                              <a
                                href={href}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="underline decoration-primary/40 hover:decoration-primary"
                              >
                                {children}
                              </a>
                            ),
                          }}
                        >
                          {message.content}
                        </ReactMarkdown>
                      </div>
                    ) : (
                      <p className="text-sm italic opacity-60">Thinking...</p>
                    )}

                    {message.citations?.length ? (
                      <div className="mt-3 border-t border-current/10 pt-3">
                        <p className="mb-2 flex items-center gap-1 text-xs font-medium opacity-70">
                          <Quote className="h-3 w-3" />
                          Citations
                        </p>
                        <div className="space-y-1.5">
                          {message.citations.map((citation, index) => (
                            <button
                              key={`${message.id}-${index}`}
                              type="button"
                              onClick={() => {
                                setSelectedCitation(citation);
                                setSidebarView("club");
                              }}
                              className="flex w-full items-start gap-2 rounded-xl px-2 py-1 text-left text-xs transition-colors hover:bg-black/10"
                            >
                              <span
                                className={cn(
                                  "mt-1 inline-block h-2 w-2 shrink-0 rounded-full",
                                  citation.verified === false
                                    ? "bg-citation-unverified"
                                    : citation.match_type === "exact"
                                      ? "bg-citation-exact"
                                      : citation.match_type === "fuzzy"
                                        ? "bg-citation-fuzzy"
                                        : "bg-citation-normalized"
                                )}
                              />
                              <span className="line-clamp-2 italic font-serif">
                                &ldquo;{citation.text}&rdquo;{" "}
                                <span className="not-italic text-muted-foreground font-label text-[10px]">
                                  {citationLabel(citation)}
                                </span>
                              </span>
                            </button>
                          ))}
                        </div>
                      </div>
                    ) : null}
                  </div>
                </div>
              );
            })}

            {activeAgent ? (
              <div className="flex items-start gap-3">
                <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-primary/10">
                  <Loader2 className="h-4 w-4 animate-spin text-primary" />
                </div>
                <div className="rounded-3xl rounded-tl-md border border-white/10 bg-black/10 px-4 py-3 text-sm text-muted-foreground">
                  {getAgentConfig(activeAgent, session?.preferences).name} is composing a reply...
                </div>
              </div>
            ) : null}

            <div ref={messagesEndRef} />
          </div>
        </div>

        <div className="glass border-t border-border/50 p-4">
          <form
            onSubmit={(event) => {
              event.preventDefault();
              sendMessage();
            }}
            className="mx-auto flex max-w-4xl items-center gap-2"
          >
            <VoiceInput
              onTranscript={handleVoiceTranscript}
              onListeningChange={setIsListening}
              disabled={sending || !session?.is_active}
            />
            <Input
              ref={inputRef}
              value={input}
              onChange={(event) => setInput(event.target.value)}
              placeholder={
                experienceMode === "audio"
                  ? "Jump into the conversation..."
                  : "What do you think? What caught your eye?"
              }
              disabled={sending || !session?.is_active}
              className="flex-1"
            />
            <Button type="submit" disabled={sending || !input.trim()}>
              {sending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
            </Button>
            <Button
              variant="ghost"
              size="icon"
              onClick={() => setMobileSidebar(true)}
              className="lg:hidden shrink-0"
            >
              <PanelRightOpen className="h-4 w-4" />
            </Button>
          </form>
          {isListening ? (
            <div className="mt-2 flex items-center justify-center gap-2 text-xs text-red-400">
              <VoiceWaves active />
              <span>Listening...</span>
            </div>
          ) : (
            <p className="mt-2 text-center text-xs text-muted-foreground">
              Need a nudge? Fire one of the conversation sparks above and let the room answer in real time.
            </p>
          )}
        </div>
      </div>

      {/* Mobile sidebar overlay */}
      {mobileSidebar && (
        <div
          className="fixed inset-0 z-40 bg-black/60 lg:hidden"
          onClick={() => setMobileSidebar(false)}
        />
      )}

      <aside
        className={cn(
          "glass border-l border-border/50 flex-col",
          "lg:flex lg:w-[360px] lg:relative lg:z-auto",
          mobileSidebar
            ? "fixed inset-y-0 right-0 z-50 flex w-[340px] animate-slide-in-right"
            : "hidden"
        )}
      >
        <div className="border-b border-white/10 p-3">
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={() => setMobileSidebar(false)}
              className="lg:hidden shrink-0"
            >
              <X className="h-4 w-4" />
            </Button>
            <div className="grid flex-1 grid-cols-3 gap-2">
              <Button
                variant={sidebarView === "club" ? "default" : "outline"}
                size="sm"
                onClick={() => setSidebarView("club")}
              >
                Club
              </Button>
              <Button
                variant={sidebarView === "reader" ? "default" : "outline"}
                size="sm"
                onClick={() => setSidebarView("reader")}
              >
                Reader
              </Button>
              <Button
                variant={sidebarView === "audio" ? "default" : "outline"}
                size="sm"
                onClick={() => setSidebarView("audio")}
              >
                Audio
              </Button>
            </div>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-4">
          {sidebarView === "club" ? (
            <div className="space-y-5">
              <Card className="border-white/10 bg-black/10">
                <CardContent className="p-4">
                  <p className="text-sm font-medium text-white">Room pulse</p>
                  <p className="mt-2 text-sm leading-6 text-foreground/80">
                    {roomInvitation}
                  </p>
                  <div className="mt-4 space-y-2">
                    {sparkDeck.slice(0, 3).map((prompt) => (
                      <button
                        key={prompt}
                        type="button"
                        disabled={sending}
                        onClick={() => void submitMessage(prompt)}
                        className="w-full rounded-2xl border border-white/10 bg-white/[0.03] px-3 py-3 text-left text-xs leading-5 text-foreground/85 transition-colors hover:border-primary/40 hover:bg-primary/10 disabled:opacity-50"
                      >
                        {prompt}
                      </button>
                    ))}
                  </div>
                </CardContent>
              </Card>

              {session?.preferences?.discussion_style === "sexy" ? (
                <Card className="border-rose-500/20 bg-rose-500/5">
                  <CardContent className="p-4">
                    <p className="text-sm font-medium text-rose-100">What to notice</p>
                    <p className="mt-2 text-sm leading-6 text-rose-50/75">
                      {eroticFocusNotes[session.preferences.erotic_focus || "longing"]}
                    </p>
                  </CardContent>
                </Card>
              ) : null}

              <div>
                <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold">
                  <LibraryBig className="h-4 w-4 text-primary" />
                  Reading slice
                </h3>
                <div className="space-y-2">
                  {session?.sections.map((section) => (
                    <Card
                      key={section.id}
                      className="cursor-pointer border-white/10 bg-black/10"
                      onClick={() => {
                        setReaderSectionId(section.id);
                        setSidebarView("reader");
                      }}
                    >
                      <CardContent className="p-3">
                        <p className="text-sm font-medium">
                          {section.title || `Section ${section.order_index + 1}`}
                        </p>
                        <p className="mt-1 text-xs text-muted-foreground">
                          {section.section_type}
                          {section.reading_time_min ? ` · ${section.reading_time_min} min` : ""}
                        </p>
                      </CardContent>
                    </Card>
                  ))}
                </div>
              </div>

              {selectedCitation ? (
                <div>
                  <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold">
                    <Quote className="h-4 w-4 text-primary" />
                    Selected citation
                  </h3>
                  <Card className="border-white/10 bg-primary/5">
                    <CardContent className="p-4">
                      <p className="text-sm italic">&quot;{selectedCitation.text}&quot;</p>
                      <p className="mt-3 text-xs text-muted-foreground">
                        {selectedCitation.chunk_id.slice(0, 12)}...
                        {selectedCitation.char_start != null && selectedCitation.char_end != null
                          ? ` · chars ${selectedCitation.char_start}-${selectedCitation.char_end}`
                          : ""}
                      </p>
                    </CardContent>
                  </Card>
                </div>
              ) : null}

              <div>
                <h3 className="mb-3 text-sm font-semibold">Book club voices</h3>
                <div className="space-y-2">
                  {visibleRoles.map((role) => {
                    const config = getAgentConfig(role, session?.preferences);
                    const Icon = config.icon;
                    return (
                      <div
                        key={role}
                        className={cn(
                          "flex items-center gap-3 rounded-2xl border border-white/10 px-3 py-3",
                          activeAgent === role && config.bgColor
                        )}
                      >
                        <div
                          className={cn(
                            "flex h-8 w-8 items-center justify-center rounded-xl",
                            config.bgColor
                          )}
                        >
                          <Icon className={cn("h-4 w-4", config.color)} />
                        </div>
                        <div>
                          <p className="text-sm font-medium">{config.name}</p>
                          <p className="text-xs text-muted-foreground">{config.subtitle}</p>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          ) : null}

          {sidebarView === "reader" ? (
            <div className="space-y-4">
              <div>
                <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold">
                  <BookOpen className="h-4 w-4 text-primary" />
                  Open book
                </h3>
                <div className="space-y-2">
                  {explore?.sections.map((section) => (
                    <button
                      key={section.id}
                      type="button"
                      onClick={() => setReaderSectionId(section.id)}
                      className={cn(
                        "w-full rounded-2xl border px-3 py-3 text-left transition-colors",
                        readerSectionId === section.id
                          ? "border-primary/50 bg-primary/10"
                          : "border-white/10 bg-black/10 hover:border-primary/30"
                      )}
                    >
                      <p className="text-sm font-medium">
                        {section.title || `Section ${section.order_index + 1}`}
                      </p>
                      <p className="mt-1 text-xs text-muted-foreground">
                        {section.preview_text}
                      </p>
                    </button>
                  ))}
                </div>
              </div>

              <Card className="border-white/10 bg-black/10">
                <CardContent className="p-4">
                  {exploreLoading ? (
                    <div className="py-8 text-center text-sm text-muted-foreground">
                      <Loader2 className="mx-auto mb-3 h-5 w-5 animate-spin text-primary" />
                      Loading section text...
                    </div>
                  ) : (
                    <>
                      <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">
                        {explore?.active_section?.title || "Section preview"}
                      </p>
                      <p className="mt-3 whitespace-pre-wrap text-sm leading-7 text-foreground/90 font-serif">
                        {explore?.active_section?.text || "Pick a section to open the text here."}
                      </p>
                    </>
                  )}
                </CardContent>
              </Card>
            </div>
          ) : null}

          {sidebarView === "audio" ? (
            <div className="space-y-4">
              <Card className="border-white/10 bg-black/10">
                <CardContent className="p-4">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <p className="text-sm font-medium">Experience mode</p>
                      <p className="mt-1 text-xs text-muted-foreground">
                        Option A starts TTS while agent text is still streaming. Option B keeps it purely textual.
                      </p>
                    </div>
                    {experienceMode === "audio" ? (
                      <Volume2 className="h-4 w-4 text-primary" />
                    ) : (
                      <VolumeX className="h-4 w-4 text-muted-foreground" />
                    )}
                  </div>
                </CardContent>
              </Card>

              <div>
                <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold">
                  <Headphones className="h-4 w-4 text-primary" />
                  Local audiobook matches
                </h3>
                <div className="space-y-2">
                  {explore?.audiobook_matches?.length ? (
                    explore.audiobook_matches.map((match) => (
                      <Card key={match.path} className="border-white/10 bg-black/10">
                        <CardContent className="p-3">
                          <p className="text-sm font-medium">{match.title_guess}</p>
                          <p className="mt-1 text-xs text-muted-foreground">
                            {match.match_reason || "Likely local match"}
                          </p>
                          <p className="mt-2 text-[11px] text-muted-foreground">
                            {match.parent_folder || match.filename}
                          </p>
                        </CardContent>
                      </Card>
                    ))
                  ) : (
                    <Card className="border-dashed border-white/10 bg-black/10">
                      <CardContent className="p-4 text-sm text-muted-foreground">
                        No local audiobook surfaced for this title yet. The app will still
                        run in conversational audio mode using live TTS.
                      </CardContent>
                    </Card>
                  )}
                </div>
              </div>
            </div>
          ) : null}
        </div>
      </aside>
    </div>
  );
}
