import { API_BASE } from "@/lib/utils";

export interface AudiobookSummary {
  id: string;
  title: string;
  source_kind: "folder" | "file";
  extension: string;
  extensions: string[];
  size_bytes: number;
  track_count: number;
  parent_folder: string | null;
  modified_at: string | null;
  match_score?: number | null;
  match_reason?: string | null;
}

export interface AudiobookTrack {
  id: string;
  index: number;
  title: string;
  album: string | null;
  artist: string | null;
  filename: string;
  extension: string;
  size_bytes: number;
  duration_seconds: number | null;
  stream_url: string;
}

export interface AudiobookManifest extends AudiobookSummary {
  author: string | null;
  duration_seconds: number | null;
  tracks: AudiobookTrack[];
}

export interface AudiobookLibrary {
  audiobooks_dir: string;
  inherited_from_books: boolean;
  total: number;
  total_tracks: number;
  audiobooks: AudiobookSummary[];
}

export interface ListeningState {
  audiobook_id: string;
  title: string;
  current_track_id: string;
  track_index: number;
  track_count: number;
  position_seconds: number;
  duration_seconds: number | null;
  playback_rate: number;
  completed: boolean;
  persisted: boolean;
  updated_at: string | null;
}

export interface CachedListeningState {
  current_track_id: string;
  position_seconds: number;
  duration_seconds?: number;
  playback_rate: number;
  completed?: boolean;
  updated_at: string;
}

function listeningCacheKey(audiobookId: string): string {
  return `lbc-audiobook-state-${audiobookId}`;
}

export function loadCachedListeningState(audiobookId: string): CachedListeningState | null {
  if (typeof window === "undefined") return null;
  try {
    const value = JSON.parse(window.localStorage.getItem(listeningCacheKey(audiobookId)) || "null");
    if (
      !value ||
      typeof value.current_track_id !== "string" ||
      typeof value.position_seconds !== "number" ||
      !Number.isFinite(value.position_seconds) ||
      value.position_seconds < 0 ||
      typeof value.playback_rate !== "number" ||
      !Number.isFinite(value.playback_rate) ||
      value.playback_rate < 0.5 ||
      value.playback_rate > 3 ||
      typeof value.updated_at !== "string" ||
      !Number.isFinite(Date.parse(value.updated_at))
    ) {
      return null;
    }
    return value as CachedListeningState;
  } catch {
    return null;
  }
}

export function cacheListeningState(
  audiobookId: string,
  state: Omit<CachedListeningState, "updated_at">,
): CachedListeningState {
  const cached = { ...state, updated_at: new Date().toISOString() };
  if (typeof window !== "undefined") {
    try {
      window.localStorage.setItem(listeningCacheKey(audiobookId), JSON.stringify(cached));
    } catch {
      // Server persistence remains authoritative when browser storage is unavailable.
    }
  }
  return cached;
}

async function parseResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const payload = await response.json().catch(() => ({ detail: "Audiobook request failed" }));
    throw new Error(payload.detail || `Audiobook request failed (HTTP ${response.status})`);
  }
  return response.json() as Promise<T>;
}

export async function fetchAudiobooks(
  search = "",
  skip = 0,
  limit = 60,
  signal?: AbortSignal,
): Promise<AudiobookLibrary> {
  const query = new URLSearchParams({ skip: String(skip), limit: String(limit) });
  if (search.trim()) query.set("search", search.trim());
  const response = await fetch(`${API_BASE}/v1/audiobooks?${query}`, {
    cache: "no-store",
    signal,
  });
  return parseResponse<AudiobookLibrary>(response);
}

export async function fetchAudiobookMatches(
  title: string,
  author?: string,
  signal?: AbortSignal,
): Promise<AudiobookSummary[]> {
  const query = new URLSearchParams({ title, limit: "3" });
  if (author) query.set("author", author);
  const response = await fetch(`${API_BASE}/v1/audiobooks/matches?${query}`, {
    cache: "no-store",
    signal,
  });
  return parseResponse<AudiobookSummary[]>(response);
}

export async function fetchAudiobookManifest(
  audiobookId: string,
  signal?: AbortSignal,
): Promise<AudiobookManifest> {
  const response = await fetch(`${API_BASE}/v1/audiobooks/${audiobookId}`, {
    cache: "no-store",
    signal,
  });
  return parseResponse<AudiobookManifest>(response);
}

export async function fetchListeningState(
  audiobookId: string,
  signal?: AbortSignal,
): Promise<ListeningState> {
  const response = await fetch(`${API_BASE}/v1/audiobooks/${audiobookId}/state`, {
    cache: "no-store",
    signal,
  });
  return parseResponse<ListeningState>(response);
}

export async function fetchRecentAudiobooks(
  signal?: AbortSignal,
): Promise<ListeningState[]> {
  const response = await fetch(`${API_BASE}/v1/audiobooks/recent?limit=12`, {
    cache: "no-store",
    signal,
  });
  const payload = await parseResponse<{ books: ListeningState[] }>(response);
  return payload.books;
}

export async function saveListeningState(
  audiobookId: string,
  state: {
    current_track_id: string;
    position_seconds: number;
    duration_seconds?: number;
    playback_rate: number;
    completed?: boolean;
  },
): Promise<ListeningState> {
  const response = await fetch(`${API_BASE}/v1/audiobooks/${audiobookId}/state`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(state),
    keepalive: true,
  });
  return parseResponse<ListeningState>(response);
}

export function audiobookStreamUrl(track: AudiobookTrack): string {
  return `${API_BASE}${track.stream_url}`;
}

export function audiobookCoverUrl(audiobookId: string): string {
  return `${API_BASE}/v1/audiobooks/${audiobookId}/cover`;
}
