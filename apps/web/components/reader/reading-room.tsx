"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  AlertCircle,
  ArrowLeft,
  BookOpenText,
  Bookmark,
  BookmarkPlus,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Columns2,
  Cloud,
  CloudOff,
  Contrast,
  Download,
  Headphones,
  LibraryBig,
  ListTree,
  Loader2,
  MapPin,
  MessageCircle,
  Moon,
  PanelRightClose,
  PanelRightOpen,
  Quote,
  RefreshCw,
  Search,
  ScrollText,
  SlidersHorizontal,
  Sparkles,
  Sun,
  Trash2,
  X,
} from "lucide-react";
import { toast } from "sonner";
import { API_BASE, cn } from "@/lib/utils";
import {
  fetchAudiobookMatches,
  type AudiobookSummary,
} from "@/lib/audiobooks";
import { saveReadingHistory } from "@/lib/reading-history";
import {
  deleteReaderMark,
  fetchReaderSnapshot,
  mergeReaderMarks,
  persistReaderMark,
  persistReaderState,
  type ReaderMark,
  type ReaderPublicationDescriptor,
} from "@/lib/reader-sync";
import {
  saveDiscussionFocus,
  type DiscussionFocus,
} from "@/lib/discussion-focus";
import {
  FoliateReader,
  type FoliateReaderHandle,
  type ReaderLocation,
  type ReaderMetadata,
  type ReaderPreferences,
  type TocItem,
} from "./foliate-reader";
import { TextReader } from "./text-reader";
import { PdfReader } from "./pdf-reader";
import type {
  ReaderInteractionHandle,
  ReaderSearchResult,
  ReaderSelection,
  ReaderTarget,
} from "./reader-interactions";

type SyncStatus = "loading" | "saving" | "synced" | "offline";

const DEFAULT_PREFERENCES: ReaderPreferences = {
  theme: "paper",
  flow: "paginated",
  fontSize: 18,
  lineHeight: 1.72,
  maxWidth: 680,
};

function hashPath(path: string): string {
  let hash = 2166136261;
  for (let index = 0; index < path.length; index += 1) {
    hash ^= path.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0).toString(36);
}

function loadPreferences(): ReaderPreferences {
  if (typeof window === "undefined") return DEFAULT_PREFERENCES;
  try {
    const raw = window.localStorage.getItem("lbc-reader-preferences-v1");
    return raw
      ? { ...DEFAULT_PREFERENCES, ...(JSON.parse(raw) as Partial<ReaderPreferences>) }
      : DEFAULT_PREFERENCES;
  } catch {
    return DEFAULT_PREFERENCES;
  }
}

function loadPreferencesUpdatedAt(): string | null {
  if (typeof window === "undefined") return null;
  try {
    const stored = JSON.parse(
      window.localStorage.getItem("lbc-reader-preferences-v1") || "{}",
    ) as { updatedAt?: string };
    return stored.updatedAt || null;
  } catch {
    return null;
  }
}

function formatProgress(fraction: number): string {
  if (fraction <= 0) return "opening";
  if (fraction >= 0.999) return "finished";
  return `${Math.round(fraction * 100)}%`;
}

function loadPendingDeletions(storageKey: string): Set<string> {
  try {
    const stored = JSON.parse(window.localStorage.getItem(storageKey) || "[]");
    return new Set(Array.isArray(stored) ? stored.filter((id) => typeof id === "string") : []);
  } catch {
    return new Set();
  }
}

function savePendingDeletions(storageKey: string, ids: Set<string>): void {
  try {
    window.localStorage.setItem(storageKey, JSON.stringify([...ids]));
  } catch {
    // The active session still honors the deletion.
  }
}

