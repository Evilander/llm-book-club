"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { API_BASE } from "@/lib/utils";
import type { Message, SessionData } from "@/types/api";

type ExperienceMode = "audio" | "text";

interface OnSentenceReadyParams {
  sentence: string;
  role: string;
  voice: string;
}

interface UseDiscussionSessionOptions {
  sessionId: string;
  experienceMode: ExperienceMode;
  onSentenceReady: (params: OnSentenceReadyParams) => void;
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

export function useDiscussionSession({
  sessionId,
  experienceMode,
  onSentenceReady,
}: UseDiscussionSessionOptions) {
  const [session, setSession] = useState<SessionData | null>(null);
  const [bookTitle, setBookTitle] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [activeAgent, setActiveAgent] = useState<string | null>(null);
  const [sessionTime, setSessionTime] = useState(0);

  const startedRef = useRef(false);
  const speechBuffersRef = useRef<Record<string, string>>({});

  // Keep a ref to experienceMode so SSE callbacks always see the latest value
  // without forcing the streaming closure to re-create on mode change.
  const experienceModeRef = useRef(experienceMode);
  experienceModeRef.current = experienceMode;

  // Same for onSentenceReady -- the callback identity may change but we always
  // want the latest version inside the streaming loop.
  const onSentenceReadyRef = useRef(onSentenceReady);
  onSentenceReadyRef.current = onSentenceReady;

  // Session timer
  useEffect(() => {
    if (!loading && session?.is_active) {
      const interval = setInterval(() => setSessionTime((value) => value + 1), 1000);
      return () => clearInterval(interval);
    }
  }, [loading, session?.is_active]);

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
            onSentenceReadyRef.current({
              sentence: data.messages[0].content,
              role: data.messages[0].role || "facilitator",
              voice: "nova",
            });
          }
        }
        setActiveAgent(null);
      }

      return sessionData as SessionData;
    } catch (error) {
      console.error("Failed to load session:", error);
      return null;
    } finally {
      setLoading(false);
    }
  }, [sessionId]);

  useEffect(() => {
    loadSession();
  }, [loadSession]);

  async function submitMessage(rawMessage: string, opts?: { stopAudioBeforeSend?: () => void }) {
    const messageText = rawMessage.trim();
    if (!messageText || sending) {
      return;
    }

    // Let the caller interrupt audio playback
    opts?.stopAudioBeforeSend?.();

    setSending(true);
    setMessages((prev) => [
      ...prev,
      {
        id: `user-${Date.now()}`,
        role: "user",
        content: messageText,
        citations: null,
        created_at: new Date().toISOString(),
      },
    ]);

    try {
      const res = await fetch(`${API_BASE}/v1/sessions/${sessionId}/message/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          content: messageText,
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
            // Client-side sentence splitting fallback for older backends
            if (experienceModeRef.current === "audio" && !useSentenceEvents && delta) {
              const nextBuffer = `${speechBuffersRef.current[role] || ""}${delta}`;
              const { segments, remaining } = extractSpeakableSegments(nextBuffer);
              speechBuffersRef.current[role] = remaining;
              for (const segment of segments) {
                onSentenceReadyRef.current({
                  sentence: segment,
                  role,
                  voice: agentVoices[role] || "nova",
                });
              }
            }
          } else if (event.type === "sentence_ready") {
            useSentenceEvents = true;
            if (experienceModeRef.current === "audio") {
              const role = String(event.role || "assistant");
              const voice = String(event.voice || agentVoices[role] || "nova");
              const sentence = String(event.sentence || "");
              if (sentence.trim()) {
                onSentenceReadyRef.current({ sentence, role, voice });
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
            // Client-side fallback flush
            if (experienceModeRef.current === "audio" && !useSentenceEvents) {
              const tail = (speechBuffersRef.current[role] || content).trim();
              if (tail) {
                onSentenceReadyRef.current({
                  sentence: tail,
                  role,
                  voice: agentVoices[role] || "nova",
                });
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

  return {
    session,
    setSession,
    bookTitle,
    messages,
    loading,
    sending,
    activeAgent,
    sessionTime,
    loadSession,
    submitMessage,
  };
}
