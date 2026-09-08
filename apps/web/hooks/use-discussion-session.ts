"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { API_BASE } from "@/lib/utils";
import { readEventStream } from "@/lib/event-stream";
import type { CitationData, Message, SessionData } from "@/types/api";

type ExperienceMode = "audio" | "text";
interface OnSentenceReadyParams { sentence: string; role: string; voice: string }
interface UseDiscussionSessionOptions {
  sessionId: string;
  experienceMode: ExperienceMode;
  onSentenceReady: (params: OnSentenceReadyParams) => void;
  startAutomatically?: boolean;
  includeCloseReader?: boolean;
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

export function useDiscussionSession({ sessionId, experienceMode, onSentenceReady, startAutomatically = true, includeCloseReader = true }: UseDiscussionSessionOptions) {
  const [session, setSession] = useState<SessionData | null>(null);
  const [bookTitle, setBookTitle] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [activeAgent, setActiveAgent] = useState<string | null>(null);
  const [sessionTime, setSessionTime] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [activeMessageId, setActiveMessageId] = useState<string | null>(null);
  const startedRef = useRef(false);
  const sendingRef = useRef(false);
  const loadController = useRef<AbortController | null>(null);
  const streamController = useRef<AbortController | null>(null);
  const experienceModeRef = useRef(experienceMode);
  experienceModeRef.current = experienceMode;
  const onSentenceReadyRef = useRef(onSentenceReady);
  onSentenceReadyRef.current = onSentenceReady;

  useEffect(() => {
    if (!loading && session?.is_active) {
      const interval = setInterval(() => setSessionTime((value) => value + 1), 1000);
      return () => clearInterval(interval);
    }
  }, [loading, session?.is_active]);

  const loadSession = useCallback(async () => {
    loadController.current?.abort();
    const controller = new AbortController();
    loadController.current = controller;
    setLoading(true);
    setError(null);
    try {
      const [sessionRes, messagesRes] = await Promise.all([
        fetch(`${API_BASE}/v1/sessions/${sessionId}`, { signal: controller.signal }),
        fetch(`${API_BASE}/v1/sessions/${sessionId}/messages`, { signal: controller.signal }),
      ]);
      if (!sessionRes.ok || !messagesRes.ok) throw new Error("load");
      const sessionData: SessionData = await sessionRes.json();
      const messagesData = await messagesRes.json();
      if (controller.signal.aborted) return null;
      setSession(sessionData);
      setMessages(messagesData.messages || []);
      setLoading(false);
      if (sessionData.book_id) {
        fetch(`${API_BASE}/v1/books/${sessionData.book_id}`, { signal: controller.signal })
          .then((res) => res.ok ? res.json() : null)
          .then((book) => { if (book && !controller.signal.aborted) setBookTitle(book.title || ""); })
          .catch(() => undefined);
      }
      if (startAutomatically && sessionData.is_active && !(messagesData.messages || []).length && !startedRef.current) {
        startedRef.current = true;
        sendingRef.current = true;
        setSending(true);
        setActiveAgent("facilitator");
        const res = await fetch(`${API_BASE}/v1/sessions/${sessionId}/start-discussion`, { method: "POST", signal: controller.signal });
        if (!res.ok) { startedRef.current = false; throw new Error("start"); }
        // Reload canonical IDs, including on older start-discussion responses.
        const saved = await fetch(`${API_BASE}/v1/sessions/${sessionId}/messages`, { signal: controller.signal });
        if (!saved.ok) throw new Error("history");
        const data = await saved.json();
        if (controller.signal.aborted) return null;
        setMessages(data.messages || []);
        if (sessionData.preferences?.experience_mode === "audio" && data.messages?.[0]?.content) {
          onSentenceReadyRef.current({ sentence: data.messages[0].content, role: data.messages[0].role, voice: "nova" });
        }
      }
      return sessionData;
    } catch {
      if (!controller.signal.aborted) setError("The conversation couldn’t be loaded. Please try again.");
      return null;
    } finally {
      if (!controller.signal.aborted) {
        setLoading(false);
        sendingRef.current = false;
        setSending(false);
        setActiveAgent(null);
      }
    }
  }, [sessionId, startAutomatically]);

  useEffect(() => {
    void loadSession();
    return () => { loadController.current?.abort(); streamController.current?.abort(); };
  }, [loadSession]);

  async function submitMessage(rawMessage: string, opts?: { stopAudioBeforeSend?: () => void }) {
    const content = rawMessage.trim();
    if (!content || sendingRef.current || loading || !session?.is_active) return false;
    opts?.stopAudioBeforeSend?.();
    sendingRef.current = true;
    setSending(true);
    setError(null);
    const controller = new AbortController();
    streamController.current = controller;
    const optimisticId = `user-${crypto.randomUUID()}`;
    setMessages((prev) => [...prev, { id: optimisticId, role: "user", content, citations: null, created_at: new Date().toISOString() }]);
    let accepted = false;
    let finished = false;
    let agentFailed = false;
    const messageIds: Record<string, string> = {};
    const voices: Record<string, string> = {};
    const speechBuffers: Record<string, string> = {};
    let useSentenceEvents = false;
    let lastSequence = -1;
    try {
      const response = await fetch(`${API_BASE}/v1/sessions/${sessionId}/message/stream`, {
        method: "POST", headers: { "Content-Type": "application/json" }, signal: controller.signal,
        body: JSON.stringify({ content, include_close_reader: includeCloseReader, adaptive: includeCloseReader }),
      });
      if (!response.ok || !response.body) {
        const data = await response.json().catch(() => null);
        if (typeof data?.detail === "string" && data.detail.includes("Session message limit")) throw new Error("session-limit");
        throw new Error("send");
      }
      accepted = true;
      for await (const event of readEventStream(response.body)) {
        const sequence = typeof event.sequence === "number" ? event.sequence : null;
        if (sequence !== null && sequence <= lastSequence) continue;
        if (sequence !== null) lastSequence = sequence;
        const role = typeof event.role === "string" ? event.role : "assistant";
        const voice = typeof event.voice === "string" ? event.voice : voices[role] || "nova";
        if (event.type === "message_start") {
          if (event.sentence_events === true) useSentenceEvents = true;
          const id = typeof event.message_id === "string" ? event.message_id : `stream-${crypto.randomUUID()}`;
          messageIds[role] = id;
          voices[role] = voice;
          speechBuffers[role] = "";
          setActiveAgent(role);
          setActiveMessageId(id);
          setMessages((prev) => [...prev, { id, role, content: "", citations: null, created_at: new Date().toISOString() }]);
        } else if (event.type === "message_delta") {
          const delta = typeof event.delta === "string" ? event.delta : "";
          const id = messageIds[role];
          if (!id) continue;
          setMessages((prev) => prev.map((message) => message.id === id ? { ...message, content: message.content + delta } : message));
          if (experienceModeRef.current === "audio" && !useSentenceEvents && delta) {
            const { segments, remaining } = extractSpeakableSegments((speechBuffers[role] || "") + delta);
            speechBuffers[role] = remaining;
            for (const sentence of segments) onSentenceReadyRef.current({ sentence, role, voice });
          }
        } else if (event.type === "sentence_ready") {
          useSentenceEvents = true;
          if (experienceModeRef.current === "audio" && typeof event.sentence === "string" && event.sentence.trim()) onSentenceReadyRef.current({ sentence: event.sentence, role, voice });
        } else if (event.type === "message_end") {
          const id = messageIds[role];
          const savedId = typeof event.message_id === "string" ? event.message_id : id;
          const text = typeof event.content === "string" ? event.content : null;
          const citations = Array.isArray(event.citations) ? event.citations as CitationData[] : [];
          setMessages((prev) => prev.map((message) => message.id === id ? { ...message, id: savedId, content: text ?? message.content, citations } : message));
          if (experienceModeRef.current === "audio" && !useSentenceEvents && speechBuffers[role]?.trim()) onSentenceReadyRef.current({ sentence: speechBuffers[role].trim(), role, voice });
          delete speechBuffers[role];
          setActiveMessageId(null);
        } else if (event.type === "agent_error") {
          agentFailed = true;
          setError("One reader couldn’t finish their reply. Your conversation so far is still here.");
          setMessages((prev) => prev.filter((message) => message.id !== messageIds[role] || message.content.length > 0));
          setActiveMessageId(null);
        } else if (event.type === "error") {
          throw new Error("stream");
        } else if (event.type === "done") {
          finished = true;
          break;
        }
      }
      if (!finished) throw new Error("interrupted");
      return !agentFailed;
    } catch (failure) {
      if (!controller.signal.aborted) {
        setError(failure instanceof Error && failure.message === "session-limit" ? "This conversation is full. Reconnect your companion to continue with your saved book memory." : accepted ? "The reply was interrupted. Refresh the conversation to check what was saved before sending again." : "Your message couldn’t be sent. Check your connection and try again.");
        if (!accepted) setMessages((prev) => prev.filter((message) => message.id !== optimisticId));
      }
      return false;
    } finally {
      if (!controller.signal.aborted) {
        sendingRef.current = false;
        setSending(false);
        setActiveAgent(null);
        setActiveMessageId(null);
      }
    }
  }

  return { session, setSession, bookTitle, messages, loading, sending, activeAgent, activeMessageId, sessionTime, error, loadSession, submitMessage };
}
