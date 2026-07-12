"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Image from "next/image";
import {
  ArrowLeft,
  BookOpenText,
  Check,
  ChevronLeft,
  ChevronRight,
  Cloud,
  CloudOff,
  Disc3,
  Gauge,
  Headphones,
  ListMusic,
  Loader2,
  MoonStar,
  Pause,
  Play,
  RotateCcw,
  RotateCw,
  Search,
  TimerOff,
} from "lucide-react";
import {
  audiobookStreamUrl,
  audiobookCoverUrl,
  cacheListeningState,
  fetchAudiobookManifest,
  fetchAudiobooks,
  fetchListeningState,
  fetchRecentAudiobooks,
  loadCachedListeningState,
  saveListeningState,
  type AudiobookLibrary,
  type AudiobookManifest,
  type AudiobookSummary,
  type ListeningState,
} from "@/lib/audiobooks";
import { cn, formatFileSize } from "@/lib/utils";

type SyncStatus = "loading" | "saving" | "synced" | "offline";
type SleepMode = { kind: "timer"; endsAt: number } | { kind: "track" } | null;

function formatTime(seconds: number | null | undefined): string {
  if (!seconds || !Number.isFinite(seconds)) return "0:00";
  const whole = Math.max(0, Math.floor(seconds));
  const hours = Math.floor(whole / 3600);
  const minutes = Math.floor((whole % 3600) / 60);
  const remainder = whole % 60;
  return hours > 0
    ? `${hours}:${String(minutes).padStart(2, "0")}:${String(remainder).padStart(2, "0")}`
    : `${minutes}:${String(remainder).padStart(2, "0")}`;
}

