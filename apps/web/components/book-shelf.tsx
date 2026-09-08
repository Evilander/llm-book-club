"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type DragEvent,
} from "react";
import {
  ArrowRight,
  BookOpen,
  Plus,
  Loader2,
  Search,
  Upload,
} from "lucide-react";
import { toast } from "sonner";
import Link from "next/link";
import { Manicule } from "@/components/lamplight";
import { API_BASE, cn, formatFileSize } from "@/lib/utils";
import type {
  BinderyStatusResponse,
  LocalBook,
  LocalFolderEntry,
  LocalFolderLibraryResponse,
  LocalLibraryResponse,
} from "@/types/api";



import { BulkQueueDialog } from "@/components/bulk-queue-dialog";

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
  stage?: string | null;
  stage_started_at?: string | null;
  created_at: string;
  section_count: number;
  session_count: number;
  last_session_at: string | null;
  has_audiobook: boolean;
  reading_progress_pct?: number | null;
  current_unit_title?: string | null;
  units_completed?: number | null;
  total_units?: number | null;
  last_read_at?: string | null;
}

interface BookShelfProps {
  onSelectBook: (bookId: string) => void;
}

const LOCAL_PAGE_SIZE = 12;
const ROOT_FOLDER_FILTER = "__root__";

const COVER_COLORS = ["#65776a", "#8c705d", "#657780", "#96855f", "#777367", "#7b777f"];

function bookMatchesSearch(book: IngestedBook, query: string) {
  if (!query) return true;
  const haystack = [book.title, book.author, book.filename]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  return haystack.includes(query.toLowerCase());
}

function isApiFetchFailure(error: unknown) {
  return (
    error instanceof TypeError ||
    (error instanceof Error && /failed to fetch/i.test(error.message))
  );
}

function libraryErrorMessage(error: unknown) {
  if (isApiFetchFailure(error)) {
    return "The local library is unavailable. Please try again in a moment.";
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "Failed to browse local library.";
}

function selectFeaturedBook(books: IngestedBook[]) {
  return [...books]
    .filter(
      (book) =>
        (book.reading_progress_pct != null && book.reading_progress_pct > 0) ||
        Boolean(book.last_read_at || book.last_session_at)
    )
    .sort((left, right) => {
      const leftTime = left.last_read_at
        ? new Date(left.last_read_at).getTime()
        : left.last_session_at
          ? new Date(left.last_session_at).getTime()
          : 0;
      const rightTime = right.last_read_at
        ? new Date(right.last_read_at).getTime()
        : right.last_session_at
          ? new Date(right.last_session_at).getTime()
          : 0;
      return rightTime - leftTime;
    })[0];
}

/**
 * Render ingest errors as something a reader wants to see, not a SQL dump.
 * The bindery floor was leaking the full psycopg INSERT statement and
 * parameter bag into the UI. Map known failure modes to short prose; for
 * anything unrecognized, surface the first 90 chars only.
 */
function humanizeIngestError(raw: string | null | undefined): string {
  if (!raw) return "This book could not be prepared. Please try again.";
  const text = String(raw);
  if (/StringDataRightTruncation|value too long/.test(text)) {
    return "This book has an unusually long title or chapter heading. Please try preparing it again.";
  }
  if (/orphan(ed)?\b/i.test(text)) {
    return "Carried over from an earlier worker. A retry will pick it up cleanly.";
  }
  if (/timeout|timed out/i.test(text)) {
    return "The extractor stalled. Retry while the worker is fresh.";
  }
  if (/permission|denied|access/i.test(text)) {
    return "Couldn't open the source file. Check the file's permissions or path.";
  }
  if (/encoding|decode/i.test(text)) {
    return "The file's text encoding tripped the extractor. A retry sometimes recovers.";
  }
  // Strip SQLAlchemy/psycopg parenthetical prefix and trim aggressively.
  const cleaned = text
    .replace(/^\([^)]*\)\s*/, "")
    .replace(/\s+/g, " ")
    .trim();
  return cleaned.length > 90 ? cleaned.slice(0, 87) + "…" : cleaned;
}

function statusLabel(book: IngestedBook) {
  switch (book.ingest_status) {
    case "processing":
      return "Processing";
    case "queued":
      return "Queued";
    case "failed":
      return "Failed";
    default:
      return "Ready";
  }
}

function folderMatchesSearch(folder: LocalFolderEntry, query: string) {
  return !query || folder.name.toLowerCase().includes(query.toLowerCase());
}

function folderDisplayName(folder: string | null) {
  if (folder === ROOT_FOLDER_FILTER) {
    return "Loose books";
  }
  return folder || "Library";
}

