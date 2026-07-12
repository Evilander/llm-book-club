import { API_BASE } from "@/lib/utils";

export const READING_HISTORY_KEY = "lbc-reading-history-v1";
export const READING_HISTORY_EVENT = "lbc-reading-history-changed";

export interface ReadingHistoryEntry {
  id: string;
  media_id: string | null;
  path: string;
  title: string;
  author?: string;
  extension: string;
  reader_kind: "foliate" | "pdf" | "text";
  can_discuss: boolean;
  book_id: string | null;
  ingest_status: string | null;
  fraction: number;
  chapter?: string;
  updated_at: string;
}

function isHistoryEntry(value: unknown): value is ReadingHistoryEntry {
  if (!value || typeof value !== "object") return false;
  const entry = value as Partial<ReadingHistoryEntry>;
  return Boolean(
    typeof entry.id === "string" &&
      typeof entry.path === "string" &&
      typeof entry.title === "string" &&
      typeof entry.extension === "string" &&
      ["foliate", "pdf", "text"].includes(entry.reader_kind || "") &&
      typeof entry.fraction === "number" &&
      typeof entry.updated_at === "string",
  );
}

export function loadReadingHistory(): ReadingHistoryEntry[] {
  if (typeof window === "undefined") return [];
  try {
    const value = JSON.parse(window.localStorage.getItem(READING_HISTORY_KEY) || "[]");
    if (!Array.isArray(value)) return [];
    return value.filter(isHistoryEntry).sort((left, right) =>
      right.updated_at.localeCompare(left.updated_at),
    );
  } catch {
    return [];
  }
}

export function saveReadingHistory(entry: ReadingHistoryEntry): void {
  if (typeof window === "undefined") return;
  const history = loadReadingHistory();
  const next = [entry, ...history.filter((item) => item.path !== entry.path)].slice(0, 40);
  window.localStorage.setItem(READING_HISTORY_KEY, JSON.stringify(next));
  window.dispatchEvent(new Event(READING_HISTORY_EVENT));
}

interface RecentReadingResponse {
  books: Array<{
    publication_id: string;
    file_path: string;
    title: string;
    author: string | null;
    extension: string;
    reader_kind: string;
    can_discuss: boolean;
    book_id: string | null;
    ingest_status: string | null;
    fraction: number;
    chapter: string | null;
    updated_at: string;
  }>;
}

function mergeHistory(
  localHistory: ReadingHistoryEntry[],
  serverHistory: ReadingHistoryEntry[],
): ReadingHistoryEntry[] {
  const byPath = new Map<string, ReadingHistoryEntry>();
  for (const entry of [...localHistory, ...serverHistory]) {
    const current = byPath.get(entry.path);
    if (!current || entry.updated_at > current.updated_at) byPath.set(entry.path, entry);
  }
  return [...byPath.values()]
    .sort((left, right) => right.updated_at.localeCompare(left.updated_at))
    .slice(0, 40);
}

export async function loadSyncedReadingHistory(): Promise<ReadingHistoryEntry[]> {
  const localHistory = loadReadingHistory();
  try {
    const response = await fetch(`${API_BASE}/v1/reader/recent?limit=40`, {
      cache: "no-store",
    });
    if (!response.ok) return localHistory;
    const payload = (await response.json()) as RecentReadingResponse;
    const serverHistory = payload.books.flatMap((book) =>
      ["foliate", "pdf", "text"].includes(book.reader_kind)
        ? [{
            id: book.publication_id,
            media_id: book.publication_id,
            path: book.file_path,
            title: book.title,
            author: book.author || undefined,
            extension: book.extension,
            reader_kind: book.reader_kind as ReadingHistoryEntry["reader_kind"],
            can_discuss: book.can_discuss,
            book_id: book.book_id,
            ingest_status: book.ingest_status,
            fraction: book.fraction,
            chapter: book.chapter || undefined,
            updated_at: book.updated_at,
          }]
        : [],
    );
    return mergeHistory(localHistory, serverHistory);
  } catch {
    return localHistory;
  }
}