function AudiobookBrowser() {
  const router = useRouter();
  const [search, setSearch] = useState("");
  const [library, setLibrary] = useState<AudiobookLibrary | null>(null);
  const [books, setBooks] = useState<AudiobookSummary[]>([]);
  const [recent, setRecent] = useState<ListeningState[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    void fetchRecentAudiobooks(controller.signal)
      .then(setRecent)
      .catch(() => setRecent([]));
    return () => controller.abort();
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => {
      setLoading(true);
      setError(null);
      void fetchAudiobooks(search, 0, 60, controller.signal)
        .then((payload) => {
          setLibrary(payload);
          setBooks(payload.audiobooks);
        })
        .catch((loadError) => {
          if (loadError instanceof DOMException && loadError.name === "AbortError") return;
          setError(loadError instanceof Error ? loadError.message : "Could not open the audio library");
        })
        .finally(() => setLoading(false));
    }, 250);
    return () => {
      window.clearTimeout(timeout);
      controller.abort();
    };
  }, [search]);

  async function loadMore() {
    if (!library || loadingMore) return;
    setLoadingMore(true);
    try {
      const payload = await fetchAudiobooks(search, books.length, 60);
      setBooks((current) => [...current, ...payload.audiobooks]);
    } finally {
      setLoadingMore(false);
    }
  }

  return (
    <main className="min-h-screen bg-background px-4 py-8 text-foreground">
      <div className="mx-auto max-w-6xl">
        <button
          type="button"
          onClick={() => router.push("/")}
          className="mb-7 inline-flex items-center gap-2 text-sm text-muted-foreground transition-colors hover:text-primary"
        >
          <ArrowLeft className="h-4 w-4" /> Return to the shelf
        </button>

        <section className="overflow-hidden rounded-[2rem] border border-white/10 bg-[radial-gradient(circle_at_top_left,rgba(217,119,6,0.2),transparent_32%),radial-gradient(circle_at_bottom_right,rgba(45,212,191,0.1),transparent_28%),rgba(12,10,9,0.94)] px-6 py-8 shadow-2xl md:px-10">
          <div className="flex flex-col justify-between gap-8 md:flex-row md:items-end">
            <div className="max-w-3xl">
              <p className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.26em] text-primary/80">
                <Headphones className="h-4 w-4" /> Your listening room
              </p>
              <h1 className="mt-3 font-serif text-4xl font-bold text-white md:text-5xl">
                Let the shelf read to you.
              </h1>
              <p className="mt-4 max-w-2xl leading-7 text-white/65">
                Multi-track folders become one audiobook, playback resumes across browsers,
                and every file stays inside your private local library.
              </p>
            </div>
            {library && (
              <div className="rounded-2xl border border-white/10 bg-black/20 px-5 py-4 text-sm text-white/70">
                <strong className="block font-serif text-2xl text-white">
                  {library.total.toLocaleString()}
                </strong>
                audio collections · {library.total_tracks.toLocaleString()} tracks
              </div>
            )}
          </div>
        </section>

        {recent.length > 0 && (
          <section className="mt-8" aria-labelledby="continue-listening-heading">
            <div className="mb-4 flex items-end justify-between gap-4">
              <div>
                <p className="text-[10px] font-semibold uppercase tracking-[0.24em] text-primary/70">
                  Your place is kept
                </p>
                <h2 id="continue-listening-heading" className="mt-1 flex items-center gap-2 font-serif text-xl font-semibold">
                  <Play className="h-4 w-4 fill-current text-primary" /> Continue listening
                </h2>
              </div>
              <span className="hidden text-xs text-muted-foreground sm:block">
                Synced to your private local reader profile
              </span>
            </div>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {recent.slice(0, 4).map((state) => {
                const fraction = Math.min(
                  1,
                  (state.track_index + (state.duration_seconds ? state.position_seconds / state.duration_seconds : 0)) /
                    Math.max(1, state.track_count),
                );
                return (
                  <button
                    key={state.audiobook_id}
                    type="button"
                    data-testid="continue-listening-card"
                    onClick={() => router.push(`/listen?audioId=${state.audiobook_id}`)}
                    className="rounded-2xl border border-white/10 bg-card/75 p-4 text-left transition-all hover:-translate-y-1 hover:border-primary/45"
                  >
                    <strong className="line-clamp-2 font-serif text-sm">{state.title}</strong>
                    <span className="mt-2 block text-xs text-muted-foreground">
                      Track {state.track_index + 1} of {state.track_count} · {formatTime(state.position_seconds)}
                    </span>
                    <span className="mt-3 block h-1 overflow-hidden rounded-full bg-white/10">
                      <span className="block h-full rounded-full bg-primary" style={{ width: `${Math.max(2, fraction * 100)}%` }} />
                    </span>
                  </button>
                );
              })}
            </div>
          </section>
        )}

        <div className="relative mt-8">
          <Search className="absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search titles, authors, or folders…"
            className="h-12 w-full rounded-2xl border border-white/10 bg-card/80 pl-11 pr-4 outline-none transition-colors placeholder:text-muted-foreground focus:border-primary/60"
          />
        </div>

        {library?.inherited_from_books && (
          <p className="mt-3 text-xs text-muted-foreground">
            Audio was discovered beside your ebooks in {library.audiobooks_dir}.
          </p>
        )}

        {loading ? (
          <div className="flex min-h-72 flex-col items-center justify-center gap-3 text-muted-foreground">
            <Loader2 className="h-7 w-7 animate-spin text-primary" />
            <span>Listening for chapters…</span>
          </div>
        ) : error ? (
          <div className="mt-8 rounded-2xl border border-red-400/20 bg-red-500/5 p-6 text-red-200">
            {error}
          </div>
        ) : books.length === 0 ? (
          <div className="mt-8 rounded-2xl border border-dashed border-white/15 p-12 text-center text-muted-foreground">
            <Disc3 className="mx-auto mb-4 h-9 w-9" />
            No local audio matched that search.
          </div>
        ) : (
          <>
            <section className="mt-8 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {books.map((book) => (
                <button
                  key={book.id}
                  type="button"
                  data-testid="audiobook-card"
                  onClick={() => router.push(`/listen?audioId=${book.id}`)}
                  className="group flex min-h-32 items-center gap-4 rounded-2xl border border-white/10 bg-card/75 p-4 text-left transition-all hover:-translate-y-1 hover:border-primary/45 hover:shadow-glow"
                >
                  <span className="grid h-20 w-16 shrink-0 place-items-center rounded-xl border border-primary/20 bg-[linear-gradient(145deg,rgba(217,119,6,0.28),rgba(15,23,42,0.9))] text-primary shadow-lg">
                    <Headphones className="h-7 w-7" />
                  </span>
                  <span className="min-w-0">
                    <strong className="line-clamp-2 font-serif text-base leading-5 group-hover:text-primary">
                      {book.title}
                    </strong>
                    <span className="mt-2 block text-xs text-muted-foreground">
                      {book.track_count.toLocaleString()} {book.track_count === 1 ? "track" : "tracks"}
                      {` · ${formatFileSize(book.size_bytes)}`}
                    </span>
                    {book.parent_folder && (
                      <span className="mt-1 block truncate text-[11px] text-muted-foreground/65">
                        {book.parent_folder}
                      </span>
                    )}
                  </span>
                </button>
              ))}
            </section>
            {library && books.length < library.total && (
              <div className="mt-8 text-center">
                <button
                  type="button"
                  onClick={() => void loadMore()}
                  disabled={loadingMore}
                  className="rounded-xl border border-white/10 px-5 py-3 text-sm transition-colors hover:border-primary/50 hover:text-primary disabled:opacity-50"
                >
                  {loadingMore ? "Opening more…" : `Show more (${(library.total - books.length).toLocaleString()} remaining)`}
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </main>
  );
}

