"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import {
  ArrowLeft,
  Send,
  Volume2,
  VolumeX,
  Quote,
  User,
  BookOpen,
  Eye,
  Sparkles,
  StopCircle,
  MessageCircle,
  Loader2,
  ChevronRight,
  Flame,
  Focus,
  Timer,
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { VoiceInput } from "@/components/voice-input";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { cn, API_BASE } from "@/lib/utils";

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
  title: string;
  section_type: string;
  reading_time_min: number | null;
}

interface SessionData {
  session_id: string;
  book_id: string;
  mode: string;
  current_phase: string;
  sections: Section[];
  is_active: boolean;
}

interface DiscussionStageProps {
  sessionId: string;
  onBack: () => void;
}

type AgentRole = "facilitator" | "close_reader" | "skeptic" | "user";

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
    subtitle: "your guide",
    icon: Sparkles,
    color: "text-amber-400",
    bgColor: "bg-amber-500/10",
    borderColor: "border-amber-500/30",
  },
  close_reader: {
    name: "Ellis",
    subtitle: "the reader",
    icon: Eye,
    color: "text-teal-400",
    bgColor: "bg-teal-500/10",
    borderColor: "border-teal-500/30",
  },
  skeptic: {
    name: "Kit",
    subtitle: "devil's advocate",
    icon: Flame,
    color: "text-rose-400",
    bgColor: "bg-rose-500/10",
    borderColor: "border-rose-500/30",
  },
};