export function BookShelf({ onSelectBook }: BookShelfProps) {
  const [ingested, setIngested] = useState<IngestedBook[]>([]);
  const [loadingIngested, setLoadingIngested] = useState(true);
  const [booksError, setBooksError] = useState<string | null>(null);
  const [visibleBooks, setVisibleBooks] = useState(12);
  const uploadRef = useRef<HTMLInputElement>(null);
  const [localFolders, setLocalFolders] = useState<LocalFolderEntry[]>([]);
  const [localRootCount, setLocalRootCount] = useState(0);
  const [localBooksDir, setLocalBooksDir] = useState<string | null>(null);
  const [loadingFolders, setLoadingFolders] = useState(true);
  const [localBooks, setLocalBooks] = useState<LocalBook[]>([]);
  const [localTotal, setLocalTotal] = useState(0);
  const [loadingLocal, setLoadingLocal] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [refreshingLocal, setRefreshingLocal] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);
  const [activeLocalFolder, setActiveLocalFolder] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [localSearch, setLocalSearch] = useState("");
  const [debouncedLocalSearch, setDebouncedLocalSearch] = useState("");
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  // ID of the volume the user just sent to the bindery — surface the binding
  // interstitial overlay for this book until it transitions to completed/failed.

  // Bulk-queue dialog state (only visible inside an active folder)
  const [bulkDialogOpen, setBulkDialogOpen] = useState(false);
  const [bulkRunning, setBulkRunning] = useState(false);
  const [ingesting, setIngesting] = useState<Record<string, string>>({});

  const [binderyPaused, setBinderyPaused] = useState(false);

  const localDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const activeQueryRef = useRef("");

  useEffect(() => {
    localDebounceRef.current = setTimeout(() => setDebouncedLocalSearch(localSearch.trim()), 250);
    return () => {
      if (localDebounceRef.current) {
        clearTimeout(localDebounceRef.current);
      }
    };
  }, [localSearch]);

  const loadIngested = useCallback(async (quiet = false) => {
    if (!quiet) {
      setLoadingIngested(true);
    }
    try {
      // Fetch a wide window so the bindery floor (in-flight books) and the
      // daylight shelf (completed books) are both populated from one call.
      // With the strategic seed in flight, the default page (50 newest) is
      // dominated by queued items and the shelf would render empty.
      const response = await fetch(`${API_BASE}/v1/books?limit=500`);
      if (!response.ok) {
        throw new Error(`Books request failed: ${response.status}`);
      }
      const data = (await response.json()) as { books?: IngestedBook[] };
      setIngested(data.books || []);
      setBooksError(null);
    } catch (error) {
      setBooksError("Your library could not be reached. Please try again in a moment.");
      if (!(error instanceof TypeError)) {
        console.error("Failed to load books:", error);
      }
    } finally {
      if (!quiet) {
        setLoadingIngested(false);
      }
    }
  }, []);

  const loadBinderyStatus = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE}/v1/library/bindery/status`);
      if (!response.ok) {
        throw new Error(`Bindery status request failed: ${response.status}`);
      }
      const data = (await response.json()) as BinderyStatusResponse;
      setBinderyPaused(data.paused);
    } catch (error) {
      if (!isApiFetchFailure(error)) {
        console.error("Failed to load bindery status:", error);
      }
    }
  }, []);

  const loadFolders = useCallback(async (refresh = false) => {
    setLoadingFolders(true);
    if (refresh) {
      setRefreshingLocal(true);
    }
    setLocalError(null);

    try {
      const params = new URLSearchParams();
      if (refresh) {
        params.set("refresh", "true");
      }
      const query = params.toString();
      const response = await fetch(`${API_BASE}/v1/library/local/folders${query ? `?${query}` : ""}`);
      if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: "Failed" }));
        throw new Error(error.detail || `HTTP ${response.status}`);
      }
      const data = (await response.json()) as LocalFolderLibraryResponse;
      setLocalFolders(data.folders || []);
      setLocalRootCount(data.root_book_count || 0);
      setLocalBooksDir(data.books_dir || null);
    } catch (error) {
      if (!isApiFetchFailure(error)) {
        console.error("Failed to load local folders:", error);
      }
      setLocalError(libraryErrorMessage(error));
      setLocalFolders([]);
      setLocalRootCount(0);
      setLocalBooksDir(null);
    } finally {
      setLoadingFolders(false);
      setRefreshingLocal(false);
    }
  }, []);

  const loadLocal = useCallback(
    async (reset: boolean, refresh = false, offset = 0) => {
      if (!activeLocalFolder) {
        setLocalBooks([]);
        setLocalTotal(0);
        setLoadingLocal(false);
        setLoadingMore(false);
        return;
      }

      const queryKey = `${activeLocalFolder}|${debouncedLocalSearch}`;
      activeQueryRef.current = queryKey;

      if (reset) {
        setLoadingLocal(true);
      } else {
        setLoadingMore(true);
      }
      if (refresh) {
        setRefreshingLocal(true);
      }
      setLocalError(null);

      try {
        const params = new URLSearchParams({
          skip: String(reset ? 0 : offset),
          limit: String(LOCAL_PAGE_SIZE),
          folder: activeLocalFolder,
        });
        if (debouncedLocalSearch) {
          params.set("search", debouncedLocalSearch);
        }
        if (refresh) {
          params.set("refresh", "true");
        }

        const response = await fetch(`${API_BASE}/v1/library/local?${params.toString()}`);
        if (!response.ok) {
          const error = await response.json().catch(() => ({ detail: "Failed" }));
          throw new Error(error.detail || `HTTP ${response.status}`);
        }
        const data = (await response.json()) as LocalLibraryResponse;
        if (activeQueryRef.current !== queryKey) {
          return;
        }

        setLocalTotal(data.total ?? 0);
        setLocalBooks((current) => {
          if (reset) {
            return data.books || [];
          }
          const seen = new Set(current.map((book) => book.path));
          const fresh = (data.books || []).filter((book) => !seen.has(book.path));
          return [...current, ...fresh];
        });
      } catch (error) {
        if (!isApiFetchFailure(error)) {
          console.error("Failed to load local books:", error);
        }
        setLocalError(libraryErrorMessage(error));
      } finally {
        setLoadingLocal(false);
        setLoadingMore(false);
        setRefreshingLocal(false);
      }
    },
    [activeLocalFolder, debouncedLocalSearch]
  );

  useEffect(() => {
    void loadIngested();
  }, [loadIngested]);

  useEffect(() => {
    void loadBinderyStatus();
  }, [loadBinderyStatus]);

  useEffect(() => {
    void loadFolders();
  }, [loadFolders]);

  useEffect(() => {
    if (activeLocalFolder) {
      void loadLocal(true);
      return;
    }
    setLocalBooks([]);
    setLocalTotal(0);
    setLoadingLocal(false);
  }, [activeLocalFolder, loadLocal]);

  useEffect(() => {
    if (!ingested.some((book) => book.ingest_status !== "completed")) {
      return;
    }
    const interval = setInterval(() => {
      void loadIngested(true);
      void loadBinderyStatus();
    }, 6000);
    return () => clearInterval(interval);
  }, [ingested, loadBinderyStatus, loadIngested]);

  async function handleUpload(file: File) {
    setUploading(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const response = await fetch(`${API_BASE}/v1/ingest`, {
        method: "POST",
        body: formData,
      });
      if (!response.ok) {
        const errorText = await response.text().catch(() => "Unknown error");
        throw new Error(errorText || `HTTP ${response.status}`);
      }
      toast.success(`"${file.name}" added to your shelf`);
      await loadIngested();
    } catch (error) {
      console.error("Upload failed:", error);
      toast.error("Upload failed - check the backend and try again.");
    } finally {
      setUploading(false);
    }
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragOver(false);
    const file = event.dataTransfer.files[0];
    if (file && /\.(pdf|epub|txt)$/i.test(file.name)) {
      void handleUpload(file);
    }
  }

  async function ingestLocal(path: string) {
    setIngesting((current) => ({ ...current, [path]: "ingesting" }));
    try {
      const response = await fetch(`${API_BASE}/v1/library/local/ingest`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ file_path: path }),
      });
      if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: "Failed" }));
        throw new Error(error.detail || "Ingest failed");
      }
      const data = (await response.json()) as { book_id: string };
      setIngesting((current) => ({ ...current, [path]: "done" }));
      setLocalBooks((current) =>
        current.map((book) =>
          book.path === path ? { ...book, already_ingested: true, book_id: data.book_id } : book
        )
      );
      toast.success("At the press. The binding has started.");
      await loadIngested(true);
    } catch (error) {
      console.error("Local ingest failed:", error);
      setIngesting((current) => ({ ...current, [path]: "failed" }));
      toast.error("Failed to add the book. Try again.");
    }
  }

  function openLocalFolder(folder: string) {
    setActiveLocalFolder(folder);
    setLocalSearch("");
    setDebouncedLocalSearch("");
    setLocalBooks([]);
    setLocalTotal(0);
  }

  async function confirmBulkIngest(limit: number) {
    if (!activeLocalFolder) return;
    setBulkRunning(true);
    try {
      const response = await fetch(`${API_BASE}/v1/library/local/ingest_folder`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          folder: activeLocalFolder,
          limit,
          include_already_ingested: false,
        }),
      });
      if (!response.ok) {
        const err = await response.json().catch(() => ({ detail: "Failed" }));
        throw new Error(err.detail || `HTTP ${response.status}`);
      }
      const data = await response.json();
      toast.success(
        `${data.queued_count} ${data.queued_count === 1 ? "volume" : "volumes"} on the press.`
      );
      setBulkDialogOpen(false);
      await loadIngested(true);
    } catch (error) {
      console.error("Bulk ingest failed:", error);
      const message = error instanceof Error ? error.message : "Failed";
      toast.error(`The bindery refused the batch: ${message}`);
      throw error;
    } finally {
      setBulkRunning(false);
    }
  }

  async function toggleBinderyPause() {
    const nextPaused = !binderyPaused;
    try {
      const response = await fetch(`${API_BASE}/v1/library/bindery/pause`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ paused: nextPaused }),
      });
      if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: "Failed" }));
        throw new Error(error.detail || `HTTP ${response.status}`);
      }
      const data = (await response.json()) as BinderyStatusResponse;
      setBinderyPaused(data.paused);
      toast.success(data.paused ? "The bindery is paused." : "The bindery is running again.");
    } catch (error) {
      console.error("Bindery pause toggle failed:", error);
      toast.error("Could not update the bindery.");
      await loadBinderyStatus();
    }
  }

  async function retryBook(bookId: string) {
    try {
      const response = await fetch(`${API_BASE}/v1/books/${bookId}/retry`, {
        method: "POST",
      });
      if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: "Failed" }));
        throw new Error(error.detail || `HTTP ${response.status}`);
      }
      toast.success("Back on the press.");
      await loadIngested(true);
      await loadBinderyStatus();
    } catch (error) {
      console.error("Retry failed:", error);
      toast.error("Could not retry that volume.");
    }
  }

  function returnToLocalFolders() {
    setActiveLocalFolder(null);
    setLocalSearch("");
    setDebouncedLocalSearch("");
    setLocalBooks([]);
    setLocalTotal(0);
  }

  async function refreshLocalLibrary() {
    await loadFolders(true);
    if (activeLocalFolder) {
      await loadLocal(true, true);
    }
  }

  const filteredIngested = useMemo(
    () => ingested.filter((book) => bookMatchesSearch(book, search)),
    [ingested, search]
  );
  const readyBooks = filteredIngested.filter((book) => book.ingest_status === "completed");
  const allReadyBooks = ingested.filter((book) => book.ingest_status === "completed");
  const pendingBooks = ingested.filter((book) => book.ingest_status !== "completed");
  const featuredBook = selectFeaturedBook(allReadyBooks) ?? allReadyBooks[0] ?? null;
  const shelfBooks = readyBooks.slice(0, visibleBooks);
  const filteredLocalFolders = useMemo(
    () => localFolders.filter((folder) => folderMatchesSearch(folder, debouncedLocalSearch)),
    [localFolders, debouncedLocalSearch]
  );
  const showRootFolder =
    localRootCount > 0 &&
    (!debouncedLocalSearch || "loose books".includes(debouncedLocalSearch.toLowerCase()));
  const nextLocalBook = activeLocalFolder
    ? localBooks.find((book) => !book.already_ingested) ?? null
    : null;
  const hasMoreLocal = Boolean(activeLocalFolder) && localBooks.length < localTotal;
  const localSearchPlaceholder = activeLocalFolder
    ? `Search ${folderDisplayName(activeLocalFolder)}...`
    : "Search library categories...";
  const activeFolderMeta = activeLocalFolder
    ? localFolders.find((folder) => folder.name === activeLocalFolder)
    : null;
  const activeFolderTotal = activeFolderMeta?.book_count ?? localTotal;
  const activeFolderAlreadyIngested = activeLocalFolder
    ? localBooks.filter((book) => book.already_ingested).length
    : 0;

  return (
    <div className="quiet-library">
      <input ref={uploadRef} type="file" accept=".pdf,.epub,.txt" className="sr-only" aria-label="Upload a book"
        disabled={uploading} onChange={(event) => { const file = event.target.files?.[0]; if (file) void handleUpload(file); event.target.value = ""; }} />
      <BulkQueueDialog open={bulkDialogOpen} onCancel={() => setBulkDialogOpen(false)} onConfirm={confirmBulkIngest}
        folderName={folderDisplayName(activeLocalFolder)} totalInFolder={activeFolderTotal} alreadyIngestedCount={activeFolderAlreadyIngested} />
      <div className="library-heading">
        <div><h2>Your library</h2><p>A familiar book. A fresh start. Pick up wherever you like.</p></div>
        <div className="library-tools">
          <label className="library-search"><Search size={16} aria-hidden="true" /><input aria-label="Search your books" placeholder="Find a book" value={search} onChange={(event) => { setSearch(event.target.value); setVisibleBooks(12); }} /></label>
          <button className="reading-button secondary" disabled={uploading} onClick={() => uploadRef.current?.click()}>{uploading ? <Loader2 size={15} className="animate-spin" /> : <Plus size={16} />} {uploading ? "Adding…" : "Add a book"}</button>
        </div>
      </div>
      {booksError ? (
        <div className="library-notice" role="alert"><p>{booksError}</p><button className="text-link" onClick={() => void loadIngested()}>Try again <ArrowRight size={14} /></button></div>
      ) : loadingIngested ? (
        <div className="library-empty" role="status"><Loader2 className="mx-auto animate-spin" size={20} /><p>Opening your library…</p></div>
      ) : (
        <>
          {!search && featuredBook && (featuredBook.last_read_at || featuredBook.last_session_at || (featuredBook.reading_progress_pct ?? 0) > 0) ? (
            <div className="library-continue">
              <BookOpen size={32} strokeWidth={1.2} aria-hidden="true" />
              <div className="continue-copy"><p className="quiet-eyebrow">Right where you left off</p><h3>{featuredBook.title}</h3><p>{featuredBook.current_unit_title || featuredBook.author || "Your next page is waiting"}{(featuredBook.reading_progress_pct ?? 0) > 0 ? ` · ${Math.round(featuredBook.reading_progress_pct!)}% read` : ""}</p></div>
              <button className="reading-button" onClick={() => onSelectBook(featuredBook.id)}>Continue reading <ArrowRight size={16} /></button>
            </div>
          ) : null}
          {shelfBooks.length ? (
            <div className="book-grid">{shelfBooks.map((book) => {
              const hash = Array.from(book.title).reduce((sum, letter) => sum + letter.charCodeAt(0), 0);
              return <article className="book-tile" key={book.id}>
                <button className="book-cover" style={{ "--cover-color": COVER_COLORS[hash % COVER_COLORS.length] } as React.CSSProperties} onClick={() => onSelectBook(book.id)} aria-label={`Read ${book.title}`}>
                  <span>{book.author || "Your collection"}</span><strong>{book.title}</strong><i aria-hidden="true" /><span>{book.file_type.toUpperCase()}</span>
                </button>
                <h3>{book.title}</h3><p>{book.author || "Unknown author"}</p>
                <div className="book-tile-actions"><Link href={`/books/${book.id}`} className="text-link">Book club <ArrowRight size={12} /></Link><span className="book-progress">{book.reading_progress_pct ? `${Math.round(book.reading_progress_pct)}% read` : "Ready to read"}</span></div>
              </article>;
            })}</div>
          ) : (
            <div className="library-empty"><BookOpen size={28} strokeWidth={1.2} className="mx-auto" aria-hidden="true" /><h3>{search ? "No books found" : "Every good conversation starts with a book."}</h3><p>{search ? "Try another title or author." : "Bring a PDF, EPUB, or text file. We’ll keep a place for you."}</p><button className="text-link" onClick={() => search ? setSearch("") : uploadRef.current?.click()} disabled={uploading}>{search ? "Clear search" : "Choose your first book"} <ArrowRight size={14} /></button></div>
          )}
          {readyBooks.length > visibleBooks ? <button className="text-link mt-8" onClick={() => setVisibleBooks((n) => n + 12)}>Show more books <ArrowRight size={14} /></button> : null}
        </>
      )}
      {pendingBooks.length ? <div className="library-pending" aria-label="Books being prepared">
        {pendingBooks.map((book) => <div key={book.id}><p>{book.title}<small>{book.ingest_status === "failed" ? humanizeIngestError(book.ingest_error) : "Preparing for reading. This will update automatically."}</small></p><span>{statusLabel(book)}</span>{book.ingest_status === "failed" ? <button className="text-link" onClick={() => void retryBook(book.id)}>Retry</button> : <Loader2 size={16} className="animate-spin" />}</div>)}
        <button className="text-link mt-3" onClick={() => void toggleBinderyPause()}>{binderyPaused ? "Resume preparation" : "Pause preparation"}</button>
      </div> : null}
      <details className="library-imports"><summary>Import from your device or local collection</summary>
      <section className="grid gap-6 xl:grid-cols-[0.9fr_1.1fr]">
        <div className="card-paper px-6 py-6 md:px-8">
          <div className="flex flex-col gap-3 border-b border-foxed/55 pb-4 md:flex-row md:items-end md:justify-between">
            <div>
              <p className="eyebrow text-foxed">Add a book</p>
              <h3 className="mt-2 font-serif text-4xl italic text-ink">Your books, here</h3>
            </div>
            <button
              type="button"
              onClick={() => void refreshLocalLibrary()}
              className="inline-flex items-center gap-2 text-[10px] uppercase tracking-[0.18em] text-foxed transition-colors font-label hover:text-ink disabled:opacity-50"
              disabled={refreshingLocal}
            >
              {refreshingLocal ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <span className="text-sm leading-none text-brass">§</span>
              )}
              Refresh local scan
            </button>
          </div>

          <div className="mt-5 space-y-5">
            <div
              className={cn(
                "rounded-[2px] border border-dashed px-5 py-5 transition-colors",
                dragOver
                  ? "border-brass bg-[rgba(196,154,74,0.1)]"
                  : "border-foxed/40 bg-[rgba(26,20,16,0.04)]"
              )}
              onDragOver={(event) => {
                event.preventDefault();
                setDragOver(true);
              }}
              onDragLeave={() => setDragOver(false)}
              onDrop={handleDrop}
            >
              <p className="text-[10px] uppercase tracking-[0.18em] text-foxed font-label">
                Upload directly
              </p>
              <p className="mt-3 font-serif text-3xl italic text-ink">
                Drop a PDF, EPUB, or text file here.
              </p>
              <p className="mt-3 text-sm leading-7 text-ink-pencil">
                Choose a file from your device, or browse your local collection. We’ll prepare it for reading and discussion.
              </p>
              <label className="mt-5 inline-block cursor-pointer">
                <input
                  type="file"
                  accept=".pdf,.epub,.txt"
                  className="sr-only"
                  onChange={(event) => {
                    const file = event.target.files?.[0];
                    if (file) {
                      void handleUpload(file);
                    }
                  }}
                  disabled={uploading}
                />
                <span className="btn inline-flex items-center gap-2">
                  {uploading ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Upload className="h-4 w-4" />
                  )}
                  {uploading ? "Uploading..." : "Choose a file"}
                </span>
              </label>
            </div>

            <div className="rounded-[2px] border border-foxed/35 bg-[rgba(26,20,16,0.04)] px-5 py-5">
              <p className="text-[10px] uppercase tracking-[0.18em] text-foxed font-label">
                Local catalogue
              </p>
              {nextLocalBook ? (
                <>
                  <p className="mt-3 font-serif text-3xl italic text-ink">
                    {nextLocalBook.title_guess}
                  </p>
                  <p className="mt-2 text-sm text-ink-pencil">
                    {`${nextLocalBook.extension.toUpperCase()} · ${formatFileSize(nextLocalBook.size_bytes)}`}
                  </p>
                  <button
                    type="button"
                    onClick={() => void ingestLocal(nextLocalBook.path)}
                    disabled={ingesting[nextLocalBook.path] === "ingesting"}
                    className="btn mt-5 inline-flex items-center gap-2"
                  >
                    {ingesting[nextLocalBook.path] === "ingesting" ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : null}
                    Add this book
                  </button>
                </>
              ) : (
                <p className="mt-3 text-sm leading-7 text-ink-pencil">
                  {loadingLocal
                    ? "Scanning the local library now."
                    : activeLocalFolder
                      ? "No un-ingested local volume is currently waiting in this category."
                      : "Choose a category before importing from the local library."}
                </p>
              )}
            </div>
          </div>
        </div>

        <div className="card-paper px-6 py-6 md:px-8">
          <div className="flex flex-col gap-3 border-b border-foxed/55 pb-4 md:flex-row md:items-end md:justify-between">
            <div>
              <p className="eyebrow text-foxed">Local library</p>
              <h3 className="mt-2 font-serif text-4xl italic text-ink">
                {activeLocalFolder ? folderDisplayName(activeLocalFolder) : "Library categories"}
              </h3>
            </div>
            <p className="text-[10px] uppercase tracking-[0.18em] text-foxed font-label">
              {activeLocalFolder
                ? localTotal > 0
                  ? `${localBooks.length} of ${localTotal} shown`
                  : "Folder selected"
                : loadingFolders
                  ? "Counting categories"
                  : `${filteredLocalFolders.length + (showRootFolder ? 1 : 0)} of ${(localFolders.length + (localRootCount ? 1 : 0)).toLocaleString()} categories`}
            </p>
          </div>

          <label className="relative mt-5 block">
            <span className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-sm text-brass">
              §
            </span>
            <input
              value={localSearch}
              onChange={(event) => setLocalSearch(event.target.value)}
              placeholder={localSearchPlaceholder}
              className="w-full rounded-[2px] border border-foxed/35 bg-[rgba(26,20,16,0.05)] py-3 pl-11 pr-4 text-sm text-ink outline-none transition-colors placeholder:text-foxed/80 focus:border-brass"
            />
          </label>

          {activeLocalFolder && !localError ? (
            <div className="mt-5 flex flex-col gap-3 border-b border-foxed/35 pb-4 sm:flex-row sm:items-center sm:justify-between">
              <p className="text-[11px] uppercase tracking-[0.18em] text-foxed font-label">
                Library / <span className="text-ink">{folderDisplayName(activeLocalFolder)}</span>
              </p>
              <div className="flex flex-wrap items-center gap-4">
                {activeFolderTotal > 0 ? (
                  <button
                    type="button"
                    onClick={() => setBulkDialogOpen(true)}
                    disabled={bulkRunning}
                    className="inline-flex items-center gap-2 border-b border-brass/55 pb-1 text-[11px] uppercase tracking-[0.18em] text-ink transition-colors font-label hover:border-[var(--ink-sam)] hover:text-[var(--ink-sam)] disabled:opacity-50"
                  >
                    {bulkRunning ? "Adding books…" : "Import this folder"}
                    <Manicule className="h-4 w-4 text-brass" />
                  </button>
                ) : null}
                <button
                  type="button"
                  onClick={returnToLocalFolders}
                  className="self-start border-b border-foxed/45 pb-1 text-[11px] uppercase tracking-[0.18em] text-ink-pencil transition-colors font-label hover:border-brass hover:text-ink"
                >
                  Back to categories
                </button>
              </div>
            </div>
          ) : null}

          {localError ? (
            <div className="mt-5 rounded-[2px] border border-[rgba(91,26,42,0.35)] bg-[rgba(91,26,42,0.06)] px-4 py-4 text-sm leading-7 text-[var(--ink-sable)]">
              {localError}
            </div>
          ) : !activeLocalFolder ? (
            <>
              {loadingFolders ? (
                <div className="mt-8 text-center text-sm text-ink-pencil">
                  <Loader2 className="mx-auto mb-3 h-5 w-5 animate-spin text-brass" />
                  Counting local categories...
                </div>
              ) : filteredLocalFolders.length === 0 && !showRootFolder ? (
                <div className="mt-5 rounded-[2px] border border-foxed/35 bg-[rgba(26,20,16,0.04)] px-5 py-5 text-sm leading-7 text-ink-pencil">
                  {debouncedLocalSearch
                    ? "No library categories match that search."
                    : "No local books were found in the configured library directory."}
                </div>
              ) : (
                <div className="mt-5 grid gap-3">
                  {showRootFolder ? (
                    <button
                      type="button"
                      onClick={() => openLocalFolder(ROOT_FOLDER_FILTER)}
                      className="group rounded-[2px] border border-foxed/35 bg-[rgba(26,20,16,0.04)] px-4 py-4 text-left transition-colors hover:border-brass hover:bg-[rgba(196,154,74,0.07)]"
                    >
                      <div className="flex items-start justify-between gap-4">
                        <div className="min-w-0">
                          <p className="text-[10px] uppercase tracking-[0.18em] text-foxed font-label">
                            Library category
                          </p>
                          <p className="mt-2 font-serif text-3xl italic leading-tight text-ink transition-colors group-hover:text-[var(--ink-sam)]">
                            Loose books
                          </p>
                        </div>
                        <div className="shrink-0 text-right">
                          <p className="font-serif text-3xl italic leading-none text-brass">
                            {localRootCount.toLocaleString()}
                          </p>
                          <p className="mt-1 text-[10px] uppercase tracking-[0.16em] text-foxed font-label">
                            books
                          </p>
                        </div>
                      </div>
                      <p className="mt-3 text-sm leading-6 text-ink-pencil">
                        Files directly inside {localBooksDir || "BOOKS_DIR"}.
                      </p>
                    </button>
                  ) : null}

                  {filteredLocalFolders.map((folder) => (
                    <button
                      key={folder.name}
                      type="button"
                      onClick={() => openLocalFolder(folder.name)}
                      className="group rounded-[2px] border border-foxed/35 bg-[rgba(26,20,16,0.04)] px-4 py-4 text-left transition-colors hover:border-brass hover:bg-[rgba(196,154,74,0.07)]"
                    >
                      <div className="flex items-start justify-between gap-4">
                        <div className="min-w-0">
                          <p className="text-[10px] uppercase tracking-[0.18em] text-foxed font-label">
                            Library category
                          </p>
                          <p className="mt-2 font-serif text-3xl italic leading-tight text-ink transition-colors group-hover:text-[var(--ink-sam)]">
                            {folder.name}
                          </p>
                        </div>
                        <div className="shrink-0 text-right">
                          <p className="font-serif text-3xl italic leading-none text-brass">
                            {folder.book_count.toLocaleString()}
                          </p>
                          <p className="mt-1 text-[10px] uppercase tracking-[0.16em] text-foxed font-label">
                            books
                          </p>
                        </div>
                      </div>
                      {folder.sample_titles.length > 0 ? (
                        <p className="mt-3 line-clamp-2 text-sm leading-6 text-ink-pencil">
                          {folder.sample_titles.join(" / ")}
                        </p>
                      ) : null}
                      <p className="mt-3 text-[10px] uppercase tracking-[0.16em] text-foxed font-label">
                        {folder.audiobook_count.toLocaleString()} audio file{folder.audiobook_count === 1 ? "" : "s"}
                      </p>
                    </button>
                  ))}
                </div>
              )}
            </>
          ) : loadingLocal ? (
            <div className="mt-8 text-center text-sm text-ink-pencil">
              <Loader2 className="mx-auto mb-3 h-5 w-5 animate-spin text-brass" />
              Loading local volumes...
            </div>
          ) : localBooks.length === 0 ? (
            <div className="mt-5 rounded-[2px] border border-foxed/35 bg-[rgba(26,20,16,0.04)] px-5 py-5 text-sm leading-7 text-ink-pencil">
              {debouncedLocalSearch
                ? "No local files in this category match that search."
                : "No local books were found in this category."}
            </div>
          ) : (
            <>
              <div className="mt-5 space-y-3">
                {localBooks.map((book) => {
                  const ready = book.already_ingested && book.book_id;
                  const ingestState = ingesting[book.path];
                  return (
                    <div
                      key={book.path}
                      className="flex flex-col gap-4 rounded-[2px] border border-foxed/35 bg-[rgba(26,20,16,0.04)] px-4 py-4 md:flex-row md:items-center md:justify-between"
                    >
                      <div className="min-w-0 flex-1">
                        <p className="font-serif text-2xl italic leading-tight text-ink">
                          {book.title_guess}
                        </p>
                        <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] uppercase tracking-[0.16em] text-ink-pencil font-label">
                          <span>{book.extension.toUpperCase()}</span>
                          <span>{formatFileSize(book.size_bytes)}</span>
                          <span className="truncate">{book.filename}</span>
                        </div>
                      </div>

                      <div className="flex flex-wrap items-center gap-3">
                        {ready ? (
                          <button
                            type="button"
                            onClick={() => onSelectBook(book.book_id as string)}
                            className="border-b border-foxed/45 pb-1 text-[11px] uppercase tracking-[0.18em] text-ink-pencil transition-colors font-label hover:border-[var(--ink-sam)] hover:text-[var(--ink-sam)]"
                          >
                            Read book
                          </button>
                        ) : (
                          <button
                            type="button"
                            onClick={() => void ingestLocal(book.path)}
                            disabled={ingestState === "ingesting"}
                            className="btn"
                          >
                            {ingestState === "ingesting" ? "Adding..." : "Add to shelf"}
                          </button>
                        )}

                        <div className="text-[10px] uppercase tracking-[0.18em] text-foxed font-label">
                          {ready ? "In your library" : "Local file"}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>

              {hasMoreLocal ? (
                <div className="mt-5 flex justify-center">
                  <button
                    type="button"
                    onClick={() => void loadLocal(false, false, localBooks.length)}
                    disabled={loadingMore}
                    className="btn inline-flex items-center gap-2"
                  >
                    {loadingMore ? "Loading more..." : "Load more"}
                  </button>
                </div>
              ) : null}
            </>
          )}
        </div>
      </section>
      </details>
    </div>
  );
}
