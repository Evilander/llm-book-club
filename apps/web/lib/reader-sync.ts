import { API_BASE } from "@/lib/utils";
import type { ReaderTarget } from "@/components/reader/reader-interactions";

export interface ReaderPublicationDescriptor {
  file_path: string;
  title: string;
  author?: string;
  extension: string;
  reader_kind: "foliate" | "pdf" | "text";
  can_discuss: boolean;
  book_id: string | null;
  ingest_status: string | null;
}

export interface SyncedReaderPreferences {
  theme: "paper" | "night" | "contrast";
  flow: "paginated" | "scrolled";
  fontSize: number;
  lineHeight: number;
  maxWidth: number;
}

export interface ReaderMark {
  id: string;
  kind?: "highlight" | "note" | "bookmark";
  quote: string;
  note: string;
  fraction: number;
  chapter?: string;
  page?: string;
  target?: ReaderTarget;
  createdAt: string;
  updatedAt?: string;
}

interface ServerAnnotation {
  id: string;
  kind: "highlight" | "note" | "bookmark";
  quote: string;
  note: string;
  fraction: number;
  chapter: string | null;
  page: string | null;
  target: ReaderTarget | null;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
}

export interface ServerReadingState {
  id: string;
  publication_id: string;
  file_path: string;
  title: string;
  author: string | null;
  extension: string;
  reader_kind: "foliate" | "pdf" | "text";
  can_discuss: boolean;
  book_id: string | null;
  ingest_status: string | null;
  fraction: number;
  chapter: string | null;
  page: string | null;
  location: {
    fraction?: number;
    cfi?: string;
    chapter?: string;
    page?: string;
  };
  updated_at: string;
}

export interface ReaderSnapshot {
  publication_id: string;
  preferences: SyncedReaderPreferences;
  preferences_updated_at: string;
  state: ServerReadingState | null;
  annotations: ServerAnnotation[];
}

export interface MergedReaderMarks {
  marks: ReaderMark[];
  localOnly: ReaderMark[];
}

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

function annotationToMark(annotation: ServerAnnotation): ReaderMark {
  return {
    id: annotation.id,
    kind: annotation.kind,
    quote: annotation.quote,
    note: annotation.note,
    fraction: annotation.fraction,
    chapter: annotation.chapter || undefined,
    page: annotation.page || undefined,
    target: annotation.target || undefined,
    createdAt: annotation.created_at,
    updatedAt: annotation.updated_at,
  };
}

function markTimestamp(mark: ReaderMark): number {
  return Date.parse(mark.updatedAt || mark.createdAt) || 0;
}

export function mergeReaderMarks(
  localMarks: ReaderMark[],
  serverAnnotations: ServerAnnotation[],
  pendingDeletionIds: Set<string>,
): MergedReaderMarks {
  const tombstones = new Set(
    serverAnnotations
      .filter((annotation) => annotation.deleted_at)
      .map((annotation) => annotation.id),
  );
  const serverMarks = new Map(
    serverAnnotations
      .filter((annotation) => !annotation.deleted_at)
      .map((annotation) => [annotation.id, annotationToMark(annotation)]),
  );
  const merged = new Map<string, ReaderMark>();
  const localOnly: ReaderMark[] = [];

  for (const localMark of localMarks) {
    if (tombstones.has(localMark.id) || pendingDeletionIds.has(localMark.id)) continue;
    const serverMark = serverMarks.get(localMark.id);
    if (!serverMark) {
      merged.set(localMark.id, localMark);
      if (UUID_PATTERN.test(localMark.id)) localOnly.push(localMark);
      continue;
    }
    merged.set(
      localMark.id,
      markTimestamp(localMark) > markTimestamp(serverMark) ? localMark : serverMark,
    );
    serverMarks.delete(localMark.id);
  }

  for (const [id, serverMark] of serverMarks) {
    if (!pendingDeletionIds.has(id)) merged.set(id, serverMark);
  }

  return {
    marks: [...merged.values()]
      .sort((left, right) => right.createdAt.localeCompare(left.createdAt))
      .slice(0, 500),
    localOnly,
  };
}

async function parseResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Reader sync failed" }));
    throw new Error(error.detail || `Reader sync failed (HTTP ${response.status})`);
  }
  return response.json() as Promise<T>;
}

export async function fetchReaderSnapshot(
  filePath: string,
  signal?: AbortSignal,
): Promise<ReaderSnapshot> {
  const query = new URLSearchParams({ file_path: filePath });
  const response = await fetch(`${API_BASE}/v1/reader/state?${query}`, {
    signal,
    cache: "no-store",
  });
  return parseResponse<ReaderSnapshot>(response);
}

export async function persistReaderState(
  publication: ReaderPublicationDescriptor,
  location: {
    fraction: number;
    cfi?: string;
    chapter?: string;
    page?: string;
  },
  preferences: SyncedReaderPreferences,
): Promise<ReaderSnapshot> {
  const response = await fetch(`${API_BASE}/v1/reader/state`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...publication, location, preferences }),
    keepalive: true,
  });
  return parseResponse<ReaderSnapshot>(response);
}

export async function persistReaderMark(
  publication: ReaderPublicationDescriptor,
  mark: ReaderMark,
): Promise<void> {
  const response = await fetch(`${API_BASE}/v1/reader/annotations/${mark.id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      publication,
      kind: mark.kind || (mark.quote ? "highlight" : "note"),
      quote: mark.quote,
      note: mark.note,
      fraction: mark.fraction,
      chapter: mark.chapter,
      page: mark.page,
      target: mark.target,
      created_at: mark.createdAt,
      updated_at: mark.updatedAt || mark.createdAt,
    }),
    keepalive: true,
  });
  await parseResponse<ServerAnnotation>(response);
}

export async function deleteReaderMark(
  filePath: string,
  markId: string,
): Promise<void> {
  const query = new URLSearchParams({ file_path: filePath });
  const response = await fetch(
    `${API_BASE}/v1/reader/annotations/${markId}?${query}`,
    { method: "DELETE", keepalive: true },
  );
  await parseResponse<ServerAnnotation>(response);
}