function getAgentConfig(role: string) {
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

// Voice wave animation component
function VoiceWaves({ active }: { active: boolean }) {
  return (
    <div className="flex items-center justify-center gap-1 h-6">
      {[...Array(5)].map((_, i) => (
        <div
          key={i}
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

// Typing indicator component
function TypingIndicator({ agent }: { agent: string }) {
  const config = getAgentConfig(agent);
  return (
    <div className="flex items-start gap-3 message-enter-agent">
      <div
        className={cn(
          "w-9 h-9 rounded-xl flex items-center justify-center shrink-0",
          config.bgColor
        )}
      >
        <config.icon className={cn("w-4 h-4", config.color)} />
      </div>
      <div className={cn("rounded-2xl rounded-tl-md px-4 py-3", config.bgColor)}>
        <div className="flex items-center gap-1.5">
          <span className="typing-dot w-2 h-2 rounded-full bg-current opacity-60" />
          <span className="typing-dot w-2 h-2 rounded-full bg-current opacity-60" />
          <span className="typing-dot w-2 h-2 rounded-full bg-current opacity-60" />
        </div>
      </div>
    </div>
  );
}

// Citation quality indicator
function citationQualityInfo(cite: CitationData): {
  color: string;
  label: string;
  description: string;
} {
  // If verified field is not present at all, treat as legacy (no verification data)
  if (cite.verified === undefined || cite.verified === null) {
    return {
      color: "bg-zinc-400",
      label: "Not checked",
      description: "This citation has no verification data",
    };
  }
  if (cite.verified === false) {
    return {
      color: "bg-red-400/80",
      label: "Unverified",
      description: "This quote could not be verified against the source text",
    };
  }
  switch (cite.match_type) {
    case "exact":
      return {
        color: "bg-emerald-400",
        label: "Exact match",
        description: "This quote exactly matches the source text",
      };
    case "normalized":
      return {
        color: "bg-emerald-400/70",
        label: "Normalized match",
        description: "This quote matches the source after whitespace/unicode normalization",
      };
    case "fuzzy":
      return {
        color: "bg-amber-400",
        label: "Fuzzy match",
        description: "This quote partially matches the source text (word overlap)",
      };
    default:
      return {
        color: "bg-zinc-400",
        label: "Unknown",
        description: "Verification status is unknown",
      };
  }
}

function CitationQualityDot({ citation }: { citation: CitationData }) {
  const quality = citationQualityInfo(citation);
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span
          className={cn(
            "inline-block w-1.5 h-1.5 rounded-full shrink-0 mt-1.5",
            quality.color
          )}
        />
      </TooltipTrigger>
      <TooltipContent side="top">
        <p className="font-medium">{quality.label}</p>
        <p className="text-muted-foreground text-[10px] max-w-[200px]">
          {quality.description}
        </p>
      </TooltipContent>
    </Tooltip>
  );
}

export function DiscussionStage({ sessionId, onBack }: DiscussionStageProps) {
  const [session, setSession] = useState<SessionData | null>(null);
  const [bookTitle, setBookTitle] = useState<string>("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [activeAgent, setActiveAgent] = useState<string | null>(null);
  const [voiceEnabled, setVoiceEnabled] = useState(false);
  const [playingAudio, setPlayingAudio] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [selectedCitation, setSelectedCitation] = useState<CitationData | null>(null);
  const [showSidebar, setShowSidebar] = useState(true);
  const [focusMode, setFocusMode] = useState(false);
  const [sessionTime, setSessionTime] = useState(0); // seconds
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const startedRef = useRef(false);

  // Session timer
  useEffect(() => {
    if (!loading && session?.is_active) {
      const interval = setInterval(() => {
        setSessionTime((prev) => prev + 1);
      }, 1000);
      return () => clearInterval(interval);
    }
  }, [loading, session?.is_active]);

  // Format session time
  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, "0")}`;
  };

  // Scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Load session data
  const loadSession = useCallback(async () => {
    try {
      const [sessionRes, messagesRes] = await Promise.all([
        fetch(`${API_BASE}/v1/sessions/${sessionId}`),
        fetch(`${API_BASE}/v1/sessions/${sessionId}/messages`),
      ]);
      const sessionData = await sessionRes.json();
      const messagesData = await messagesRes.json();
      setSession(sessionData);
      setMessages(messagesData.messages || []);

      // Fetch book title
      if (sessionData.book_id) {
        try {
          const bookRes = await fetch(`${API_BASE}/v1/books/${sessionData.book_id}`);
          const bookData = await bookRes.json();
          setBookTitle(bookData.title || "");
        } catch {
          // Non-critical — continue without title
        }
      }

      // Start discussion if no messages yet (guard against React strict mode double-fire)
      if ((messagesData.messages || []).length === 0 && !startedRef.current) {
        startedRef.current = true;
        await startDiscussion();
      }
    } catch (e) {
      console.error("Failed to load session:", e);
    } finally {
      setLoading(false);
    }
  }, [sessionId]);

  useEffect(() => {
    loadSession();
  }, [loadSession]);

  async function startDiscussion() {
    setActiveAgent("facilitator");
    try {
      const res = await fetch(
        `${API_BASE}/v1/sessions/${sessionId}/start-discussion`,
        { method: "POST" }
      );
      const data = await res.json();
      if (data.messages) {
        setMessages((prev) => [
          ...prev,
          ...data.messages.map((m: any, i: number) => ({
            id: `new-${Date.now()}-${i}`,
            role: m.role,
            content: m.content,
            citations: m.citations,
            created_at: new Date().toISOString(),
          })),
        ]);

        if (voiceEnabled && data.messages.length > 0) {
          playTTS(data.messages[0].content);
        }
      }
    } catch (e) {
      console.error("Failed to start discussion:", e);
    } finally {
      setActiveAgent(null);
    }
  }

  async function sendMessage() {
    if (!input.trim() || sending) return;

    const userMessage = input.trim();
    setInput("");
    setSending(true);

    // Add user message immediately
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
      const res = await fetch(
        `${API_BASE}/v1/sessions/${sessionId}/message/stream`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            content: userMessage,
            include_close_reader: true,
          }),
        }
      );

      if (!res.ok) {
        throw new Error(`Request failed: ${res.status}`);
      }
      if (!res.body) {
        throw new Error("Streaming not supported");
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      const messageIds: Record<string, string> = {};
      let buffer = "";
      let playedFirstTts = false;
      let lastSeenSequence = -1;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const parts = buffer.split("\n\n");
        buffer = parts.pop() ?? "";

        for (const part of parts) {
          const lines = part.split("\n").map((l) => l.trim());
          const dataLine = lines.find((l) => l.startsWith("data: "));
          if (!dataLine) continue;

          const raw = dataLine.slice(6);
          let event: any;
          try {
            event = JSON.parse(raw);
          } catch {
            continue;
          }

          // Deduplication: skip events already seen based on sequence number
          const seq = typeof event.sequence === "number" ? event.sequence : -1;
          if (seq > 0 && seq <= lastSeenSequence) continue;
          if (seq > 0) lastSeenSequence = seq;

          if (event.type === "message_start") {
            const role = String(event.role || "assistant");
            setActiveAgent(role);
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
            const id = messageIds[role];
            if (!id) continue;
            const delta = String(event.delta || "");
            setMessages((prev) =>
              prev.map((m) =>
                m.id === id ? { ...m, content: m.content + delta } : m
              )
            );
          } else if (event.type === "message_end") {
            const role = String(event.role || "assistant");
            const id = messageIds[role];
            if (!id) continue;
            const content = String(event.content || "");
            const citations = Array.isArray(event.citations)
              ? event.citations
              : null;
            setMessages((prev) =>
              prev.map((m) =>
                m.id === id ? { ...m, content, citations } : m
              )
            );

            if (
              voiceEnabled &&
              !playedFirstTts &&
              role === "facilitator" &&
              content
            ) {
              playedFirstTts = true;
              playTTS(content);
            }
          } else if (event.type === "agent_error") {
            const role = String(event.role || "assistant");
            const id = messageIds[role];
            if (id) {
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === id
                    ? {
                        ...m,
                        content: `[Agent encountered an error: ${event.error}]`,
                      }
                    : m
                )
              );
            }
          } else if (event.type === "done") {
            setActiveAgent(null);
          } else if (event.type === "error") {
            console.error("Streaming error:", event.error);
          }
        }
      }
    } catch (e) {
      console.error("Failed to send message:", e);
    } finally {
      setSending(false);
      setActiveAgent(null);
    }
  }

  async function playTTS(text: string) {
    if (audioRef.current) {
      audioRef.current.pause();
    }

    setPlayingAudio(true);
    try {
      const res = await fetch(`${API_BASE}/v1/tts/synthesize`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, voice: "nova" }),
      });
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      audioRef.current = audio;
      audio.onended = () => {
        setPlayingAudio(false);
        URL.revokeObjectURL(url);
      };
      audio.play();
    } catch (e) {
      console.error("TTS failed:", e);
      setPlayingAudio(false);
    }
  }

  function stopAudio() {
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current = null;
    }
    setPlayingAudio(false);
  }

  // Handle voice transcript - append to input
  function handleVoiceTranscript(text: string) {
    setInput((prev) => (prev ? `${prev} ${text}` : text));
    inputRef.current?.focus();
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center">
          <Loader2 className="w-8 h-8 mx-auto animate-spin text-primary mb-4" />
          <p className="text-muted-foreground">Loading discussion...</p>
        </div>
      </div>
    );
  }

  return (
    <TooltipProvider delayDuration={300}>
    <div className={cn("h-full flex relative", focusMode && "focus-mode-active")}>
      {/* Focus mode overlay */}
      {focusMode && (
        <div className="absolute inset-0 pointer-events-none z-10">
          <div className="absolute inset-0 bg-gradient-radial from-transparent via-transparent to-background/80" />
        </div>
      )}

      {/* Main chat area */}
      <div className={cn("flex-1 flex flex-col min-w-0 z-20", focusMode && "relative")}>
        {/* Header */}
        <div className="glass border-b border-border/50 px-4 py-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Button
                variant="ghost"
                size="icon-sm"
                onClick={onBack}
                className="shrink-0"
              >
                <ArrowLeft className="w-4 h-4" />
              </Button>
              <div>
                <h2 className="font-semibold text-sm">
                  {bookTitle || "Reading Together"}
                </h2>
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  <span>with Sam, Ellis & Kit</span>
                </div>
              </div>
            </div>

            <div className="flex items-center gap-2">
              {/* Session timer */}
              <div className="flex items-center gap-1.5 px-2 py-1 rounded-lg bg-secondary/50 text-xs text-muted-foreground">
                <Timer className="w-3 h-3" />
                <span className="font-mono">{formatTime(sessionTime)}</span>
              </div>

              {/* Focus mode toggle */}
              <Button
                variant="ghost"
                size="icon-sm"
                onClick={() => setFocusMode(!focusMode)}
                className={cn(
                  "h-7 w-7",
                  focusMode && "bg-purple-500/20 text-purple-400"
                )}
                title={focusMode ? "Exit focus mode" : "Enter focus mode"}
              >
                <Focus className="w-3.5 h-3.5" />
              </Button>

              {/* Voice controls */}
              <div className="flex items-center gap-1 p-1 rounded-lg bg-secondary/50">
                <Button
                  variant="ghost"
                  size="icon-sm"
                  onClick={() => setVoiceEnabled(!voiceEnabled)}
                  className={cn(
                    "h-7 w-7",
                    voiceEnabled && "bg-primary/20 text-primary"
                  )}
                >
                  {voiceEnabled ? (
                    <Volume2 className="w-3.5 h-3.5" />
                  ) : (
                    <VolumeX className="w-3.5 h-3.5" />
                  )}
                </Button>
                {playingAudio && (
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    onClick={stopAudio}
                    className="h-7 w-7 text-destructive"
                  >
                    <StopCircle className="w-3.5 h-3.5" />
                  </Button>
                )}
              </div>

              {/* Toggle sidebar on mobile */}
              <Button
                variant="ghost"
                size="icon-sm"
                onClick={() => setShowSidebar(!showSidebar)}
                className="lg:hidden"
              >
                <BookOpen className="w-4 h-4" />
              </Button>
            </div>
          </div>

          {/* Voice activity indicator */}
          {playingAudio && (
            <div className="mt-2 flex items-center gap-2 text-xs text-primary">
              <VoiceWaves active={true} />
              <span>Speaking...</span>
            </div>
          )}
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {messages.map((msg, index) => {
            const config = getAgentConfig(msg.role);
            const isUser = msg.role === "user";
            const Icon = config.icon;

            return (
              <div
                key={msg.id}
                className={cn(
                  "flex gap-3",
                  isUser ? "flex-row-reverse message-enter-user" : "message-enter-agent"
                )}
                style={{ animationDelay: `${index * 50}ms` }}
              >
                {/* Avatar */}
                <div
                  className={cn(
                    "w-9 h-9 rounded-xl flex items-center justify-center shrink-0 transition-all",
                    config.bgColor,
                    msg.id.startsWith("stream-") && "animate-pulse-glow"
                  )}
                >
                  <Icon className={cn("w-4 h-4", config.color)} />
                </div>

                {/* Message bubble */}
                <div
                  className={cn(
                    "max-w-[80%] rounded-2xl px-4 py-3 transition-all",
                    isUser
                      ? "rounded-tr-md bg-primary text-primary-foreground"
                      : `rounded-tl-md ${config.bgColor} border ${config.borderColor}`
                  )}
                >
                  {/* Agent name */}
                  {!isUser && (
                    <div className="flex items-center gap-2 mb-1.5">
                      <span className={cn("text-xs font-medium", config.color)}>
                        {config.name}
                      </span>
                      {config.subtitle && (
                        <span className="text-[10px] text-muted-foreground opacity-60">
                          {config.subtitle}
                        </span>
                      )}
                      {voiceEnabled && msg.content && (
                        <button
                          onClick={() => playTTS(msg.content)}
                          className="opacity-50 hover:opacity-100 transition-opacity"
                        >
                          <Volume2 className="w-3 h-3" />
                        </button>
                      )}
                    </div>
                  )}

                  {/* Content */}
                  {msg.content ? (
                    <div className="text-sm leading-relaxed prose prose-sm prose-invert max-w-none prose-p:my-1.5 prose-li:my-0.5 prose-headings:my-2 prose-pre:bg-black/20 prose-pre:text-xs prose-code:text-xs prose-code:bg-black/20 prose-code:px-1 prose-code:py-0.5 prose-code:rounded">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>
                        {msg.content}
                      </ReactMarkdown>
                    </div>
                  ) : (
                    <p className="text-sm opacity-50 italic">Thinking...</p>
                  )}

                  {/* Citations */}
                  {msg.citations && msg.citations.length > 0 && (() => {
                    const validCitations = msg.citations.filter(
                      (c) => c.verified !== false
                    );
                    const invalidCount = msg.citations.length - validCitations.length;
                    const displayCitations = msg.citations;

                    return (
                      <div className="mt-3 pt-3 border-t border-current/10">
                        <p className="text-xs font-medium opacity-70 mb-2 flex items-center gap-1">
                          <Quote className="w-3 h-3" />
                          Citations
                        </p>
                        <div className="space-y-1.5">
                          {displayCitations.map((cite, i) => {
                            const isUnverified = cite.verified === false;
                            return (
                              <button
                                key={i}
                                className={cn(
                                  "flex items-start gap-2 text-left text-xs transition-opacity group",
                                  isUnverified
                                    ? "opacity-40 hover:opacity-60"
                                    : "opacity-70 hover:opacity-100"
                                )}
                                onClick={() => setSelectedCitation(cite)}
                              >
                                <CitationQualityDot citation={cite} />
                                <ChevronRight className="w-3 h-3 mt-0.5 shrink-0 group-hover:translate-x-0.5 transition-transform" />
                                <span
                                  className={cn(
                                    "line-clamp-2 italic",
                                    isUnverified && "line-through decoration-current/30"
                                  )}
                                >
                                  &ldquo;{cite.text}&rdquo;
                                </span>
                              </button>
                            );
                          })}
                        </div>
                        {invalidCount > 0 && (
                          <p className="text-[10px] text-muted-foreground mt-2 opacity-60">
                            {invalidCount} citation{invalidCount > 1 ? "s" : ""} could not be verified against the source text
                          </p>
                        )}
                      </div>
                    );
                  })()}
                </div>
              </div>
            );
          })}

          {/* Typing indicator */}
          {activeAgent && <TypingIndicator agent={activeAgent} />}

          <div ref={messagesEndRef} />
        </div>

        {/* Input area */}
        <div className="p-4 border-t border-border/50 glass">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              sendMessage();
            }}
            className="flex items-center gap-2"
          >
            {/* Voice input button */}
            <VoiceInput
              onTranscript={handleVoiceTranscript}
              onListeningChange={setIsListening}
              disabled={sending || !session?.is_active}
            />

            {/* Text input */}
            <Input
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="What do you think? What caught your eye?"
              disabled={sending || !session?.is_active}
              className="flex-1"
            />

            {/* Send button */}
            <Button
              type="submit"
              disabled={sending || !input.trim()}
              className={cn(
                "shrink-0 transition-all",
                input.trim() && "shadow-glow"
              )}
            >
              {sending ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Send className="w-4 h-4" />
              )}
            </Button>
          </form>

          {/* Voice listening indicator */}
          {isListening && (
            <div className="mt-2 flex items-center justify-center gap-2 text-xs text-red-400">
              <VoiceWaves active={true} />
              <span>Listening...</span>
            </div>
          )}
        </div>
      </div>

      {/* Sidebar */}
      <div
        className={cn(
          "w-80 border-l border-border/50 glass flex-col hidden lg:flex transition-all duration-300",
          showSidebar ? "flex" : "hidden",
          focusMode && "opacity-30 pointer-events-none"
        )}
      >
        {/* Reading slice */}
        <div className="p-4 border-b border-border/50">
          <h3 className="font-semibold text-sm mb-3 flex items-center gap-2">
            <BookOpen className="w-4 h-4 text-primary" />
            Reading Slice
          </h3>
          <div className="space-y-2 max-h-40 overflow-y-auto">
            {session?.sections.map((section) => (
              <Card key={section.id} className="p-2.5 bg-secondary/30">
                <p className="font-medium text-xs line-clamp-1">
                  {section.title || "Untitled"}
                </p>
                <p className="text-[10px] text-muted-foreground mt-0.5">
                  {section.section_type} • ~{section.reading_time_min || 5} min
                </p>
              </Card>
            ))}
          </div>
        </div>

        {/* Selected citation */}
        {selectedCitation && (() => {
          const quality = citationQualityInfo(selectedCitation);
          const isUnverified = selectedCitation.verified === false;
          return (
            <div className="p-4 border-b border-border/50">
              <h3 className="font-semibold text-sm mb-3 flex items-center gap-2">
                <Quote className="w-4 h-4 text-primary" />
                Selected Citation
              </h3>
              <Card
                className={cn(
                  "p-3",
                  isUnverified
                    ? "bg-red-500/5 border-red-500/20 border-dashed"
                    : "bg-primary/5 border-primary/20"
                )}
              >
                <p
                  className={cn(
                    "text-sm italic leading-relaxed",
                    isUnverified && "opacity-60"
                  )}
                >
                  &ldquo;{selectedCitation.text}&rdquo;
                </p>
                <div className="flex items-center gap-2 mt-2">
                  <span
                    className={cn(
                      "inline-block w-2 h-2 rounded-full",
                      quality.color
                    )}
                  />
                  <span className="text-[10px] text-muted-foreground">
                    {quality.label}
                  </span>
                </div>
                <p className="text-[10px] text-muted-foreground mt-1">
                  Chunk: {selectedCitation.chunk_id.slice(0, 12)}...
                  {selectedCitation.char_start != null &&
                    selectedCitation.char_end != null && (
                      <span className="ml-1">
                        (chars {selectedCitation.char_start}&ndash;{selectedCitation.char_end})
                      </span>
                    )}
                </p>
              </Card>
              <Button
                variant="ghost"
                size="sm"
                className="w-full mt-2 text-xs"
                onClick={() => setSelectedCitation(null)}
              >
                Clear selection
              </Button>
            </div>
          );
        })()}

        {/* Agent presence */}
        <div className="p-4 flex-1">
          <h3 className="font-semibold text-sm mb-3">Your Book Club</h3>
          <div className="space-y-2">
            {(["facilitator", "close_reader", "skeptic"] as const).map(
              (role) => {
                const config = agentConfig[role];
                const Icon = config.icon;
                const isActive = activeAgent === role;

                return (
                  <div
                    key={role}
                    className={cn(
                      "flex items-center gap-3 p-2 rounded-lg transition-all",
                      isActive ? config.bgColor : "opacity-50"
                    )}
                  >
                    <div
                      className={cn(
                        "w-8 h-8 rounded-lg flex items-center justify-center",
                        config.bgColor,
                        isActive && "animate-pulse"
                      )}
                    >
                      <Icon className={cn("w-4 h-4", config.color)} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-xs font-medium">{config.name}</p>
                      <p className="text-[10px] text-muted-foreground">
                        {isActive ? "Thinking..." : config.subtitle || "Ready"}
                      </p>
                    </div>
                    {isActive && (
                      <div className="w-2 h-2 rounded-full bg-primary animate-pulse" />
                    )}
                  </div>
                );
              }
            )}
          </div>
        </div>
      </div>
    </div>
    </TooltipProvider>
  );
}