export function ReadingRoom() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const path = searchParams.get("path") || "";
  const filename = path.split(/[\\/]/).pop() || "book";
  const format = (searchParams.get("format") || filename.split(".").pop() || "").toLowerCase();
  const renderer = searchParams.get("renderer") || (format === "pdf" ? "pdf" : format === "txt" ? "text" : "foliate");
  const readerKind: "foliate" | "pdf" | "text" =
    renderer === "pdf" ? "pdf" : renderer === "text" ? "text" : "foliate";
  const canDiscuss = searchParams.get("canDiscuss") === "true";
  const initialBookId = searchParams.get("bookId");
  const mediaId = searchParams.get("mediaId");
  const initialIngestStatus = searchParams.get("ingestStatus");
  const pathHash = useMemo(() => hashPath(path), [path]);
  const locationStorageKey = `lbc-reader-location-${pathHash}`;
  const notesStorageKey = `lbc-reader-notes-${pathHash}`;
  const pendingDeletionsStorageKey = `lbc-reader-deletions-${pathHash}`;
  const fileUrl = useMemo(() => {
    const query = new URLSearchParams({ file_path: path });
    return `${API_BASE}/v1/library/local/file?${query.toString()}`;
  }, [path]);

  const readerRef = useRef<FoliateReaderHandle>(null);
  const pdfReaderRef = useRef<ReaderInteractionHandle>(null);
  const textReaderRef = useRef<ReaderInteractionHandle>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const searchRequestRef = useRef(0);
  const preferencesUpdatedAtRef = useRef<string | null>(loadPreferencesUpdatedAt());
  const [title, setTitle] = useState(searchParams.get("title") || filename.replace(/\.[^.]+$/, ""));
  const [author, setAuthor] = useState<string | undefined>(
    searchParams.get("author") || undefined,
  );
  const [toc, setToc] = useState<TocItem[]>([]);
  const [location, setLocation] = useState<ReaderLocation>({ fraction: 0 });
  const [preferences, setPreferences] = useState<ReaderPreferences>(loadPreferences);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tocOpen, setTocOpen] = useState(false);
  const [preferencesOpen, setPreferencesOpen] = useState(false);
  const [marginOpen, setMarginOpen] = useState(true);
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchedQuery, setSearchedQuery] = useState("");
  const [searchResults, setSearchResults] = useState<ReaderSearchResult[]>([]);
  const [searchProgress, setSearchProgress] = useState(0);
  const [searching, setSearching] = useState(false);
  const [activeSearchResultId, setActiveSearchResultId] = useState<string | null>(null);
  const [selection, setSelection] = useState<ReaderSelection | null>(null);
  const [noteDraft, setNoteDraft] = useState("");
  const [notes, setNotes] = useState<ReaderMark[]>([]);
  const [bookId, setBookId] = useState<string | null>(initialBookId);
  const [ingestStatus, setIngestStatus] = useState<string | null>(initialIngestStatus);
  const [ingestError, setIngestError] = useState<string | null>(null);
  const [preparingDiscussion, setPreparingDiscussion] = useState(false);
  const [pendingFocus, setPendingFocus] = useState<DiscussionFocus | null>(null);
  const [stateHydrated, setStateHydrated] = useState(false);
  const [syncStatus, setSyncStatus] = useState<SyncStatus>("loading");
  const [syncedPublicationId, setSyncedPublicationId] = useState<string | null>(mediaId);
  const [audiobookMatch, setAudiobookMatch] = useState<AudiobookSummary | null>(null);

  const publication: ReaderPublicationDescriptor = {
    file_path: path,
    title,
    author,
    extension: format,
    reader_kind: readerKind,
    can_discuss: canDiscuss,
    book_id: bookId,
    ingest_status: ingestStatus,
  };
  const publicationRef = useRef(publication);
  publicationRef.current = publication;

  const foliateHighlights = useMemo(
    () => notes.flatMap((note) =>
      (note.kind === "highlight" || (!note.kind && Boolean(note.quote)))
        && note.target?.kind === "foliate"
        ? [note.target.cfi]
        : [],
    ),
    [notes],
  );

  useEffect(() => {
    if (!title.trim()) return;
    const controller = new AbortController();
    void fetchAudiobookMatches(title, author, controller.signal)
      .then((matches) => setAudiobookMatch(matches[0] || null))
      .catch((matchError) => {
        if (matchError instanceof DOMException && matchError.name === "AbortError") return;
        setAudiobookMatch(null);
      });
    return () => controller.abort();
  }, [author, title]);

  useEffect(() => {
    document.body.classList.add("reader-active");
    return () => document.body.classList.remove("reader-active");
  }, []);

  useEffect(() => {
    if (!searchOpen) return;
    const timeout = window.setTimeout(() => searchInputRef.current?.focus(), 50);
    return () => window.clearTimeout(timeout);
  }, [searchOpen]);

  useEffect(() => {
    const handleShortcut = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLocaleLowerCase() === "f") {
        event.preventDefault();
        setSearchOpen(true);
        setTocOpen(false);
        setPreferencesOpen(false);
      } else if (event.key === "Escape" && searchOpen) {
        closeSearch();
      }
    };
    window.addEventListener("keydown", handleShortcut);
    return () => window.removeEventListener("keydown", handleShortcut);
  }, [searchOpen]);

  useEffect(() => {
    try {
      window.localStorage.setItem(
        "lbc-reader-preferences-v1",
        JSON.stringify({
          ...preferences,
          updatedAt: preferencesUpdatedAtRef.current,
        }),
      );
    } catch {
      // Preferences are optional; reading is not.
    }
  }, [preferences]);

  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(notesStorageKey);
      setNotes(raw ? (JSON.parse(raw) as ReaderMark[]) : []);
    } catch {
      setNotes([]);
    }
  }, [notesStorageKey]);

  useEffect(() => {
    if (!path) {
      setStateHydrated(true);
      return;
    }

    let disposed = false;
    setStateHydrated(false);
    setSyncStatus("loading");
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 1800);
    const localMarks = (() => {
      try {
        const stored = JSON.parse(window.localStorage.getItem(notesStorageKey) || "[]");
        return Array.isArray(stored) ? (stored as ReaderMark[]) : [];
      } catch {
        return [];
      }
    })();
    const pendingDeletionIds = loadPendingDeletions(pendingDeletionsStorageKey);
    const localPreferences = loadPreferences();
    const localPreferencesUpdatedAt = loadPreferencesUpdatedAt();

    const hydrate = async () => {
      try {
        const snapshot = await fetchReaderSnapshot(path, controller.signal);
        if (disposed) return;
        setSyncedPublicationId(snapshot.publication_id);
        const localPreferencesAreNewer =
          Date.parse(localPreferencesUpdatedAt || "")
          > Date.parse(snapshot.preferences_updated_at);
        preferencesUpdatedAtRef.current = localPreferencesAreNewer
          ? localPreferencesUpdatedAt
          : snapshot.preferences_updated_at;
        setPreferences(
          localPreferencesAreNewer ? localPreferences : snapshot.preferences,
        );

        const merged = mergeReaderMarks(
          localMarks,
          snapshot.annotations,
          pendingDeletionIds,
        );
        setNotes(merged.marks);
        try {
          window.localStorage.setItem(notesStorageKey, JSON.stringify(merged.marks));
        } catch {
          // Server state remains authoritative when browser storage is unavailable.
        }

        if (snapshot.state) {
          const serverState = snapshot.state;
          if (serverState.title) setTitle(serverState.title);
          if (serverState.author) setAuthor(serverState.author);
          setBookId((current) => current || serverState.book_id);
          setIngestStatus((current) => current || serverState.ingest_status);

          let localUpdatedAt = 0;
          try {
            const localLocation = JSON.parse(
              window.localStorage.getItem(locationStorageKey) || "{}",
            ) as { updatedAt?: string };
            localUpdatedAt = Date.parse(localLocation.updatedAt || "") || 0;
          } catch {
            localUpdatedAt = 0;
          }
          if (Date.parse(serverState.updated_at) > localUpdatedAt) {
            const serverLocation = serverState.location;
            const fraction = Math.max(
              0,
              Math.min(1, serverLocation.fraction ?? serverState.fraction),
            );
            const cachedLocation = readerKind === "pdf"
              ? {
                  page: Number(serverLocation.page?.match(/Page (\d+)/)?.[1]) || 1,
                  fraction,
                  updatedAt: serverState.updated_at,
                }
              : readerKind === "foliate"
                ? {
                    cfi: serverLocation.cfi,
                    fraction,
                    updatedAt: serverState.updated_at,
                  }
                : { fraction, updatedAt: serverState.updated_at };
            try {
              window.localStorage.setItem(
                locationStorageKey,
                JSON.stringify(cachedLocation),
              );
            } catch {
              // The in-memory location still opens correctly for this session.
            }
            setLocation({
              fraction,
              cfi: serverLocation.cfi,
              chapter: serverLocation.chapter || serverState.chapter || undefined,
              page: serverLocation.page || serverState.page || undefined,
            });
          }
        }

        setStateHydrated(true);

        const syncTasks: Promise<void>[] = merged.localOnly.map((mark) =>
          persistReaderMark(publicationRef.current, mark),
        );
        for (const markId of pendingDeletionIds) {
          syncTasks.push(
            deleteReaderMark(path, markId).then(() => {
              pendingDeletionIds.delete(markId);
              savePendingDeletions(
                pendingDeletionsStorageKey,
                pendingDeletionIds,
              );
            }),
          );
        }
        if (syncTasks.length > 0) {
          setSyncStatus("saving");
          const outcomes = await Promise.allSettled(syncTasks);
          if (!disposed) {
            setSyncStatus(
              outcomes.some((outcome) => outcome.status === "rejected")
                ? "offline"
                : "synced",
            );
          }
        } else {
          setSyncStatus("synced");
        }
      } catch (syncError) {
        if (!disposed) {
          setNotes(localMarks);
          setSyncStatus("offline");
          if (!(syncError instanceof DOMException && syncError.name === "AbortError")) {
            console.warn("Reader profile is temporarily offline", syncError);
          }
        }
      } finally {
        window.clearTimeout(timeout);
        if (!disposed) setStateHydrated(true);
      }
    };

    void hydrate();
    return () => {
      disposed = true;
      controller.abort();
      window.clearTimeout(timeout);
    };
  }, [
    locationStorageKey,
    notesStorageKey,
    path,
    pendingDeletionsStorageKey,
    readerKind,
  ]);

  useEffect(() => {
    if (!path || loading || error) return;
    const timeout = window.setTimeout(() => {
      try {
        saveReadingHistory({
          id: pathHash,
          media_id: syncedPublicationId,
          path,
          title,
          author,
          extension: format,
          reader_kind: readerKind,
          can_discuss: canDiscuss,
          book_id: bookId,
          ingest_status: ingestStatus,
          fraction: Math.max(0, Math.min(1, location.fraction)),
          chapter: location.chapter || location.page,
          updated_at: new Date().toISOString(),
        });
      } catch {
        // Browser storage is an enhancement; the reader remains usable without it.
      }
    }, 250);
    return () => window.clearTimeout(timeout);
  }, [
    author,
    bookId,
    canDiscuss,
    error,
    format,
    ingestStatus,
    loading,
    location.chapter,
    location.fraction,
    location.page,
    path,
    pathHash,
    readerKind,
    syncedPublicationId,
    title,
  ]);

  useEffect(() => {
    if (!stateHydrated || !path || loading || error) return;
    setSyncStatus("saving");
    const timeout = window.setTimeout(() => {
      void persistCurrentProfile()
        .then(() => setSyncStatus("synced"))
        .catch(() => setSyncStatus("offline"));
    }, 900);
    return () => window.clearTimeout(timeout);
  }, [
    author,
    bookId,
    canDiscuss,
    error,
    format,
    ingestStatus,
    loading,
    location.cfi,
    location.chapter,
    location.fraction,
    location.page,
    path,
    preferences,
    readerKind,
    stateHydrated,
    title,
  ]);

  useEffect(() => {
    if (!bookId || !["queued", "processing"].includes(ingestStatus || "")) return;
    let disposed = false;
    const checkStatus = async () => {
      try {
        const response = await fetch(`${API_BASE}/v1/books/${bookId}`);
        if (!response.ok) return;
        const bookStatus = await response.json();
        if (!disposed) {
          setIngestStatus(bookStatus.ingest_status || null);
          setIngestError(bookStatus.ingest_error || null);
        }
      } catch {
        // Poll quietly; the primary reading experience remains local.
      }
    };
    const interval = window.setInterval(checkStatus, 5000);
    void checkStatus();
    return () => {
      disposed = true;
      window.clearInterval(interval);
    };
  }, [bookId, ingestStatus]);

  useEffect(() => {
    if (!pendingFocus || !bookId || ingestStatus !== "completed") return;
    saveDiscussionFocus(bookId, pendingFocus);
    setPendingFocus(null);
    router.push(`/books/${bookId}?from=reader&focus=1`);
  }, [bookId, ingestStatus, pendingFocus, router]);

  const handleMetadata = useCallback((metadata: ReaderMetadata) => {
    if (metadata.title) setTitle(metadata.title);
    if (metadata.author) setAuthor(metadata.author);
    setToc(metadata.toc);
  }, []);

  const handleLocation = useCallback((next: ReaderLocation) => setLocation(next), []);
  const handleSelection = useCallback((nextSelection: ReaderSelection) => {
    setSelection(nextSelection);
    setMarginOpen(true);
  }, []);
  const handleLoading = useCallback((isLoading: boolean) => setLoading(isLoading), []);
  const handleError = useCallback((message: string | null) => setError(message), []);

  function updatePreferences(
    updater: (current: ReaderPreferences) => ReaderPreferences,
  ) {
    preferencesUpdatedAtRef.current = new Date().toISOString();
    setPreferences(updater);
  }

  function activeReader(): ReaderInteractionHandle | null {
    if (renderer === "pdf") return pdfReaderRef.current;
    if (renderer === "text") return textReaderRef.current;
    return readerRef.current;
  }

  function currentTarget(): ReaderTarget | null {
    if (renderer === "foliate" && location.cfi) {
      return { kind: "foliate", cfi: location.cfi };
    }
    if (renderer === "pdf") {
      const page = Number(location.page?.match(/Page (\d+)/)?.[1]);
      if (Number.isFinite(page) && page > 0) return { kind: "pdf", page };
    }
    if (renderer === "text") {
      return { kind: "text", offset: 0, fraction: location.fraction };
    }
    return null;
  }

  function closeSearch() {
    searchRequestRef.current += 1;
    activeReader()?.clearSearch();
    setSearchOpen(false);
    setSearching(false);
    setSearchQuery("");
    setSearchedQuery("");
    setSearchResults([]);
    setActiveSearchResultId(null);
  }

  async function performSearch() {
    const query = searchQuery.trim();
    const reader = activeReader();
    if (!reader || query.length < 2) return;
    const requestId = ++searchRequestRef.current;
    setSearching(true);
    setSearchProgress(0);
    setSearchResults([]);
    setActiveSearchResultId(null);
    reader.clearSearch();
    try {
      const results = await reader.search(query, (fraction) => {
        if (searchRequestRef.current === requestId) setSearchProgress(fraction);
      });
      if (searchRequestRef.current !== requestId) return;
      setSearchResults(results);
      setSearchedQuery(query);
      setSearchProgress(1);
    } catch (caught) {
      console.error("Book search failed", caught);
      if (searchRequestRef.current === requestId) {
        toast.error("This edition could not be searched");
      }
    } finally {
      if (searchRequestRef.current === requestId) setSearching(false);
    }
  }

  function openSearchResult(searchResult: ReaderSearchResult) {
    setActiveSearchResultId(searchResult.id);
    activeReader()?.goToSearchResult(searchResult);
  }

  async function prepareDiscussion(announce = true): Promise<{
    book_id: string;
    status: string;
  } | null> {
    if (!canDiscuss || !path) return null;
    setPreparingDiscussion(true);
    try {
      const response = await fetch(`${API_BASE}/v1/library/local/ingest`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ file_path: path }),
      });
      if (!response.ok) {
        const detail = await response.json().catch(() => ({ detail: "Preparation failed" }));
        throw new Error(detail.detail || "Preparation failed");
      }
      const preparation = await response.json();
      setBookId(preparation.book_id);
      setIngestStatus(preparation.status || "queued");
      setIngestError(null);
      if (announce) {
        toast.success("Sam, Ellis, and Kit are reading ahead in the background");
      }
      return {
        book_id: preparation.book_id,
        status: preparation.status || "queued",
      };
    } catch (caught) {
      console.error("Discussion preparation failed", caught);
      toast.error(caught instanceof Error ? caught.message : "Could not prepare the AI room");
      return null;
    } finally {
      setPreparingDiscussion(false);
    }
  }

  async function discussSelection() {
    const quote = selection?.text.trim() || "";
    if (quote.length < 8) return;
    const focus: DiscussionFocus = {
      quote: quote.slice(0, 4000),
      question:
        noteDraft.trim().slice(0, 1000) ||
        "What do you notice in this passage that I might be missing?",
      chapter: location.chapter,
      page: location.page,
      fraction: location.fraction,
      created_at: new Date().toISOString(),
    };

    if (bookId) {
      saveDiscussionFocus(bookId, focus);
      if (ingestStatus === "completed") {
        router.push(`/books/${bookId}?from=reader&focus=1`);
        return;
      }
      setPendingFocus(focus);
      if (!["queued", "processing"].includes(ingestStatus || "")) {
        await prepareDiscussion(false);
      }
      toast.success("This passage will open when its evidence index is ready");
      return;
    }

    const preparation = await prepareDiscussion(false);
    if (!preparation) return;
    saveDiscussionFocus(preparation.book_id, focus);
    if (preparation.status === "completed") {
      router.push(`/books/${preparation.book_id}?from=reader&focus=1`);
    } else {
      setPendingFocus(focus);
      toast.success("This passage will open when its evidence index is ready");
    }
  }

  function openDiscussion() {
    if (!bookId) return;
    router.push(`/books/${bookId}?from=reader`);
  }

  function openAudiobook() {
    if (!audiobookMatch) return;
    const returnTo = `${window.location.pathname}${window.location.search}`;
    const query = new URLSearchParams({
      audioId: audiobookMatch.id,
      returnTo,
    });
    router.push(`/listen?${query}`);
  }

  function storeNotes(next: ReaderMark[], successMessage?: string) {
    setNotes(next);
    try {
      window.localStorage.setItem(notesStorageKey, JSON.stringify(next));
    } catch {
      toast.error("The offline copy could not be saved in this browser");
    }
    if (successMessage) toast.success(successMessage);
  }

  async function persistCurrentProfile() {
    const snapshot = await persistReaderState(
      publicationRef.current,
      {
        fraction: Math.max(0, Math.min(1, location.fraction)),
        cfi: location.cfi,
        chapter: location.chapter,
        page: location.page,
      },
      preferences,
    );
    setSyncedPublicationId(snapshot.publication_id);
    preferencesUpdatedAtRef.current = snapshot.preferences_updated_at;
  }

  function syncMark(mark: ReaderMark) {
    setSyncStatus("saving");
    void persistCurrentProfile()
      .then(() => persistReaderMark(publicationRef.current, mark))
      .then(() => setSyncStatus("synced"))
      .catch(() => setSyncStatus("offline"));
  }

  function saveNote() {
    const note = noteDraft.trim();
    if (!note && !selection) return;
    const target = selection?.target || currentTarget();
    const createdAt = new Date().toISOString();
    const savedNote: ReaderMark = {
      id: crypto.randomUUID(),
      kind: selection ? "highlight" : "note",
      quote: selection?.text || "",
      note,
      fraction: location.fraction,
      chapter: location.chapter,
      page: location.page,
      target: target || undefined,
      createdAt,
      updatedAt: createdAt,
    };
    const next = [savedNote, ...notes].slice(0, 500);
    storeNotes(
      next,
      selection ? "Highlighted and kept in the margin" : "Kept in the margin",
    );
    syncMark(savedNote);
    setNoteDraft("");
    setSelection(null);
  }

  function saveBookmark() {
    const target = currentTarget();
    if (!target) {
      toast.error("The reader is still finding this location");
      return;
    }
    const createdAt = new Date().toISOString();
    const bookmark: ReaderMark = {
      id: crypto.randomUUID(),
      kind: "bookmark",
      quote: "",
      note: "",
      fraction: location.fraction,
      chapter: location.chapter,
      page: location.page,
      target,
      createdAt,
      updatedAt: createdAt,
    };
    const next = [bookmark, ...notes].slice(0, 500);
    storeNotes(next, "Page marked");
    syncMark(bookmark);
  }

  function removeNote(id: string) {
    const next = notes.filter((note) => note.id !== id);
    storeNotes(next);
    const pendingDeletionIds = loadPendingDeletions(pendingDeletionsStorageKey);
    pendingDeletionIds.add(id);
    savePendingDeletions(pendingDeletionsStorageKey, pendingDeletionIds);
    setSyncStatus("saving");
    void persistCurrentProfile()
      .then(() => deleteReaderMark(path, id))
      .then(() => {
        pendingDeletionIds.delete(id);
        savePendingDeletions(pendingDeletionsStorageKey, pendingDeletionIds);
        setSyncStatus("synced");
      })
      .catch(() => setSyncStatus("offline"));
  }

  function goToNote(note: ReaderMark) {
    if (note.target) {
      activeReader()?.goToTarget(note.target);
    } else if (renderer === "foliate") {
      readerRef.current?.goToFraction(note.fraction);
    } else if (renderer === "pdf") {
      const page = Number(note.page?.match(/Page (\d+)/)?.[1]);
      if (Number.isFinite(page) && page > 0) {
        pdfReaderRef.current?.goToTarget({ kind: "pdf", page });
      }
    } else if (renderer === "text") {
      textReaderRef.current?.goToTarget({
        kind: "text",
        offset: 0,
        fraction: note.fraction,
      });
    }
  }

  function exportNotes() {
    if (notes.length === 0) return;
    const lines = [`# Notes on ${title}`, ""];
    if (author) lines.push(`*${author}*`, "");
    for (const note of [...notes].reverse()) {
      const place = note.chapter || note.page || `${Math.round(note.fraction * 100)}%`;
      lines.push(`## ${note.kind === "bookmark" ? "Bookmark" : "Mark"} · ${place}`, "");
      if (note.quote) lines.push(`> ${note.quote.replace(/\n/g, "\n> ")}`, "");
      if (note.note) lines.push(note.note, "");
    }
    const blob = new Blob([lines.join("\n")], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${title.replace(/[<>:"/\\|?*]+/g, "-").slice(0, 120)} - notes.md`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  if (!path) {
    return (
      <div className="reader-shell reader-empty-state">
        <LibraryBig className="h-10 w-10" />
        <h1>No book was chosen.</h1>
        <button type="button" onClick={() => router.push("/")}>Return to the shelf</button>
      </div>
    );
  }

  const isDiscussionReady = ingestStatus === "completed" && Boolean(bookId);
  const isDiscussionPending = ["queued", "processing"].includes(ingestStatus || "");

  return (
    <div className={cn("reader-shell", `reader-theme-${preferences.theme}`)}>
      <header className="reader-toolbar">
        <div className="reader-toolbar-left">
          <button className="reader-icon-button" type="button" onClick={() => router.push("/")} title="Back to your library">
            <ArrowLeft className="h-4 w-4" />
          </button>
          <div className="reader-title-block">
            <div className="reader-kicker">{format.toUpperCase()} · {location.page || formatProgress(location.fraction)}</div>
            <h1>{title}</h1>
            <p>{author || location.chapter || location.page || "Your private reading room"}</p>
          </div>
        </div>

        <div className="reader-toolbar-progress" aria-label={`${Math.round(location.fraction * 100)} percent read`}>
          <div style={{ width: `${location.fraction * 100}%` }} />
        </div>

        <div className="reader-toolbar-actions">
          <div
            className="reader-sync-status"
            data-status={syncStatus}
            data-testid="reader-sync-status"
            title={
              syncStatus === "offline"
                ? "Profile sync is offline; this browser still has your place"
                : syncStatus === "synced"
                  ? "Saved to your local reader profile"
                  : "Saving your reading profile"
            }
          >
            {syncStatus === "offline" ? (
              <CloudOff className="h-3.5 w-3.5" />
            ) : syncStatus === "synced" ? (
              <Cloud className="h-3.5 w-3.5" />
            ) : (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            )}
            <span>
              {syncStatus === "offline"
                ? "Offline copy"
                : syncStatus === "synced"
                  ? "Profile saved"
                  : "Saving"}
            </span>
          </div>
          {renderer === "foliate" && toc.length > 0 && (
            <button className={cn("reader-pill-button", tocOpen && "active")} type="button" onClick={() => {
              setTocOpen((value) => !value);
              if (searchOpen) closeSearch();
              setPreferencesOpen(false);
            }}>
              <ListTree className="h-3.5 w-3.5" /> Contents
            </button>
          )}
          <button
            className={cn("reader-pill-button", searchOpen && "active")}
            type="button"
            title="Find in this book (Ctrl+F)"
            onClick={() => {
              if (searchOpen) {
                closeSearch();
                return;
              }
              setSearchOpen(true);
              setTocOpen(false);
              setPreferencesOpen(false);
            }}
          >
            <Search className="h-3.5 w-3.5" /> Find
          </button>
          <button className="reader-pill-button" type="button" onClick={saveBookmark} title="Bookmark this place">
            <Bookmark className="h-3.5 w-3.5" /> Mark
          </button>
          {renderer !== "pdf" && (
            <button className={cn("reader-pill-button", preferencesOpen && "active")} type="button" onClick={() => {
              setPreferencesOpen((value) => !value);
              if (searchOpen) closeSearch();
              setTocOpen(false);
            }}>
              <SlidersHorizontal className="h-3.5 w-3.5" /> Type
            </button>
          )}
          <button className={cn("reader-pill-button", marginOpen && "active")} type="button" onClick={() => setMarginOpen((value) => !value)}>
            {marginOpen ? <PanelRightClose className="h-3.5 w-3.5" /> : <PanelRightOpen className="h-3.5 w-3.5" />}
            The margin
          </button>
        </div>
      </header>

      <div className="reader-workspace">
        {searchOpen && (
          <aside className="reader-search-panel" aria-label="Find in this book">
            <div className="reader-panel-heading">
              <div>
                <span>inside this book</span>
                <h2>Find a passage</h2>
              </div>
              <button type="button" onClick={closeSearch} aria-label="Close search"><X className="h-4 w-4" /></button>
            </div>
            <form
              className="reader-search-form"
              onSubmit={(event) => {
                event.preventDefault();
                void performSearch();
              }}
            >
              <Search className="h-4 w-4" />
              <input
                ref={searchInputRef}
                type="search"
                value={searchQuery}
                onChange={(event) => setSearchQuery(event.target.value)}
                placeholder="Name, phrase, or idea…"
                aria-label="Search text"
              />
              <button type="submit" disabled={searching || searchQuery.trim().length < 2}>
                {searching ? <Loader2 className="h-4 w-4 animate-spin" /> : "Find"}
              </button>
            </form>
            {searching && (
              <div className="reader-search-progress">
                <span style={{ width: `${Math.max(4, searchProgress * 100)}%` }} />
              </div>
            )}
            <div className="reader-search-summary" aria-live="polite">
              {searching
                ? `Searching ${Math.round(searchProgress * 100)}%…`
                : searchedQuery
                  ? `${searchResults.length}${searchResults.length === 250 ? "+" : ""} result${searchResults.length === 1 ? "" : "s"} for “${searchedQuery}”`
                  : "Press Enter to search the entire book."}
            </div>
            <div className="reader-search-results">
              {!searching && searchedQuery && searchResults.length === 0 && (
                <div className="reader-search-empty">No matching passage in this edition.</div>
              )}
              {searchResults.map((searchResult) => (
                <button
                  key={searchResult.id}
                  type="button"
                  className={activeSearchResultId === searchResult.id ? "active" : ""}
                  onClick={() => openSearchResult(searchResult)}
                >
                  <span>{searchResult.label}</span>
                  <p>{searchResult.pre} <mark>{searchResult.match}</mark> {searchResult.post}</p>
                </button>
              ))}
            </div>
          </aside>
        )}

        {tocOpen && renderer === "foliate" && (
          <aside className="reader-toc-panel">
            <div className="reader-panel-heading">
              <div>
                <span>the book</span>
                <h2>Contents</h2>
              </div>
              <button type="button" onClick={() => setTocOpen(false)}><X className="h-4 w-4" /></button>
            </div>
            <nav>
              {toc.map((item, index) => (
                <button
                  key={`${item.href}-${index}`}
                  type="button"
                  style={{ paddingLeft: `${16 + item.depth * 14}px` }}
                  onClick={() => {
                    readerRef.current?.goTo(item.href);
                    setTocOpen(false);
                  }}
                >
                  {item.label}
                </button>
              ))}
            </nav>
          </aside>
        )}

        {preferencesOpen && renderer !== "pdf" && (
          <div className="reader-preferences-panel">
            <div className="reader-panel-heading">
              <div>
                <span>make it yours</span>
                <h2>Reading shape</h2>
              </div>
              <button type="button" onClick={() => setPreferencesOpen(false)}><X className="h-4 w-4" /></button>
            </div>
            <div className="reader-setting-group">
              <label>Light</label>
              <div className="reader-choice-row">
                {([
                  ["paper", Sun, "Paper"],
                  ["night", Moon, "Night"],
                  ["contrast", Contrast, "High contrast"],
                ] as const).map(([value, Icon, label]) => (
                  <button key={value} type="button" className={preferences.theme === value ? "active" : ""} onClick={() => updatePreferences((current) => ({ ...current, theme: value }))}>
                    <Icon className="h-3.5 w-3.5" /> {label}
                  </button>
                ))}
              </div>
            </div>
            {renderer === "foliate" && (
              <div className="reader-setting-group">
                <label>Movement</label>
                <div className="reader-choice-row">
                  <button type="button" className={preferences.flow === "paginated" ? "active" : ""} onClick={() => updatePreferences((current) => ({ ...current, flow: "paginated" }))}>
                    <Columns2 className="h-3.5 w-3.5" /> Pages
                  </button>
                  <button type="button" className={preferences.flow === "scrolled" ? "active" : ""} onClick={() => updatePreferences((current) => ({ ...current, flow: "scrolled" }))}>
                    <ScrollText className="h-3.5 w-3.5" /> Scroll
                  </button>
                </div>
              </div>
            )}
            <label className="reader-range-setting">
              <span>Type size <strong>{preferences.fontSize}px</strong></span>
              <input type="range" min="14" max="26" step="1" value={preferences.fontSize} onChange={(event) => updatePreferences((current) => ({ ...current, fontSize: Number(event.target.value) }))} />
            </label>
            <label className="reader-range-setting">
              <span>Line space <strong>{preferences.lineHeight.toFixed(2)}</strong></span>
              <input type="range" min="1.35" max="2.1" step="0.05" value={preferences.lineHeight} onChange={(event) => updatePreferences((current) => ({ ...current, lineHeight: Number(event.target.value) }))} />
            </label>
            <label className="reader-range-setting">
              <span>Measure <strong>{preferences.maxWidth}px</strong></span>
              <input type="range" min="480" max="900" step="20" value={preferences.maxWidth} onChange={(event) => updatePreferences((current) => ({ ...current, maxWidth: Number(event.target.value) }))} />
            </label>
          </div>
        )}

        <main className="reader-canvas">
          <div className="reader-paper-edge" />
          {stateHydrated && (renderer === "pdf" ? (
            <PdfReader
              ref={pdfReaderRef}
              fileUrl={fileUrl}
              storageKey={locationStorageKey}
              onProgress={(fraction, pageLabel) =>
                setLocation((current) => ({ ...current, fraction, page: pageLabel }))
              }
              onSelection={handleSelection}
              onLoadingChange={handleLoading}
              onError={handleError}
            />
          ) : renderer === "text" ? (
            <TextReader
              ref={textReaderRef}
              fileUrl={fileUrl}
              storageKey={locationStorageKey}
              preferences={preferences}
              onProgress={(fraction) => setLocation((current) => ({ ...current, fraction }))}
              onSelection={handleSelection}
              onLoadingChange={handleLoading}
              onError={handleError}
            />
          ) : (
            <FoliateReader
              ref={readerRef}
              fileUrl={fileUrl}
              filename={filename}
              storageKey={locationStorageKey}
              preferences={preferences}
              highlights={foliateHighlights}
              onLocationChange={handleLocation}
              onMetadata={handleMetadata}
              onSelection={handleSelection}
              onLoadingChange={handleLoading}
              onError={handleError}
            />
          ))}

          {loading && (
            <div className="reader-loading-state">
              <BookOpenText className="h-8 w-8" />
              <div className="reader-loading-line"><span /></div>
              <p>Opening <em>{title}</em>…</p>
              {renderer === "foliate" && <small>Large books take a moment the first time.</small>}
            </div>
          )}
          {error && (
            <div className="reader-error-state">
              <AlertCircle className="h-8 w-8" />
              <h2>This volume would not open.</h2>
              <p>{error}</p>
              <button type="button" onClick={() => router.push("/")}>Return to the shelf</button>
            </div>
          )}

          {renderer === "foliate" && !loading && !error && (
            <div className="reader-page-controls">
              <button type="button" onClick={() => readerRef.current?.previous()} aria-label="Previous page"><ChevronLeft className="h-5 w-5" /></button>
              <input
                type="range"
                min="0"
                max="1"
                step="0.001"
                value={location.fraction}
                onChange={(event) => readerRef.current?.goToFraction(Number(event.target.value))}
                aria-label="Reading progress"
              />
              <span>{formatProgress(location.fraction)}</span>
              <button type="button" onClick={() => readerRef.current?.next()} aria-label="Next page"><ChevronRight className="h-5 w-5" /></button>
            </div>
          )}
        </main>

        {marginOpen && (
          <aside className="reader-margin-panel">
            <div className="reader-margin-intro">
              <span>the margin · yours + theirs</span>
              <h2>Stay with what catches.</h2>
              <p>Highlight a line to keep a thought, then open a grounded room when you want company.</p>
            </div>

            {selection ? (
              <div className="reader-selection-card">
                <Quote className="h-4 w-4" />
                <blockquote>{selection.text}</blockquote>
                <button type="button" onClick={() => setSelection(null)}><X className="h-3.5 w-3.5" /></button>
              </div>
            ) : (
              <div className="reader-selection-hint">Select a sentence in the book to lift it into the margin.</div>
            )}

            <div className="reader-note-composer">
              <textarea
                value={noteDraft}
                onChange={(event) => setNoteDraft(event.target.value)}
                placeholder={selection ? "What did you notice?" : "Leave yourself a thought…"}
                rows={3}
              />
              <button type="button" onClick={saveNote} disabled={!noteDraft.trim() && !selection}>
                <BookmarkPlus className="h-3.5 w-3.5" /> Keep in the margin
              </button>
              {canDiscuss && (
                <button
                  className="reader-discuss-selection"
                  type="button"
                  onClick={discussSelection}
                  disabled={(selection?.text.trim().length || 0) < 8 || preparingDiscussion || Boolean(pendingFocus)}
                >
                  {preparingDiscussion || pendingFocus ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <MessageCircle className="h-3.5 w-3.5" />
                  )}
                  {pendingFocus ? "Preparing this passage" : "Discuss this passage"}
                </button>
              )}
            </div>

            <div className="reader-room-card">
              {audiobookMatch && (
                <div className="reader-audio-companion" data-testid="reader-audiobook-match">
                  <div className="reader-agent-row">
                    <span className="sam"><Headphones className="h-3.5 w-3.5" /></span>
                    <p>
                      <strong>{audiobookMatch.title}</strong>
                      <small>
                        {audiobookMatch.track_count} {audiobookMatch.track_count === 1 ? "track" : "tracks"}
                        {audiobookMatch.match_reason ? ` · ${audiobookMatch.match_reason}` : ""}
                      </small>
                    </p>
                  </div>
                  <button className="reader-primary-action" type="button" onClick={openAudiobook}>
                    <Headphones className="h-4 w-4" /> Continue in the listening room
                  </button>
                </div>
              )}
              <div className="reader-agent-row" aria-label="Discussion cast">
                <span className="sam">S</span>
                <span className="ellis">E</span>
                <span className="kit">K</span>
                <p><strong>Sam, Ellis & Kit</strong><small>grounded discussion · citations on</small></p>
              </div>
              {isDiscussionReady ? (
                <button className="reader-primary-action" type="button" onClick={openDiscussion}>
                  <MessageCircle className="h-4 w-4" />
                  Open the discussion setup
                </button>
              ) : isDiscussionPending ? (
                <div className="reader-preparing-room">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  <div><strong>The cast is reading ahead.</strong><span>You can keep reading. This button will wake up when the evidence index is ready.</span></div>
                </div>
              ) : ingestStatus === "failed" ? (
                <>
                  <div className="reader-preparing-room failed">
                    <AlertCircle className="h-4 w-4" />
                    <div>
                      <strong>AI preparation failed.</strong>
                      <span>{ingestError || "The worker could not extract or index this edition."}</span>
                    </div>
                  </div>
                  <button className="reader-primary-action" type="button" onClick={() => void prepareDiscussion()} disabled={preparingDiscussion}>
                    {preparingDiscussion ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
                    Retry AI preparation
                  </button>
                </>
              ) : canDiscuss ? (
                <button className="reader-primary-action" type="button" onClick={() => void prepareDiscussion()} disabled={preparingDiscussion}>
                  {preparingDiscussion ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
                  Prepare the AI room
                </button>
              ) : (
                <div className="reader-preparing-room neutral">
                  <CheckCircle2 className="h-4 w-4" />
                  <div><strong>Reading works now.</strong><span>Grounded discussion for {format.toUpperCase()} is not wired yet; your position and notes are still saved.</span></div>
                </div>
              )}
            </div>

            {notes.length > 0 && (
              <div className="reader-saved-notes">
                <div className="reader-saved-notes-heading">
                  <span>Your marks</span>
                  <div>
                    <small>{notes.length}</small>
                    <button type="button" onClick={exportNotes} title="Export all marks as Markdown">
                      <Download className="h-3 w-3" /> Export
                    </button>
                  </div>
                </div>
                {notes.slice(0, 20).map((note) => (
                  <article key={note.id} className={note.kind === "bookmark" ? "bookmark" : ""}>
                    {note.kind === "bookmark" && <p className="reader-bookmark-label"><Bookmark className="h-3 w-3" /> Page marked</p>}
                    {note.quote && <blockquote>“{note.quote}”</blockquote>}
                    {note.note && <p>{note.note}</p>}
                    <footer>
                      <button type="button" className="reader-note-location" onClick={() => goToNote(note)} title="Go to this mark">
                        <MapPin className="h-3 w-3" /> {note.chapter || note.page || `${Math.round(note.fraction * 100)}%`}
                      </button>
                      <button type="button" onClick={() => removeNote(note.id)} title="Remove note"><Trash2 className="h-3 w-3" /></button>
                    </footer>
                  </article>
                ))}
              </div>
            )}
          </aside>
        )}
      </div>
    </div>
  );
}
