"use client";

import { useCallback, useRef, useState } from "react";
import { API_BASE } from "@/lib/utils";

type ExperienceMode = "audio" | "text";

interface SpeechQueueItem {
  text: string;
  role: string;
  voice: string;
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

export function useAudioPlayback() {
  const [playingAudio, setPlayingAudio] = useState(false);
  const [speakingAgent, setSpeakingAgent] = useState<string | null>(null);

  const audioRef = useRef<HTMLAudioElement | null>(null);
  const audioObjectUrlRef = useRef<string | null>(null);
  const speechQueueRef = useRef<SpeechQueueItem[]>([]);
  const speechRunningRef = useRef(false);
  const abortRef = useRef<AbortController | null>(null);

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

  return {
    playingAudio,
    speakingAgent,
    stopAudio,
    enqueueSpeech,
  };
}
