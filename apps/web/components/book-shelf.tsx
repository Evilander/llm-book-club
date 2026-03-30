"use client";

import { useState, useEffect, useCallback, useRef } from "react";
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
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { API_BASE, cn, formatFileSize, formatReadingTime } from "@/lib/utils";

// ── Types ──────────────────────────────────────

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
  path: string;
  filename: string;
  extension: string;
  size_bytes: number;
  title_guess: string;
  already_ingested: boolean;
  book_id: string | null;
}

interface BookShelfProps {
  onSelectBook: (bookId: string) => void;
}

type ExtFilter = "all" | "pdf" | "epub" | "txt";

const LOCAL_PAGE_SIZE = 24;

const EXT_FILTERS: { label: string; value: ExtFilter }[] = [
  { label: "All", value: "all" },
  { label: "PDF", value: "pdf" },
  { label: "EPUB", value: "epub" },
  { label: "TXT", value: "txt" },
];

// ── Helpers ────────────────────────────────────

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

// Mini book cover with gradient spine
function BookCover({ title, ext }: { title: string; ext: string }) {
  return (
    <div
      className={cn(
        "relative shrink-0 w-14 h-20 rounded-lg overflow-hidden border border-white/10 bg-gradient-to-br shadow-md",
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
    </div>
  );
}

// ── Main component ─────────────────────────────

export function BookShelf({ onSelectBook }: BookShelfProps) {
  // Ingested books
  const [ingested, setIngested] = useState<IngestedBook[]>([]);
  const [loadingIngested, setLoadingIngested] = useState(true);

  // Local books
  const [localBooks, setLocalBooks] = useState<LocalBook[]>([]);
  const [localTotal, setLocalTotal] = useState(0);
  const [loadingLocal, setLoadingLocal] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);

  // Search / filter
  const [search, setSearch] = useState("");
  const [extFilter, setExtFilter] = useState<ExtFilter>("all");

  // Upload
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);

  // Track ingest-in-progress for local books (path -> status)
  const [ingesting, setIngesting] = useState<Record<string, string>>({});

  // Debounced search
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(undefined);

  useEffect(() => {
    debounceRef.current = setTimeout(() => setDebouncedSearch(search), 300);
    return () => clearTimeout(debounceRef.current);
  }, [search]);

  // Stale query guard for local fetches
  const activeQueryRef = useRef("");

  // ── Fetch ingested books ──

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

  // ── Fetch local books (paginated) ──

  const loadLocal = useCallback(
    async (reset: boolean) => {
      const queryKey = `${debouncedSearch}|${extFilter}`;
      activeQueryRef.current = queryKey;

      if (reset) {
        setLoadingLocal(true);
      } else {
        setLoadingMore(true);
      }
      setLocalError(null);

      try {
        const params = new URLSearchParams({
          skip: String(reset ? 0 : localBooks.length),
          limit: String(LOCAL_PAGE_SIZE),
        });
        if (debouncedSearch) params.set("search", debouncedSearch);
        if (extFilter !== "all") params.set("extension", extFilter);

        const res = await fetch(`${API_BASE}/v1/library/local?${params}`);
        if (!res.ok) {
          const err = await res.json().catch(() => ({ detail: "Failed" }));
          throw new Error(err.detail || `HTTP ${res.status}`);
        }

        const data = await res.json();

        // Drop stale responses
        if (activeQueryRef.current !== queryKey) return;

        setLocalTotal(data.total ?? 0);
        if (reset) {
          setLocalBooks(data.books || []);
        } else {
          setLocalBooks((prev) => {
            const seen = new Set(prev.map((b: LocalBook) => b.path));
            const fresh = (data.books || []).filter((b: LocalBook) => !seen.has(b.path));
            return [...prev, ...fresh];
          });
        }
      } catch (e) {
        console.error("Failed to load local books:", e);
        setLocalError(e instanceof Error ? e.message : "Failed to browse local library");
      } finally {
        setLoadingLocal(false);
        setLoadingMore(false);
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [debouncedSearch, extFilter]
  );

  useEffect(() => {
    loadLocal(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedSearch, extFilter]);

  // ── Upload handler ──

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
        toast.error("Upload failed — try again");
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
    if (file && /\.(pdf|epub|txt)$/i.test(file.name)) handleUpload(file);
  }

  // ── Ingest local book ──

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
      setIngesting((prev) => ({ ...prev, [path]: "done" }));
      setLocalBooks((prev) =>
        prev.map((b) =>
          b.path === path ? { ...b, already_ingested: true, book_id: data.book_id } : b
        )
      );
      toast.success("Book added — ready to discuss");
      loadIngested(true);
    } catch (e) {
      console.error("Local ingest failed:", e);
      setIngesting((prev) => ({ ...prev, [path]: "failed" }));
      toast.error("Failed to add book — try again");
    }
  }

  // ── Derived data ──

  const filteredIngested = ingested.filter((b) => {
    if (!search) return true;
    const hay = [b.title, b.author, b.filename].filter(Boolean).join(" ").toLowerCase();
    return hay.includes(search.toLowerCase());
  });

  const readyBooks = filteredIngested.filter((b) => b.ingest_status === "completed");
  const pendingBooks = filteredIngested.filter((b) => b.ingest_status !== "completed");
  const hasMore = localBooks.length < localTotal;
  const audioReadyBooks = readyBooks.filter((b) => b.has_audiobook).slice(0, 3);

  // "Continue Reading" — books with sessions, sorted by most recent session
  const continueReading = readyBooks
    .filter((b) => b.session_count > 0 && b.last_session_at)
    .sort((a, b) => {
      const ta = a.last_session_at ? new Date(a.last_session_at).getTime() : 0;
      const tb = b.last_session_at ? new Date(b.last_session_at).getTime() : 0;
      return tb - ta;
    })
    .slice(0, 4);

  // "Start Something New" — ready books with no sessions yet
  const freshBooks = readyBooks.filter((b) => b.session_count === 0);

  // ── Render ──

  return (
    <div className="space-y-10">
      <div className="grid gap-3 lg:grid-cols-3">
        <Card className="border-white/10 bg-black/20">
          <CardContent className="p-5">
            <p className="text-xs uppercase tracking-[0.24em] text-primary/70 font-label">
              Continue the heat
            </p>
            <p className="mt-2 text-lg font-semibold font-serif">
              {continueReading.length > 0
                ? `${continueReading.length} room${continueReading.length === 1 ? "" : "s"} already know your voice.`
                : "Start a fresh room and let the shelf surprise you."}
            </p>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">
              The best sessions feel like returning to an argument, a flirtation, or a line you still cannot stop turning over.
            </p>
          </CardContent>
        </Card>

        <Card className="border-white/10 bg-black/20">
          <CardContent className="p-5">
            <p className="text-xs uppercase tracking-[0.24em] text-primary/70 font-label">
              Good for audio
            </p>
            <p className="mt-2 text-lg font-semibold font-serif">
              {audioReadyBooks.length > 0
                ? `${audioReadyBooks.length} title${audioReadyBooks.length === 1 ? "" : "s"} already have a local audio pairing.`
                : "The shelf is ready even if tonight stays text-first."}
            </p>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">
              Conversational audio works best when you want the room to feel alive while you cook, walk, annotate, or pace.
            </p>
          </CardContent>
        </Card>

        <Card className="border-white/10 bg-black/20">
          <CardContent className="p-5">
            <p className="text-xs uppercase tracking-[0.24em] text-primary/70 font-label">
              Best use
            </p>
            <p className="mt-2 text-lg font-semibold font-serif">
              Pick a slice, choose a mood, and let the cast make you want one more chapter.
            </p>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">
              This works when you want reading to feel social, charged, and intellectually awake instead of dutiful.
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Search + compact upload */}
      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <Input
            placeholder="Search your books..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-10"
          />
        </div>
        <label>
          <input
            type="file"
            accept=".pdf,.epub,.txt"
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

      {/* Slim drop zone */}
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
              <p className="text-xs text-muted-foreground">PDF, EPUB, or TXT</p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* ── READY TO DISCUSS (ingested books) ── */}
      {loadingIngested ? (
        <div className="text-center py-8">
          <Loader2 className="w-6 h-6 mx-auto animate-spin text-primary" />
          <p className="text-sm text-muted-foreground mt-2">Loading your shelf...</p>
        </div>
      ) : filteredIngested.length > 0 ? (
        <div className="space-y-8">
          {/* Continue Reading */}
          {continueReading.length > 0 && (
            <div>
              <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
                <PlayCircle className="w-5 h-5 text-primary" />
                Continue Reading
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {continueReading.map((book) => (
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
            {freshBooks.length > 0 && continueReading.length > 0 ? "Start Something New" : "Ready to Discuss"}
            <Badge variant="outline" className="ml-1">{freshBooks.length > 0 && continueReading.length > 0 ? freshBooks.length : readyBooks.length}</Badge>
          </h3>

          {(freshBooks.length > 0 && continueReading.length > 0 ? freshBooks : readyBooks).length > 0 && (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {(freshBooks.length > 0 && continueReading.length > 0 ? freshBooks : readyBooks).map((book, i) => (
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
      ) : !search ? (
        <div className="text-center py-10">
          <div className="mx-auto mb-4 w-16 h-16 rounded-2xl bg-secondary flex items-center justify-center">
            <Book className="w-8 h-8 text-muted-foreground/50" />
          </div>
          <p className="text-base font-medium mb-1">No books on your shelf yet</p>
          <p className="text-sm text-muted-foreground">
            Upload a book above or browse your local library below
          </p>
        </div>
      ) : null}

      {/* ── LOCAL LIBRARY ── */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold flex items-center gap-2">
            <FolderOpen className="w-5 h-5 text-primary" />
            Local Library
            {!loadingLocal && (
              <span className="text-sm font-normal text-muted-foreground">
                ({localTotal.toLocaleString()} books)
              </span>
            )}
          </h3>
        </div>

        {/* Extension filters */}
        <div className="flex flex-wrap gap-2 mb-4">
          {EXT_FILTERS.map((f) => (
            <Button
              key={f.value}
              variant={extFilter === f.value ? "default" : "outline"}
              size="sm"
              onClick={() => setExtFilter(f.value)}
              className={extFilter === f.value ? "shadow-glow" : ""}
            >
              {f.label}
            </Button>
          ))}
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
            <p className="text-sm text-muted-foreground mt-2">Scanning local library...</p>
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
                const status = ingesting[book.path];
                const isIngesting = status === "ingesting";
                const isReady = book.already_ingested || status === "done";

                return (
                  <Card
                    key={book.path}
                    className={cn(
                      "group relative overflow-hidden transition-all duration-200",
                      isReady
                        ? "cursor-pointer hover:-translate-y-0.5 hover:border-primary/50 hover:shadow-glow"
                        : "hover:border-border/80"
                    )}
                    onClick={() => {
                      if (isReady && book.book_id) onSelectBook(book.book_id);
                    }}
                  >
                    <CardContent className="p-3 flex items-center gap-3">
                      <BookCover title={book.title_guess} ext={book.extension} />
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium truncate">{book.title_guess}</p>
                        <div className="flex items-center gap-1.5 mt-1 text-xs text-muted-foreground">
                          <span className="uppercase font-medium px-1 py-0.5 rounded bg-secondary/50">
                            {book.extension}
                          </span>
                          <span>{formatFileSize(book.size_bytes)}</span>
                        </div>
                      </div>
                      <div className="shrink-0">
                        {isReady ? (
                          <Badge variant="success" className="gap-1">
                            <CheckCircle className="w-3 h-3" /> Ready
                          </Badge>
                        ) : isIngesting ? (
                          <Badge variant="warning" className="gap-1">
                            <Loader2 className="w-3 h-3 animate-spin" /> Adding...
                          </Badge>
                        ) : status === "failed" ? (
                          <Button
                            variant="outline"
                            size="sm"
                            className="text-red-400 border-red-500/30"
                            onClick={(e) => {
                              e.stopPropagation();
                              ingestLocal(book.path);
                            }}
                          >
                            Retry
                          </Button>
                        ) : (
                          <Button
                            variant="outline"
                            size="sm"
                            className="gap-1 opacity-0 group-hover:opacity-100 transition-opacity"
                            onClick={(e) => {
                              e.stopPropagation();
                              ingestLocal(book.path);
                            }}
                          >
                            <Plus className="w-3.5 h-3.5" />
                            Add
                          </Button>
                        )}
                      </div>
                    </CardContent>
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