function AudiobookPlayer({ audiobookId }: { audiobookId: string }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const returnTo = searchParams.get("returnTo");
  const audioRef = useRef<HTMLAudioElement>(null);
  const pendingSeekRef = useRef(0);
  const autoplayRef = useRef(false);
  const positionRef = useRef(0);
  const rateRef = useRef(1);
  const lastCacheAtRef = useRef(0);
  const lastPersistAtRef = useRef(0);
  const persistSequenceRef = useRef(0);
  const [manifest, setManifest] = useState<AudiobookManifest | null>(null);
  const [trackIndex, setTrackIndex] = useState(0);
  const [position, setPosition] = useState(0);
  const [duration, setDuration] = useState(0);
  const [rate, setRate] = useState(1);
  const [playing, setPlaying] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [playbackError, setPlaybackError] = useState<string | null>(null);
  const [syncStatus, setSyncStatus] = useState<SyncStatus>("loading");
  const [sleepMode, setSleepMode] = useState<SleepMode>(null);
  const [sleepRemaining, setSleepRemaining] = useState(0);
  const [coverFailed, setCoverFailed] = useState(false);

  const track = manifest?.tracks[trackIndex] ?? null;
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setLoadError(null);
    setPlaybackError(null);
    setCoverFailed(false);
    void Promise.all([
      fetchAudiobookManifest(audiobookId, controller.signal),
      fetchListeningState(audiobookId, controller.signal),
    ])
      .then(([book, state]) => {
        const cached = loadCachedListeningState(audiobookId);
        const useCached = Boolean(
          cached &&
            Date.parse(cached.updated_at) > Date.parse(state.updated_at || "1970-01-01T00:00:00Z"),
        );
        const restored = useCached && cached ? cached : state;
        const restoredIndex = Math.max(
          0,
          book.tracks.findIndex((item) => item.id === restored.current_track_id),
        );
        pendingSeekRef.current = restored.position_seconds;
        positionRef.current = restored.position_seconds;
        rateRef.current = restored.playback_rate;
        setManifest(book);
        setTrackIndex(restoredIndex);
        setPosition(restored.position_seconds);
        setRate(restored.playback_rate);
        setSyncStatus(useCached ? "saving" : "synced");
        if (useCached && cached) {
          void saveListeningState(audiobookId, cached)
            .then(() => setSyncStatus("synced"))
            .catch(() => setSyncStatus("offline"));
        }
      })
      .catch((loadError) => {
        if (loadError instanceof DOMException && loadError.name === "AbortError") return;
        setLoadError(loadError instanceof Error ? loadError.message : "Could not open this audiobook");
        setSyncStatus("offline");
      })
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, [audiobookId]);

  const persist = useCallback(
    async (completed = false) => {
      const activeTrack = manifest?.tracks[trackIndex];
      if (!activeTrack) return;
      const audio = audioRef.current;
      const activePosition = audio?.currentTime ?? positionRef.current;
      const activeDuration =
        Number.isFinite(audio?.duration) && (audio?.duration ?? 0) > 0
          ? audio?.duration
          : activeTrack.duration_seconds ?? undefined;
      cacheListeningState(audiobookId, {
        current_track_id: activeTrack.id,
        position_seconds: activePosition,
        duration_seconds: activeDuration,
        playback_rate: rateRef.current,
        completed,
      });
      const sequence = ++persistSequenceRef.current;
      setSyncStatus("saving");
      try {
        await saveListeningState(audiobookId, {
          current_track_id: activeTrack.id,
          position_seconds: activePosition,
          duration_seconds: activeDuration,
          playback_rate: rateRef.current,
          completed,
        });
        if (sequence === persistSequenceRef.current) setSyncStatus("synced");
      } catch {
        if (sequence === persistSequenceRef.current) setSyncStatus("offline");
      }
    },
    [audiobookId, manifest, trackIndex],
  );

  const selectTrack = useCallback(
    (nextIndex: number, autoplay = false) => {
      if (!manifest || nextIndex < 0 || nextIndex >= manifest.tracks.length) return;
      void persist();
      pendingSeekRef.current = 0;
      positionRef.current = 0;
      autoplayRef.current = autoplay;
      setPlaybackError(null);
      setPosition(0);
      setDuration(manifest.tracks[nextIndex].duration_seconds ?? 0);
      setTrackIndex(nextIndex);
    },
    [manifest, persist],
  );

  function handleLoadedMetadata() {
    const audio = audioRef.current;
    if (!audio) return;
    audio.playbackRate = rateRef.current;
    const mediaDuration = Number.isFinite(audio.duration) ? audio.duration : 0;
    setDuration(mediaDuration || track?.duration_seconds || 0);
    const restored = Math.min(
      pendingSeekRef.current,
      mediaDuration > 0 ? Math.max(0, mediaDuration - 0.25) : pendingSeekRef.current,
    );
    audio.currentTime = restored;
    positionRef.current = restored;
    setPosition(restored);
    pendingSeekRef.current = 0;
    if (autoplayRef.current) {
      autoplayRef.current = false;
      void audio.play().catch(() => setPlaying(false));
    }
  }

  function handleTimeUpdate() {
    const audio = audioRef.current;
    if (!audio) return;
    positionRef.current = audio.currentTime;
    setPosition(audio.currentTime);
    const now = Date.now();
    if (now - lastCacheAtRef.current >= 1000 && track) {
      lastCacheAtRef.current = now;
      cacheListeningState(audiobookId, {
        current_track_id: track.id,
        position_seconds: audio.currentTime,
        duration_seconds: Number.isFinite(audio.duration) ? audio.duration : undefined,
        playback_rate: rateRef.current,
      });
    }
    if (now - lastPersistAtRef.current >= 5000) {
      lastPersistAtRef.current = now;
      void persist();
    }
    if ("mediaSession" in navigator && Number.isFinite(audio.duration) && audio.duration > 0) {
      try {
        navigator.mediaSession.setPositionState({
          duration: audio.duration,
          playbackRate: audio.playbackRate,
          position: Math.min(audio.currentTime, audio.duration),
        });
      } catch {
        // Some browsers reject position state while metadata is settling.
      }
    }
  }

  async function togglePlayback() {
    const audio = audioRef.current;
    if (!audio) return;
    if (audio.paused) {
      try {
        await audio.play();
      } catch {
        setPlaybackError("This browser could not start the audio track.");
      }
    } else {
      audio.pause();
    }
  }

  function seekBy(seconds: number) {
    const audio = audioRef.current;
    if (!audio) return;
    audio.currentTime = Math.max(0, Math.min(audio.duration || Infinity, audio.currentTime + seconds));
    positionRef.current = audio.currentTime;
    setPosition(audio.currentTime);
  }

  function seekTo(nextPosition: number) {
    const audio = audioRef.current;
    if (!audio) return;
    audio.currentTime = nextPosition;
    positionRef.current = nextPosition;
    setPosition(nextPosition);
  }

  function changeRate(nextRate: number) {
    rateRef.current = nextRate;
    setRate(nextRate);
    if (audioRef.current) audioRef.current.playbackRate = nextRate;
    void persist();
  }

  function handleEnded() {
    if (!manifest) return;
    if (sleepMode?.kind === "track") {
      setSleepMode(null);
      setPlaying(false);
      void persist();
      return;
    }
    if (trackIndex < manifest.tracks.length - 1) {
      selectTrack(trackIndex + 1, true);
    } else {
      setPlaying(false);
      void persist(true);
    }
  }

  useEffect(() => {
    if (!sleepMode || sleepMode.kind !== "timer") {
      setSleepRemaining(0);
      return;
    }
    const update = () => {
      const remaining = Math.max(0, Math.ceil((sleepMode.endsAt - Date.now()) / 1000));
      setSleepRemaining(remaining);
      if (remaining === 0) {
        audioRef.current?.pause();
        setSleepMode(null);
        void persist();
      }
    };
    update();
    const interval = window.setInterval(update, 1000);
    return () => window.clearInterval(interval);
  }, [persist, sleepMode]);

  useEffect(() => {
    if (!("mediaSession" in navigator) || !manifest || !track) return;
    navigator.mediaSession.metadata = new MediaMetadata({
      title: track.title,
      artist: track.artist || manifest.author || "",
      album: manifest.title,
      artwork: coverFailed
        ? []
        : [{ src: audiobookCoverUrl(manifest.id) }],
    });
    navigator.mediaSession.setActionHandler("play", () => void audioRef.current?.play());
    navigator.mediaSession.setActionHandler("pause", () => audioRef.current?.pause());
    navigator.mediaSession.setActionHandler("seekbackward", () => seekBy(-15));
    navigator.mediaSession.setActionHandler("seekforward", () => seekBy(15));
    navigator.mediaSession.setActionHandler("previoustrack", () => selectTrack(trackIndex - 1));
    navigator.mediaSession.setActionHandler("nexttrack", () => selectTrack(trackIndex + 1));
    return () => {
      for (const action of [
        "play",
        "pause",
        "seekbackward",
        "seekforward",
        "previoustrack",
        "nexttrack",
      ] as MediaSessionAction[]) {
        navigator.mediaSession.setActionHandler(action, null);
      }
    };
  }, [coverFailed, manifest, selectTrack, track, trackIndex]);

  useEffect(() => {
    const handleShortcut = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (
        target?.matches("input, textarea, select, button, [contenteditable='true']") ||
        event.ctrlKey ||
        event.metaKey ||
        event.altKey
      ) {
        return;
      }
      const audio = audioRef.current;
      if (!audio) return;
      if (event.code === "Space") {
        event.preventDefault();
        if (audio.paused) void audio.play();
        else audio.pause();
      } else if (event.key === "ArrowLeft") {
        event.preventDefault();
        seekBy(-15);
      } else if (event.key === "ArrowRight") {
        event.preventDefault();
        seekBy(15);
      }
    };
    window.addEventListener("keydown", handleShortcut);
    return () => window.removeEventListener("keydown", handleShortcut);
  }, []);

  useEffect(() => {
    const saveBeforeLeaving = () => void persist();
    window.addEventListener("pagehide", saveBeforeLeaving);
    return () => window.removeEventListener("pagehide", saveBeforeLeaving);
  }, [persist]);

  if (loading) {
    return (
      <div className="grid min-h-screen place-items-center bg-background text-muted-foreground">
        <div className="text-center">
          <Loader2 className="mx-auto mb-3 h-8 w-8 animate-spin text-primary" />
          Opening the listening room…
        </div>
      </div>
    );
  }

  if (loadError || !manifest || !track) {
    return (
      <div className="grid min-h-screen place-items-center bg-background px-4">
        <div className="max-w-lg rounded-2xl border border-red-400/20 bg-card p-8 text-center">
          <Headphones className="mx-auto mb-4 h-9 w-9 text-red-300" />
          <h1 className="font-serif text-2xl">The audio room did not open.</h1>
          <p className="mt-3 text-sm text-muted-foreground">{loadError || "Audiobook not found"}</p>
          <button type="button" className="mt-6 text-primary" onClick={() => router.push("/listen")}>
            Return to the audio library
          </button>
        </div>
      </div>
    );
  }

  return (
    <main className="min-h-screen bg-[radial-gradient(circle_at_top,rgba(217,119,6,0.12),transparent_28%),#0c0a09] px-4 py-6 text-foreground">
      <audio
        ref={audioRef}
        data-testid="audiobook-audio"
        src={audiobookStreamUrl(track)}
        preload="metadata"
        onLoadedMetadata={handleLoadedMetadata}
        onTimeUpdate={handleTimeUpdate}
        onPlay={() => setPlaying(true)}
        onPause={() => {
          setPlaying(false);
          void persist();
        }}
        onEnded={handleEnded}
        onError={() => setPlaybackError("This track could not be decoded by the browser.")}
      />

      <div className="mx-auto max-w-6xl">
        <header className="mb-6 flex flex-wrap items-center justify-between gap-3">
          <button
            type="button"
            onClick={() => router.push("/listen")}
            className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-primary"
          >
            <ArrowLeft className="h-4 w-4" /> Audio library
          </button>
          <div
            data-testid="audiobook-sync-status"
            data-status={syncStatus}
            className={cn(
              "inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs",
              syncStatus === "offline"
                ? "border-amber-400/25 text-amber-200"
                : "border-white/10 text-muted-foreground",
            )}
          >
            {syncStatus === "offline" ? (
              <CloudOff className="h-3.5 w-3.5" />
            ) : syncStatus === "synced" ? (
              <Cloud className="h-3.5 w-3.5" />
            ) : (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            )}
            {syncStatus === "offline" ? "Saved in this browser for now" : syncStatus === "synced" ? "Listening place saved" : "Saving your place"}
          </div>
        </header>

        <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_360px]">
          <section className="overflow-hidden rounded-[2rem] border border-white/10 bg-card/85 shadow-2xl">
            <div className="flex min-h-[28rem] flex-col items-center justify-center bg-[radial-gradient(circle_at_50%_15%,rgba(217,119,6,0.28),transparent_38%),linear-gradient(160deg,rgba(28,25,23,0.96),rgba(7,7,10,0.98))] px-6 py-10 text-center">
              <div className="relative grid h-48 w-36 place-items-center overflow-hidden rounded-2xl border border-primary/25 bg-[linear-gradient(145deg,rgba(217,119,6,0.35),rgba(15,23,42,0.92))] shadow-[0_24px_80px_rgba(0,0,0,0.45)]">
                {coverFailed ? (
                  <Headphones className="h-12 w-12 text-primary" />
                ) : (
                  <Image
                    src={audiobookCoverUrl(manifest.id)}
                    alt={`${manifest.title} cover`}
                    fill
                    sizes="144px"
                    unoptimized
                    className="object-cover"
                    onError={() => setCoverFailed(true)}
                  />
                )}
              </div>
              <p className="mt-8 text-[10px] font-semibold uppercase tracking-[0.28em] text-primary/75">
                Now listening · track {trackIndex + 1} of {manifest.tracks.length}
              </p>
              <h1 className="mt-3 max-w-2xl font-serif text-3xl font-bold text-white md:text-4xl">
                {manifest.title}
              </h1>
              <p className="mt-2 max-w-xl text-sm text-white/55">
                {track.title}
                {(track.artist || manifest.author) && ` · ${track.artist || manifest.author}`}
              </p>

              {playbackError && (
                <div className="mt-5 flex flex-wrap items-center justify-center gap-3 rounded-xl border border-amber-400/20 bg-amber-500/8 px-4 py-3 text-sm text-amber-100">
                  <span>{playbackError}</span>
                  {trackIndex < manifest.tracks.length - 1 && (
                    <button type="button" onClick={() => selectTrack(trackIndex + 1, true)} className="font-medium text-primary hover:underline">
                      Skip this track
                    </button>
                  )}
                </div>
              )}

              <div className="mt-10 w-full max-w-2xl">
                <input
                  aria-label="Listening progress"
                  type="range"
                  min="0"
                  max={Math.max(duration, 1)}
                  step="0.1"
                  value={Math.min(position, Math.max(duration, 1))}
                  onChange={(event) => seekTo(Number(event.target.value))}
                  className="w-full accent-amber-500"
                />
                <div className="mt-2 flex justify-between text-xs tabular-nums text-white/45">
                  <span>{formatTime(position)}</span>
                  <span>{formatTime(duration || track.duration_seconds)}</span>
                </div>
              </div>

              <div className="mt-7 flex items-center justify-center gap-3">
                <button type="button" onClick={() => selectTrack(trackIndex - 1)} disabled={trackIndex === 0} className="rounded-full p-3 text-white/65 hover:bg-white/5 hover:text-white disabled:opacity-25" aria-label="Previous track">
                  <ChevronLeft className="h-5 w-5" />
                </button>
                <button type="button" onClick={() => seekBy(-15)} className="relative rounded-full p-3 text-white/75 hover:bg-white/5" aria-label="Back 15 seconds">
                  <RotateCcw className="h-6 w-6" /><span className="absolute inset-0 grid place-items-center pt-0.5 text-[8px] font-bold">15</span>
                </button>
                <button type="button" onClick={() => void togglePlayback()} className="grid h-16 w-16 place-items-center rounded-full bg-primary text-primary-foreground shadow-glow transition-transform hover:scale-105" aria-label={playing ? "Pause" : "Play"}>
                  {playing ? <Pause className="h-7 w-7 fill-current" /> : <Play className="ml-1 h-7 w-7 fill-current" />}
                </button>
                <button type="button" onClick={() => seekBy(15)} className="relative rounded-full p-3 text-white/75 hover:bg-white/5" aria-label="Forward 15 seconds">
                  <RotateCw className="h-6 w-6" /><span className="absolute inset-0 grid place-items-center pt-0.5 text-[8px] font-bold">15</span>
                </button>
                <button type="button" onClick={() => selectTrack(trackIndex + 1)} disabled={trackIndex === manifest.tracks.length - 1} className="rounded-full p-3 text-white/65 hover:bg-white/5 hover:text-white disabled:opacity-25" aria-label="Next track">
                  <ChevronRight className="h-5 w-5" />
                </button>
              </div>

              <div className="mt-9 flex flex-wrap justify-center gap-2">
                <span className="mr-1 inline-flex items-center gap-1.5 text-xs text-white/45"><Gauge className="h-3.5 w-3.5" /> Speed</span>
                {[0.75, 1, 1.25, 1.5, 2, 2.5, 3].map((value) => (
                  <button key={value} type="button" onClick={() => changeRate(value)} className={cn("rounded-full border px-3 py-1 text-xs", rate === value ? "border-primary/60 bg-primary/10 text-primary" : "border-white/10 text-white/55 hover:border-white/25")}>{value}×</button>
                ))}
              </div>

              <div className="mt-4 flex flex-wrap justify-center gap-2">
                <span className="mr-1 inline-flex items-center gap-1.5 text-xs text-white/45"><MoonStar className="h-3.5 w-3.5" /> Sleep</span>
                {[15, 30, 45].map((minutes) => (
                  <button key={minutes} type="button" onClick={() => setSleepMode({ kind: "timer", endsAt: Date.now() + minutes * 60_000 })} className="rounded-full border border-white/10 px-3 py-1 text-xs text-white/55 hover:border-white/25">{minutes} min</button>
                ))}
                <button type="button" onClick={() => setSleepMode({ kind: "track" })} className="rounded-full border border-white/10 px-3 py-1 text-xs text-white/55 hover:border-white/25">End of track</button>
                {sleepMode && (
                  <button type="button" onClick={() => setSleepMode(null)} className="inline-flex items-center gap-1 rounded-full border border-primary/35 bg-primary/10 px-3 py-1 text-xs text-primary">
                    <TimerOff className="h-3 w-3" /> {sleepMode.kind === "track" ? "After this track" : formatTime(sleepRemaining)}
                  </button>
                )}
              </div>
            </div>

            <footer className="flex flex-wrap items-center justify-between gap-3 border-t border-white/8 px-6 py-4 text-xs text-muted-foreground">
              <span>
                {formatFileSize(manifest.size_bytes)} · {manifest.extensions.join(", ").toUpperCase()}
                <span className="ml-3 hidden text-white/25 sm:inline">Space play/pause · ←/→ 15 seconds</span>
              </span>
              {returnTo?.startsWith("/") && !returnTo.startsWith("//") && (
                <button type="button" onClick={() => router.push(returnTo)} className="inline-flex items-center gap-2 text-primary hover:underline">
                  <BookOpenText className="h-4 w-4" /> Return to the book
                </button>
              )}
            </footer>
          </section>

          <aside className="rounded-[2rem] border border-white/10 bg-card/80 p-4 lg:max-h-[calc(100vh-7rem)] lg:overflow-y-auto">
            <div className="mb-4 flex items-center justify-between px-2">
              <h2 className="flex items-center gap-2 font-serif text-lg"><ListMusic className="h-4 w-4 text-primary" /> Chapters</h2>
              <span className="text-xs text-muted-foreground">{manifest.tracks.length}</span>
            </div>
            <div className="space-y-1.5">
              {manifest.tracks.map((item, index) => (
                <button
                  key={item.id}
                  type="button"
                  data-testid="audiobook-track"
                  onClick={() => selectTrack(index, playing)}
                  className={cn(
                    "flex w-full items-center gap-3 rounded-xl border px-3 py-3 text-left transition-colors",
                    index === trackIndex
                      ? "border-primary/35 bg-primary/8"
                      : "border-transparent hover:border-white/10 hover:bg-white/[0.025]",
                  )}
                >
                  <span className={cn("grid h-8 w-8 shrink-0 place-items-center rounded-lg text-xs", index === trackIndex ? "bg-primary text-primary-foreground" : "bg-white/5 text-muted-foreground")}>
                    {index === trackIndex && playing ? <Disc3 className="h-3.5 w-3.5 animate-spin" /> : index + 1}
                  </span>
                  <span className="min-w-0 flex-1">
                    <strong className={cn("block truncate text-sm font-medium", index === trackIndex && "text-primary")}>{item.title}</strong>
                    <span className="mt-1 block text-[11px] text-muted-foreground">{formatTime(item.duration_seconds)} · {item.extension.toUpperCase()}</span>
                  </span>
                  {index < trackIndex && <Check className="h-3.5 w-3.5 text-emerald-400/70" />}
                </button>
              ))}
            </div>
          </aside>
        </div>
      </div>
    </main>
  );
}

export function AudiobookRoom() {
  const searchParams = useSearchParams();
  const audiobookId = searchParams.get("audioId");
  return audiobookId ? <AudiobookPlayer audiobookId={audiobookId} /> : <AudiobookBrowser />;
}
