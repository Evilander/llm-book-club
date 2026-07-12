"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import Image from "next/image";
import Link from "next/link";
import { toast } from "sonner";
import {
  Book,
  Upload,
  Clock,
  FileText,
  AlertCircle,
  CheckCircle,
  Loader2,
  BookMarked,
  Sparkles,
  FileType,
  Search,
  FolderOpen,
  Plus,
  ArrowRight,
  ChevronDown,
  Headphones,
  MessageCircle,
  PlayCircle,
  RefreshCw,
  BookOpenText,
  PanelsTopLeft,
  Eye,
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { API_BASE, cn, formatFileSize, formatReadingTime } from "@/lib/utils";
import {
  loadReadingHistory,
  loadSyncedReadingHistory,
  READING_HISTORY_EVENT,
  READING_HISTORY_KEY,
  type ReadingHistoryEntry,
} from "@/lib/reading-history";

interface IngestedBook {
  id: string;
  title: string;
  author: string | null;
  filename: string;
  file_type: string;
  file_size_bytes: number;
  total_chars: number | null;
  ingest_status: string;
  ingest_error: string | null;
  created_at: string;
  section_count: number;
  session_count: number;
  last_session_at: string | null;
  has_audiobook: boolean;
}

interface LocalBook {
  id: string;
  path: string;
  filename: string;
  extension: string;
  format_family: string;
  reader_kind: "foliate" | "pdf" | "text" | null;
  can_discuss: boolean;
  size_bytes: number;
  title_guess: string;
  parent_folder: string | null;
  book_id: string | null;
  ingest_status: string | null;
  ingest_error: string | null;
}

interface LocalPublicationDetails {
  id: string;
  title: string | null;
  author: string | null;
  has_cover: boolean;
}

interface CatalogScanStatus {
  kind: "books" | "audiobooks";
  status: "idle" | "queueing" | "queued" | "scanning" | "failed";
  generation: number;
  item_count: number;
  job_id: string | null;
  error: string | null;
}

export interface ReadableBook {
  id: string;
  path: string;
  title_guess: string;
  author?: string | null;
  extension: string;
  reader_kind: "foliate" | "pdf" | "text" | null;
  can_discuss: boolean;
  book_id: string | null;
  ingest_status: string | null;
}

interface BookShelfProps {
  onSelectBook: (bookId: string) => void;
  onReadBook: (book: ReadableBook) => void;
}

type FormatFilter = "all" | "epub" | "pdf" | "kindle" | "comic" | "text";
type LibrarySort = "title" | "modified";

const LOCAL_PAGE_SIZE = 24;

const FORMAT_FILTERS: { label: string; value: FormatFilter }[] = [
  { label: "All", value: "all" },
  { label: "EPUB", value: "epub" },
  { label: "PDF", value: "pdf" },
  { label: "Kindle / FB2", value: "kindle" },
  { label: "Comics", value: "comic" },
  { label: "Text", value: "text" },
];

function timeAgo(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(ms / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d ago`;
  const weeks = Math.floor(days / 7);
  if (weeks < 5) return `${weeks}w ago`;
  const months = Math.floor(days / 30);
  return `${months}mo ago`;
}

function getBookGradient(seed: string): string {
  const gradients = [
    "from-amber-500/70 via-orange-500/60 to-rose-500/65",
    "from-orange-400/70 via-amber-500/60 to-yellow-500/55",
    "from-red-400/65 via-orange-500/60 to-amber-500/55",
    "from-teal-400/65 via-cyan-500/55 to-sky-500/50",
    "from-emerald-400/60 via-teal-500/55 to-cyan-500/50",
    "from-indigo-400/65 via-violet-500/55 to-purple-500/55",
    "from-purple-400/65 via-fuchsia-500/55 to-rose-500/55",
    "from-sky-400/65 via-blue-500/55 to-indigo-500/55",
  ];
  const hash = seed.split("").reduce((a, c) => a + c.charCodeAt(0), 0);
  return gradients[hash % gradients.length];
}

function getFileIcon(ext: string) {
  switch (ext.toLowerCase()) {
    case "pdf":
      return <FileType className="w-5 h-5" />;
    case "epub":
      return <BookMarked className="w-5 h-5" />;
    case "mobi":
    case "azw":
    case "azw3":
    case "prc":
    case "fb2":
      return <BookOpenText className="w-5 h-5" />;
    case "cbz":
      return <PanelsTopLeft className="w-5 h-5" />;
    default:
      return <FileText className="w-5 h-5" />;
  }
}

function statusBadge(status: string) {
  switch (status) {
    case "completed":
      return (
        <Badge variant="success" className="gap-1">
          <CheckCircle className="w-3 h-3" /> Ready
        </Badge>
      );
    case "processing":
      return (
        <Badge variant="warning" className="gap-1">
          <Loader2 className="w-3 h-3 animate-spin" /> Processing
        </Badge>
      );
    case "queued":
      return (
        <Badge variant="secondary" className="gap-1">
          <Clock className="w-3 h-3" /> Queued
        </Badge>
      );
    case "failed":
      return (
        <Badge variant="error" className="gap-1">
          <AlertCircle className="w-3 h-3" /> Failed
        </Badge>
      );
    default:
      return <Badge variant="outline">{status}</Badge>;
  }
}

function BookCover({
  title,
  ext,
  mediaId,
  large = false,
}: {
  title: string;
  ext: string;
  mediaId?: string | null;
  large?: boolean;
}) {
  const [coverLoaded, setCoverLoaded] = useState(false);
  const [coverFailed, setCoverFailed] = useState(false);
  const coverUrl = mediaId ? `${API_BASE}/v1/library/local/${mediaId}/cover` : null;

  useEffect(() => {
    setCoverLoaded(false);
    setCoverFailed(false);
  }, [coverUrl]);

  return (
    <div
      className={cn(
        "relative shrink-0 overflow-hidden rounded-lg border border-white/10 bg-gradient-to-br shadow-md",
        large ? "mx-auto h-36 w-24" : "h-20 w-14",
        getBookGradient(title)
      )}
    >
      <div className="absolute inset-0 bg-[linear-gradient(140deg,rgba(255,255,255,0.18),transparent_40%,rgba(0,0,0,0.15)_100%)]" />
      <div className="absolute inset-y-0 left-0 w-1 bg-black/15" />
      <div className="relative flex flex-col items-center justify-center h-full px-1.5">
        {getFileIcon(ext)}
        <span className="mt-1 text-[9px] font-bold uppercase tracking-wider text-white/80">
          {ext}
        </span>
      </div>
      {coverUrl && !coverFailed && (
        <Image
          src={coverUrl}
          alt={`Cover of ${title}`}
          fill
          unoptimized
          sizes={large ? "96px" : "56px"}
          className={cn(
            "z-10 object-cover transition-opacity duration-500",
            coverLoaded ? "opacity-100" : "opacity-0",
          )}
          onLoad={() => setCoverLoaded(true)}
          onError={() => setCoverFailed(true)}
        />
      )}
    </div>
  );
}

export function BookShelf({ onSelectBook, onReadBook }: BookShelfProps) {
  const [ingested, setIngested] = useState<IngestedBook[]>([]);
  const [loadingIngested, setLoadingIngested] = useState(true);

  const [localBooks, setLocalBooks] = useState<LocalBook[]>([]);
  const [localDetails, setLocalDetails] = useState<Record<string, LocalPublicationDetails>>({});
  const requestedDetailsRef = useRef(new Set<string>());
  const [readingHistory, setReadingHistory] = useState<ReadingHistoryEntry[]>([]);
  const [localTotal, setLocalTotal] = useState(0);
  const [catalogTotal, setCatalogTotal] = useState(0);
  const [discussionCapableTotal, setDiscussionCapableTotal] = useState(0);
  const [formatCounts, setFormatCounts] = useState<Record<string, number>>({});
  const [indexedAt, setIndexedAt] = useState<string | null>(null);
  const [loadingLocal, setLoadingLocal] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [refreshingCatalog, setRefreshingCatalog] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);

  const [search, setSearch] = useState("");
  const [formatFilter, setFormatFilter] = useState<FormatFilter>("all");
  const [librarySort, setLibrarySort] = useState<LibrarySort>("modified");

  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);

  const [ingesting, setIngesting] = useState<Record<string, string>>({});

  const [debouncedSearch, setDebouncedSearch] = useState("");
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(undefined);

  useEffect(() => {
    debounceRef.current = setTimeout(() => setDebouncedSearch(search), 300);
    return () => clearTimeout(debounceRef.current);
  }, [search]);

  useEffect(() => {
    let disposed = false;
    const refreshHistory = (event?: Event) => {
      if (event instanceof StorageEvent && event.key && event.key !== READING_HISTORY_KEY) {
        return;
      }
      setReadingHistory(loadReadingHistory().slice(0, 6));
      void loadSyncedReadingHistory().then((history) => {
        if (!disposed) setReadingHistory(history.slice(0, 6));
      });
    };
    refreshHistory();
    window.addEventListener("storage", refreshHistory);
    window.addEventListener("focus", refreshHistory);
    window.addEventListener(READING_HISTORY_EVENT, refreshHistory);
    return () => {
      disposed = true;
      window.removeEventListener("storage", refreshHistory);
      window.removeEventListener("focus", refreshHistory);
      window.removeEventListener(READING_HISTORY_EVENT, refreshHistory);
    };
  }, []);

  const activeQueryRef = useRef("");
  const localCountRef = useRef(0);

  const loadIngested = useCallback(async (quiet = false) => {
    if (!quiet) setLoadingIngested(true);
    try {
      const res = await fetch(`${API_BASE}/v1/books`);
      const data = await res.json();
      setIngested(data.books || []);
    } catch (e) {
      console.error("Failed to load books:", e);
    } finally {
      if (!quiet) setLoadingIngested(false);
    }
  }, []);

  useEffect(() => {
    loadIngested();
    const iv = setInterval(() => loadIngested(true), 6000);
    return () => clearInterval(iv);
  }, [loadIngested]);

  const loadLocal = useCallback(
    async (reset: boolean, quiet = false) => {
      const queryKey = `${debouncedSearch}|${formatFilter}|${librarySort}`;
      activeQueryRef.current = queryKey;

      if (reset) {
        if (!quiet) setLoadingLocal(true);
      } else {
        setLoadingMore(true);
      }
      if (!quiet) setLocalError(null);

      try {
        const params = new URLSearchParams({
          skip: String(reset ? 0 : localCountRef.current),
          limit: String(LOCAL_PAGE_SIZE),
        });
        if (debouncedSearch) params.set("search", debouncedSearch);
        if (formatFilter !== "all") params.set("format", formatFilter);
        params.set("sort", librarySort);
        params.set("order", librarySort === "modified" ? "desc" : "asc");

        const res = await fetch(`${API_BASE}/v1/library/local?${params}`);
        if (!res.ok) {
          const err = await res.json().catch(() => ({ detail: "Failed" }));
          throw new Error(err.detail || `HTTP ${res.status}`);
        }

        const data = await res.json();

        if (activeQueryRef.current !== queryKey) return;

        setLocalTotal(data.total ?? 0);
        setCatalogTotal(data.catalog_total ?? data.total ?? 0);
        setDiscussionCapableTotal(data.discussion_capable_total ?? 0);
        setFormatCounts(data.format_counts ?? {});
        setIndexedAt(data.indexed_at ?? null);
        if (reset) {
          const next = data.books || [];
          localCountRef.current = next.length;
          setLocalBooks(next);
        } else {
          setLocalBooks((prev) => {
            const seen = new Set(prev.map((b: LocalBook) => b.path));
            const fresh = (data.books || []).filter((b: LocalBook) => !seen.has(b.path));
            const next = [...prev, ...fresh];
            localCountRef.current = next.length;
            return next;
          });
        }
      } catch (e) {
        console.error("Failed to load local books:", e);
        if (!quiet) {
          setLocalError(e instanceof Error ? e.message : "Failed to browse local library");
        }
      } finally {
        if (!quiet) setLoadingLocal(false);
        setLoadingMore(false);
      }
    },
    [debouncedSearch, formatFilter, librarySort]
  );

  useEffect(() => {
    loadLocal(true);
  }, [debouncedSearch, formatFilter, librarySort, loadLocal]);

  useEffect(() => {
    const mediaIds = localBooks
      .map((book) => book.id)
      .filter((mediaId) => !requestedDetailsRef.current.has(mediaId))
      .slice(0, 50);
    if (mediaIds.length === 0) return;
    mediaIds.forEach((mediaId) => requestedDetailsRef.current.add(mediaId));

    const controller = new AbortController();
    let finished = false;
    void fetch(`${API_BASE}/v1/library/local/details`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ media_ids: mediaIds }),
      signal: controller.signal,
    })
      .then(async (response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.json();
      })
      .then((payload) => {
        const publications = (payload.publications || []) as LocalPublicationDetails[];
        setLocalDetails((current) => {
          const next = { ...current };
          publications.forEach((publication) => {
            next[publication.id] = publication;
          });
          return next;
        });
        finished = true;
      })
      .catch((error) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        mediaIds.forEach((mediaId) => requestedDetailsRef.current.delete(mediaId));
        console.error("Publication details could not be loaded", error);
      });

    return () => {
      if (!finished) {
        controller.abort();
        mediaIds.forEach((mediaId) => requestedDetailsRef.current.delete(mediaId));
      }
    };
  }, [localBooks, localDetails]);

  useEffect(() => {
    const hasPendingDiscussionPrep = localBooks.some(
      (book) => book.ingest_status === "queued" || book.ingest_status === "processing"
    );
    if (!hasPendingDiscussionPrep) return;
    const interval = setInterval(() => loadLocal(true, true), 5000);
    return () => clearInterval(interval);
  }, [localBooks, loadLocal]);

  async function refreshCatalog() {
    setRefreshingCatalog(true);
    try {
      const res = await fetch(`${API_BASE}/v1/library/catalog/scans`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ kind: "all" }),
      });
      if (!res.ok) {
        const error = await res.json().catch(() => ({ detail: "Refresh failed" }));
        throw new Error(error.detail || "Refresh failed");
      }
      toast.message("Refreshing books and audiobooks in the background…");

      const deadline = Date.now() + 10 * 60 * 1000;
      let statuses: CatalogScanStatus[] = [];
      while (Date.now() < deadline) {
        await new Promise((resolve) => window.setTimeout(resolve, 1500));
        const statusResponse = await fetch(`${API_BASE}/v1/library/catalog/status`);
        if (!statusResponse.ok) throw new Error("Could not read catalog scan status");
        statuses = (await statusResponse.json()).catalogs || [];
        if (statuses.some((catalog) => catalog.status === "failed")) {
          const failure = statuses.find((catalog) => catalog.status === "failed");
          throw new Error(failure?.error || "Catalog scan failed");
        }
        if (!statuses.some((catalog) => ["queueing", "queued", "scanning"].includes(catalog.status))) {
          break;
        }
      }
      if (statuses.some((catalog) => ["queueing", "queued", "scanning"].includes(catalog.status))) {
        throw new Error("Catalog scan is still running; check again in a moment");
      }
      await loadLocal(true);
      const books = statuses.find((catalog) => catalog.kind === "books");
      toast.success(
        `Shelf refreshed — ${Number(books?.item_count || catalogTotal).toLocaleString()} readable files indexed`
      );
    } catch (error) {
      console.error("Catalog refresh failed:", error);
      toast.error(error instanceof Error ? error.message : "Could not refresh the local shelf");
    } finally {
      setRefreshingCatalog(false);
    }
  }

  async function handleUpload(file: File) {
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const res = await fetch(`${API_BASE}/v1/ingest`, { method: "POST", body: fd });
      if (res.ok) {
        toast.success(`"${file.name}" added to your shelf`);
        loadIngested();
      } else {
        const err = await res.text().catch(() => "Unknown error");
        console.error("Upload response:", res.status, err);
        toast.error(`Upload failed (${res.status}) — try a smaller file or different format`);
      }
    } catch (e) {
      console.error("Upload failed:", e);
      toast.error("Upload failed — check your connection");
    } finally {
      setUploading(false);
    }
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file && /\.(pdf|epub|txt|fb2|mobi|azw|azw3|prc)$/i.test(file.name)) {
      handleUpload(file);
    }
  }

  async function ingestLocal(path: string) {
    setIngesting((prev) => ({ ...prev, [path]: "ingesting" }));
    try {
      const res = await fetch(`${API_BASE}/v1/library/local/ingest`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ file_path: path }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Failed" }));
        throw new Error(err.detail || "Ingest failed");
      }
      const data = await res.json();
      setIngesting((prev) => ({ ...prev, [path]: data.status || "queued" }));
      setLocalBooks((prev) =>
        prev.map((b) =>
          b.path === path
            ? {
                ...b,
                book_id: data.book_id,
                ingest_status: data.status || "queued",
              }
            : b
        )
      );
      toast.success("AI reading room is being prepared in the background");
      loadIngested(true);
    } catch (e) {
      console.error("Local ingest failed:", e);
      setIngesting((prev) => ({ ...prev, [path]: "failed" }));
      toast.error("Failed to add book — try again");
    }
  }

  const filteredIngested = ingested.filter((b) => {
    if (!search) return true;
    const hay = [b.title, b.author, b.filename].filter(Boolean).join(" ").toLowerCase();
    return hay.includes(search.toLowerCase());
  });

  const readyBooks = filteredIngested.filter((b) => b.ingest_status === "completed");
  const pendingBooks = filteredIngested.filter((b) => b.ingest_status !== "completed");
  const hasMore = localBooks.length < localTotal;

  const recentDiscussions = readyBooks
    .filter((b) => b.session_count > 0 && b.last_session_at)
    .sort((a, b) => {
      const ta = a.last_session_at ? new Date(a.last_session_at).getTime() : 0;
      const tb = b.last_session_at ? new Date(b.last_session_at).getTime() : 0;
      return tb - ta;
    })
    .slice(0, 4);

  const freshBooks = readyBooks.filter((b) => b.session_count === 0);

  return (
    <div className="space-y-10">
      {readingHistory.length > 0 && (
        <section aria-labelledby="continue-reading-heading">
          <div className="mb-4 flex items-end justify-between gap-4">
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-[0.24em] text-primary/70">
                Your place is kept
              </p>
              <h3 id="continue-reading-heading" className="mt-1 flex items-center gap-2 text-xl font-semibold font-serif">
                <PlayCircle className="h-5 w-5 text-primary" /> Continue reading
              </h3>
            </div>
            <span className="hidden text-xs text-muted-foreground sm:block">
              Synced to your private local reader profile
            </span>
          </div>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
            {readingHistory.map((entry) => {
              const progress = Math.max(0, Math.min(1, entry.fraction));
              return (
                <button
                  key={entry.path}
                  type="button"
                  data-testid="reading-history-card"
                  className="group overflow-hidden rounded-2xl border border-white/10 bg-card/70 p-3 text-left transition-all hover:-translate-y-1 hover:border-primary/45 hover:shadow-glow"
                  onClick={() =>
                    onReadBook({
                      id: entry.media_id || "",
                      path: entry.path,
                      title_guess: entry.title,
                      author: entry.author,
                      extension: entry.extension,
                      reader_kind: entry.reader_kind,
                      can_discuss: entry.can_discuss,
                      book_id: entry.book_id,
                      ingest_status: entry.ingest_status,
                    })
                  }
                >
                  <BookCover
                    title={entry.title}
                    ext={entry.extension}
                    mediaId={entry.media_id}
                    large
                  />
                  <strong className="mt-3 block line-clamp-2 text-sm leading-5 group-hover:text-primary">
                    {entry.title}
                  </strong>
                  <span className="mt-1 block truncate text-[11px] text-muted-foreground">
                    {entry.author || entry.chapter || entry.extension.toUpperCase()}
                  </span>
                  <span className="mt-3 block h-1 overflow-hidden rounded-full bg-white/10">
                    <span
                      className="block h-full rounded-full bg-primary transition-[width]"
                      style={{ width: `${Math.max(2, progress * 100)}%` }}
                    />
                  </span>
                  <span className="mt-1.5 block text-[10px] font-medium uppercase tracking-wide text-primary/80">
                    {progress >= 0.995
                      ? "Revisit"
                      : progress > 0
                        ? `${Math.round(progress * 100)}% read`
                        : "Open again"}
                    {` · ${timeAgo(entry.updated_at)}`}
                  </span>
                </button>
              );
            })}
          </div>
        </section>
      )}

      {/* Search + compact upload */}
      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <Input
            placeholder={
              catalogTotal > 0
                ? `Search ${catalogTotal.toLocaleString()} books by title or folder...`
                : "Search your books..."
            }
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-10"
          />
        </div>
        <Button variant="outline" asChild>
          <Link href="/listen" className="gap-2">
            <Headphones className="h-4 w-4" /> Listen
          </Link>
        </Button>
        <label>
          <input
            type="file"
            accept=".pdf,.epub,.txt,.fb2,.mobi,.azw,.azw3,.prc"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) handleUpload(f);
            }}
            disabled={uploading}
          />
          <Button variant="outline" disabled={uploading} asChild className="cursor-pointer">
            <span className="gap-2">
              {uploading ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Upload className="w-4 h-4" />
              )}
              {uploading ? "Uploading..." : "Upload a book"}
            </span>
          </Button>
        </label>
      </div>

      {!loadingLocal && catalogTotal === 0 && (
        <Card
          glass
          className={cn(
            "relative overflow-hidden transition-all duration-300",
            dragOver
              ? "border-primary bg-primary/5 shadow-glow"
              : "border-dashed border-2 hover:border-primary/50"
          )}
          onDragOver={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={handleDrop}
        >
          <CardContent className="py-5 text-center">
            <div className="flex items-center justify-center gap-3">
              <div
                className={cn(
                  "w-10 h-10 rounded-xl flex items-center justify-center transition-all",
                  dragOver ? "bg-primary text-white scale-110" : "bg-secondary text-muted-foreground"
                )}
              >
                <Upload className="w-5 h-5" />
              </div>
              <div className="text-left">
                <p className="text-sm font-medium">
                  {uploading ? "Uploading..." : "Drop a book here to add it"}
                </p>
                <p className="text-xs text-muted-foreground">
                  PDF, EPUB, TXT, FB2, or DRM-free Kindle
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* ── READY TO DISCUSS (ingested books) ── */}
      {loadingIngested ? (
        <div className="text-center py-8">
          <Loader2 className="w-6 h-6 mx-auto animate-spin text-primary" />
          <p className="text-sm text-muted-foreground mt-2">Loading your shelf...</p>
        </div>
      ) : filteredIngested.length > 0 ? (
        <div className="space-y-8">
          {/* Continue Reading */}
          {recentDiscussions.length > 0 && (
            <div>
              <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
                <MessageCircle className="w-5 h-5 text-primary" />
                Recent discussions
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {recentDiscussions.map((book) => (
                  <Card
                    key={`continue-${book.id}`}
                    className="group relative overflow-hidden cursor-pointer transition-all duration-300 hover:-translate-y-1 hover:border-primary/50 hover:shadow-glow"
                    onClick={() => onSelectBook(book.id)}
                  >
                    <div
                      className={cn(
                        "absolute inset-0 bg-gradient-to-br opacity-30 group-hover:opacity-50 transition-opacity",
                        getBookGradient(book.title)
                      )}
                    />
                    <CardContent className="relative p-4 flex items-center gap-4">
                      <BookCover title={book.title} ext={book.file_type} />
                      <div className="flex-1 min-w-0">
                        <h4 className="font-semibold text-sm line-clamp-1 group-hover:text-primary transition-colors">
                          {book.title}
                        </h4>
                        {book.author && (
                          <p className="text-xs text-muted-foreground mt-0.5 line-clamp-1">{book.author}</p>
                        )}
                        <div className="flex items-center gap-2 mt-2 text-xs text-muted-foreground">
                          <span className="flex items-center gap-1">
                            <MessageCircle className="w-3 h-3" />
                            {book.session_count} {book.session_count === 1 ? "session" : "sessions"}
                          </span>
                          {book.last_session_at && (
                            <>
                              <span className="text-border">·</span>
                              <span>{timeAgo(book.last_session_at)}</span>
                            </>
                          )}
                          {book.has_audiobook && (
                            <>
                              <span className="text-border">·</span>
                              <span className="flex items-center gap-1">
                                <Headphones className="w-3 h-3" /> Audio
                              </span>
                            </>
                          )}
                        </div>
                      </div>
                      <ArrowRight className="w-4 h-4 text-primary opacity-0 group-hover:opacity-100 transition-opacity shrink-0" />
                    </CardContent>
                  </Card>
                ))}
              </div>
            </div>
          )}

          {/* Ready to Discuss (all books) */}
          <div>
          <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
            <Sparkles className="w-5 h-5 text-primary" />
            {freshBooks.length > 0 && recentDiscussions.length > 0 ? "Start Something New" : "Ready to Discuss"}
            <Badge variant="outline" className="ml-1">{freshBooks.length > 0 && recentDiscussions.length > 0 ? freshBooks.length : readyBooks.length}</Badge>
          </h3>

          {(freshBooks.length > 0 && recentDiscussions.length > 0 ? freshBooks : readyBooks).length > 0 && (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {(freshBooks.length > 0 && recentDiscussions.length > 0 ? freshBooks : readyBooks).map((book, i) => (
                <Card
                  key={book.id}
                  className={cn(
                    "group relative overflow-hidden cursor-pointer transition-all duration-300",
                    "hover:-translate-y-1 hover:border-primary/50 hover:shadow-glow"
                  )}
                  style={{ animationDelay: `${i * 40}ms` }}
                  onClick={() => onSelectBook(book.id)}
                >
                  <div
                    className={cn(
                      "absolute inset-0 bg-gradient-to-br opacity-40 group-hover:opacity-60 transition-opacity",
                      getBookGradient(book.title)
                    )}
                  />
                  <CardContent className="relative p-4">
                    <div className="flex items-start gap-3">
                      <BookCover title={book.title} ext={book.file_type} />
                      <div className="flex-1 min-w-0">
                        <h4 className="font-semibold text-sm line-clamp-2 group-hover:text-primary transition-colors">
                          {book.title}
                        </h4>
                        {book.author && (
                          <p className="text-xs text-muted-foreground mt-0.5 line-clamp-1">
                            {book.author}
                          </p>
                        )}
                        <div className="flex flex-wrap items-center gap-1.5 mt-2 text-xs text-muted-foreground">
                          <span className="uppercase font-medium px-1.5 py-0.5 rounded bg-secondary/50">
                            {book.file_type}
                          </span>
                          <span>{formatFileSize(book.file_size_bytes)}</span>
                          {book.total_chars && (
                            <>
                              <span className="text-border">·</span>
                              <span className="flex items-center gap-1">
                                <Clock className="w-3 h-3" />
                                {formatReadingTime(Math.max(1, Math.ceil(book.total_chars / 1000)))}
                              </span>
                            </>
                          )}
                          {book.section_count > 0 && (
                            <>
                              <span className="text-border">·</span>
                              <span>{book.section_count} sections</span>
                            </>
                          )}
                        </div>
                        <div className="mt-2 flex items-center gap-2">
                          {statusBadge(book.ingest_status)}
                          {book.session_count > 0 && (
                            <Badge variant="outline" className="gap-1 text-[10px]">
                              <MessageCircle className="w-2.5 h-2.5" />
                              {book.session_count} {book.session_count === 1 ? "session" : "sessions"}
                            </Badge>
                          )}
                          {book.has_audiobook && (
                            <Badge variant="outline" className="gap-1 text-[10px]">
                              <Headphones className="w-2.5 h-2.5" />
                              Audio
                            </Badge>
                          )}
                          <ArrowRight className="w-3.5 h-3.5 text-primary opacity-0 group-hover:opacity-100 transition-opacity" />
                        </div>
                      </div>
                    </div>
                  </CardContent>
                  <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-gradient-to-r from-transparent via-primary to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />
                </Card>
              ))}
            </div>
          )}

          {/* Pending/processing books */}
          {pendingBooks.length > 0 && (
            <div className="mt-4 space-y-2">
              <p className="text-xs text-muted-foreground font-medium uppercase tracking-wider">
                Processing
              </p>
              {pendingBooks.map((book) => (
                <Card key={book.id} className="opacity-70">
                  <CardContent className="p-3 flex items-center gap-3">
                    <BookCover title={book.title} ext={book.file_type} />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium truncate">{book.title}</p>
                      <p className="text-xs text-muted-foreground">
                        {formatFileSize(book.file_size_bytes)}
                      </p>
                    </div>
                    {statusBadge(book.ingest_status)}
                    {book.ingest_error && (
                      <p className="text-xs text-red-400 truncate max-w-[200px]">
                        {book.ingest_error}
                      </p>
                    )}
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
          </div>
        </div>
      ) : !search && !loadingLocal && localTotal === 0 ? (
        <div className="text-center py-10">
          <div className="mx-auto mb-4 w-16 h-16 rounded-2xl bg-secondary flex items-center justify-center">
            <Book className="w-8 h-8 text-muted-foreground/50" />
          </div>
          <p className="text-base font-medium mb-1 font-serif">The shelf is empty — every great room starts here.</p>
          <p className="text-sm text-muted-foreground mt-2 max-w-md mx-auto">
            Upload a book above, browse your local library below, or run the
            seed script to load five classic novels instantly:
          </p>
          <p className="mt-3 text-xs font-mono text-muted-foreground bg-secondary/50 inline-block px-3 py-1.5 rounded-lg">
            python scripts/seed_public_domain.py
          </p>
        </div>
      ) : null}

      {/* ── LOCAL LIBRARY ── */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <div>
            <h3 className="text-lg font-semibold flex items-center gap-2">
              <FolderOpen className="w-5 h-5 text-primary" />
              Your library
              {!loadingLocal && (
                <span className="text-sm font-normal text-muted-foreground">
                  {localTotal.toLocaleString()} shown
                </span>
              )}
            </h3>
            {!loadingLocal && catalogTotal > 0 && (
              <p className="mt-1 text-xs text-muted-foreground">
                {catalogTotal.toLocaleString()} readable here · {discussionCapableTotal.toLocaleString()} ready for AI preparation
                {indexedAt ? ` · indexed ${timeAgo(indexedAt)}` : ""}
              </p>
            )}
          </div>
          <Button
            variant="ghost"
            size="sm"
            className="gap-2 text-muted-foreground"
            onClick={refreshCatalog}
            disabled={refreshingCatalog}
            title="Rescan D:\\books for additions and removals"
          >
            <RefreshCw className={cn("w-3.5 h-3.5", refreshingCatalog && "animate-spin")} />
            {refreshingCatalog ? "Refreshing in background…" : "Refresh shelf"}
          </Button>
        </div>

        {/* Reader format filters */}
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap gap-2">
            {FORMAT_FILTERS.map((f) => (
              <Button
                key={f.value}
                variant={formatFilter === f.value ? "default" : "outline"}
                size="sm"
                onClick={() => setFormatFilter(f.value)}
                className={formatFilter === f.value ? "shadow-glow" : ""}
              >
                {f.label}
                {f.value !== "all" && formatCounts[f.value] ? (
                  <span className="ml-1.5 text-[10px] opacity-65">
                    {formatCounts[f.value].toLocaleString()}
                  </span>
                ) : null}
              </Button>
            ))}
          </div>
          <label className="flex items-center gap-2 text-xs text-muted-foreground">
            Arrange
            <select
              aria-label="Arrange library"
              value={librarySort}
              onChange={(event) => setLibrarySort(event.target.value as LibrarySort)}
              className="h-8 rounded-lg border border-border bg-card px-2.5 text-xs text-foreground outline-none focus:ring-1 focus:ring-primary"
            >
              <option value="title">Title A–Z</option>
              <option value="modified">Recently added</option>
            </select>
          </label>
        </div>

        {localError ? (
          <Card className="border-red-500/30 bg-red-500/5">
            <CardContent className="py-6 text-center">
              <AlertCircle className="w-6 h-6 mx-auto text-red-400 mb-2" />
              <p className="text-sm text-red-400">{localError}</p>
              <Button
                variant="outline"
                size="sm"
                className="mt-3"
                onClick={() => loadLocal(true)}
              >
                Retry
              </Button>
            </CardContent>
          </Card>
        ) : loadingLocal ? (
          <div className="text-center py-8">
            <Loader2 className="w-6 h-6 mx-auto animate-spin text-primary" />
            <p className="text-sm text-muted-foreground mt-2">Opening your catalog…</p>
          </div>
        ) : localBooks.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            <FolderOpen className="w-8 h-8 mx-auto mb-2 opacity-50" />
            <p>{search ? "No matching books found" : "No books found in local library"}</p>
          </div>
        ) : (
          <>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
              {localBooks.map((book) => {
                const details = localDetails[book.id];
                const displayTitle = details?.title || book.title_guess;
                const readableBook = {
                  ...book,
                  title_guess: displayTitle,
                  author: details?.author,
                };
                const status = ingesting[book.path];
                const effectiveStatus = status || book.ingest_status;
                const isPreparing =
                  effectiveStatus === "ingesting" ||
                  effectiveStatus === "queued" ||
                  effectiveStatus === "processing";
                const isReady = effectiveStatus === "completed";
                const hasFailed = effectiveStatus === "failed";

                return (
                  <Card
                    key={book.id}
                    data-testid="local-book-card"
                    data-media-id={book.id}
                    className="group relative cursor-pointer overflow-hidden transition-all duration-200 hover:-translate-y-0.5 hover:border-primary/50 hover:shadow-glow"
                    onClick={() => onReadBook(readableBook)}
                  >
                    <CardContent className="p-3 flex items-center gap-3">
                      <BookCover
                        title={displayTitle}
                        ext={book.extension}
                        mediaId={details?.has_cover ? book.id : null}
                      />
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium truncate">{displayTitle}</p>
                        {(details?.author || book.parent_folder) && (
                          <p className="mt-0.5 truncate text-[11px] text-muted-foreground/70">
                            {details?.author || book.parent_folder}
                          </p>
                        )}
                        <div className="flex items-center gap-1.5 mt-1 text-xs text-muted-foreground">
                          <span className="uppercase font-medium px-1 py-0.5 rounded bg-secondary/50">
                            {book.extension}
                          </span>
                          <span>{formatFileSize(book.size_bytes)}</span>
                        </div>
                      </div>
                      <div className="shrink-0 flex flex-col items-end gap-1.5">
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-7 gap-1.5 px-2 text-xs text-primary"
                          onClick={(event) => {
                            event.stopPropagation();
                            onReadBook(readableBook);
                          }}
                        >
                          <Eye className="w-3.5 h-3.5" />
                          Read
                        </Button>
                        {isReady ? (
                          <Button
                            variant="outline"
                            size="sm"
                            className="h-7 gap-1 px-2 text-[11px]"
                            onClick={(event) => {
                              event.stopPropagation();
                              if (book.book_id) onSelectBook(book.book_id);
                            }}
                          >
                            <Sparkles className="w-3 h-3" /> Discuss
                          </Button>
                        ) : isPreparing ? (
                          <Badge variant="warning" className="gap-1">
                            <Loader2 className="w-3 h-3 animate-spin" /> Preparing AI
                          </Badge>
                        ) : hasFailed ? (
                          <Button
                            variant="outline"
                            size="sm"
                            className="h-7 gap-1 px-2 text-[11px] text-red-300"
                            title={book.ingest_error || "Retry AI preparation"}
                            onClick={(event) => {
                              event.stopPropagation();
                              ingestLocal(book.path);
                            }}
                          >
                            <RefreshCw className="h-3 w-3" /> Retry AI
                          </Button>
                        ) : book.can_discuss ? (
                          <Button
                            variant="outline"
                            size="sm"
                            className="h-7 gap-1 px-2 text-[11px] opacity-70 transition-opacity group-hover:opacity-100"
                            onClick={(e) => {
                              e.stopPropagation();
                              ingestLocal(book.path);
                            }}
                          >
                            <Plus className="w-3 h-3" />
                            Prepare AI
                          </Button>
                        ) : (
                          <span className="text-[10px] text-muted-foreground/60">read-only for now</span>
                        )}
                      </div>
                    </CardContent>
                    <div className="absolute inset-x-0 bottom-0 h-px bg-gradient-to-r from-transparent via-primary/70 to-transparent opacity-0 transition-opacity group-hover:opacity-100" />
                  </Card>
                );
              })}
            </div>

            {/* Load more */}
            {hasMore && (
              <div className="text-center mt-6">
                <Button
                  variant="outline"
                  onClick={() => loadLocal(false)}
                  disabled={loadingMore}
                  className="gap-2"
                >
                  {loadingMore ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" />
                      Loading...
                    </>
                  ) : (
                    <>
                      <ChevronDown className="w-4 h-4" />
                      Show more ({(localTotal - localBooks.length).toLocaleString()} remaining)
                    </>
                  )}
                </Button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
