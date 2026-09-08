"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { FolderOpen, Gauge, Headphones } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { audiobookStreamUrl, cn, formatFileSize } from "@/lib/utils";
import type { AudiobookMatch } from "@/types/api";

const PLAYBACK_RATES = [0.9, 1, 1.15, 1.25, 1.5];

interface LocalAudiobookPlayerProps {
  match: AudiobookMatch;
  bookTitle?: string | null;
  bookAuthor?: string | null;
  compact?: boolean;
}

function formatDuration(totalSeconds: number) {
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = Math.floor(totalSeconds % 60);

  if (hours > 0) {
    return `${hours}:${minutes.toString().padStart(2, "0")}:${seconds
      .toString()
      .padStart(2, "0")}`;
  }
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
}

export function LocalAudiobookPlayer({
  match,
  bookTitle,
  bookAuthor,
  compact = false,
}: LocalAudiobookPlayerProps) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const [playbackRate, setPlaybackRate] = useState(1);
  const [duration, setDuration] = useState<string | null>(null);

  const title = match.title_guess || bookTitle || match.filename;
  const streamUrl = useMemo(() => audiobookStreamUrl(match.path), [match.path]);
  const folderLabel = match.parent_folder || match.filename;

  useEffect(() => {
    if (audioRef.current) {
      audioRef.current.playbackRate = playbackRate;
    }
  }, [playbackRate]);

  function updateMediaSession() {
    if (
      typeof window === "undefined" ||
      typeof navigator === "undefined" ||
      !("mediaSession" in navigator) ||
      !("MediaMetadata" in window)
    ) {
      return;
    }

    try {
      navigator.mediaSession.metadata = new window.MediaMetadata({
        title,
        artist: bookAuthor || "Local audiobook",
        album: bookTitle || title,
      });
    } catch {
      // Browser support varies; playback should never depend on Media Session.
    }
  }

  function handleLoadedMetadata() {
    const seconds = audioRef.current?.duration;
    setDuration(seconds && Number.isFinite(seconds) ? formatDuration(seconds) : null);
  }

  return (
    <div
      className={cn(
        "rounded-2xl border border-emerald-500/20 bg-emerald-500/5",
        compact ? "p-3" : "p-4"
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <p className="truncate text-sm font-medium text-foreground">{title}</p>
            <Badge variant="outline" className="text-[10px]">
              {match.extension.toUpperCase()}
            </Badge>
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            {match.match_reason || "Likely local audiobook match"}
          </p>
        </div>
        <Badge variant="success" className="shrink-0 gap-1">
          <Headphones className="h-3 w-3" />
          Local
        </Badge>
      </div>

      <div className="mt-3 flex min-w-0 items-center gap-2 text-[11px] text-muted-foreground">
        <FolderOpen className="h-3.5 w-3.5 shrink-0" />
        <span className="truncate">{folderLabel}</span>
      </div>

      <audio
        ref={audioRef}
        controls
        preload="metadata"
        src={streamUrl}
        onLoadedMetadata={handleLoadedMetadata}
        onPlay={updateMediaSession}
        className="mt-3 w-full"
      />

      <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <Gauge className="h-3.5 w-3.5" />
          <span>{duration ? `${duration} loaded` : formatFileSize(match.size_bytes)}</span>
        </div>
        <div className="flex flex-wrap gap-1">
          {PLAYBACK_RATES.map((rate) => (
            <Button
              key={rate}
              type="button"
              variant={playbackRate === rate ? "default" : "outline"}
              size="sm"
              className="min-w-10 px-2"
              onClick={() => setPlaybackRate(rate)}
              aria-label={`Set audiobook speed to ${rate}x`}
            >
              {rate}x
            </Button>
          ))}
        </div>
      </div>
    </div>
  );
}
