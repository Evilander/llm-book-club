"use client";

import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from "react";
import { ChevronLeft, ChevronRight, Loader2, Minus, Plus } from "lucide-react";
import type { PDFDocumentProxy, RenderTask, TextLayer } from "pdfjs-dist";
import {
  findTextMatches,
  type ReaderInteractionHandle,
  type ReaderSelection,
} from "./reader-interactions";

interface PdfReaderProps {
  fileUrl: string;
  storageKey: string;
  onProgress: (fraction: number, pageLabel: string) => void;
  onSelection: (selection: ReaderSelection) => void;
  onLoadingChange: (loading: boolean) => void;
  onError: (message: string | null) => void;
}

export const PdfReader = forwardRef<ReaderInteractionHandle, PdfReaderProps>(
  function PdfReader(
    {
      fileUrl,
      storageKey,
      onProgress,
      onSelection,
      onLoadingChange,
      onError,
    },
    ref,
  ) {
  const hostRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const textLayerRef = useRef<HTMLDivElement>(null);
  const pdfRef = useRef<PDFDocumentProxy | null>(null);
  const renderTaskRef = useRef<RenderTask | null>(null);
  const textLayerTaskRef = useRef<TextLayer | null>(null);
  const pdfjsRef = useRef<typeof import("pdfjs-dist") | null>(null);
  const searchTokenRef = useRef(0);
  const callbacksRef = useRef({ onProgress, onSelection, onLoadingChange, onError });
  const [pageNumber, setPageNumber] = useState(1);
  const [pageCount, setPageCount] = useState(0);
  const [zoom, setZoom] = useState(1);
  const [rendering, setRendering] = useState(false);
  const [hostSize, setHostSize] = useState({ width: 0, height: 0 });
  const [activeSearchTerm, setActiveSearchTerm] = useState("");

  callbacksRef.current = { onProgress, onSelection, onLoadingChange, onError };

  useImperativeHandle(ref, () => ({
    clearSearch: () => {
      searchTokenRef.current += 1;
      setActiveSearchTerm("");
    },
    goToSearchResult: (searchResult) => {
      if (searchResult.target.kind !== "pdf") return;
      setActiveSearchTerm(searchResult.match);
      setPageNumber(searchResult.target.page);
    },
    goToTarget: (target) => {
      if (target.kind === "pdf") setPageNumber(target.page);
    },
    search: async (query, onProgress) => {
      const document = pdfRef.current;
      const trimmedQuery = query.trim();
      if (!document || !trimmedQuery) return [];
      const token = ++searchTokenRef.current;
      const searchResults = [];
      for (let page = 1; page <= document.numPages; page += 1) {
        if (token !== searchTokenRef.current) break;
        const pdfPage = await document.getPage(page);
        const content = await pdfPage.getTextContent();
        const pageText = content.items
          .map((textItem) => ("str" in textItem ? textItem.str : ""))
          .join(" ");
        for (const match of findTextMatches(
          pageText,
          trimmedQuery,
          250 - searchResults.length,
        )) {
          searchResults.push({
            id: `pdf-${page}-${match.start}`,
            label: `Page ${page}`,
            pre: match.pre,
            match: match.match,
            post: match.post,
            target: { kind: "pdf" as const, page },
          });
        }
        onProgress?.(page / document.numPages);
        if (searchResults.length >= 250) break;
      }
      return searchResults;
    },
  }), []);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    const observer = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect;
      setHostSize({ width, height });
    });
    observer.observe(host);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    let disposed = false;
    let loadingTask: ReturnType<typeof import("pdfjs-dist")["getDocument"]> | null = null;
    callbacksRef.current.onLoadingChange(true);
    callbacksRef.current.onError(null);

    async function loadDocument() {
      try {
        const pdfjs = await import("pdfjs-dist");
        pdfjs.GlobalWorkerOptions.workerSrc = new URL(
          "pdfjs-dist/build/pdf.worker.min.mjs",
          import.meta.url,
        ).toString();
        pdfjsRef.current = pdfjs;
        loadingTask = pdfjs.getDocument({
          url: fileUrl,
          withCredentials: false,
          isEvalSupported: false,
        });
        const document = await loadingTask.promise;
        if (disposed) {
          await document.destroy();
          return;
        }
        pdfRef.current = document;
        setPageCount(document.numPages);
        let savedPage = 1;
        try {
          const raw = window.localStorage.getItem(storageKey);
          const stored = raw ? (JSON.parse(raw) as { page?: number }) : null;
          if (stored?.page) savedPage = Math.min(document.numPages, Math.max(1, stored.page));
        } catch {
          // Start at page one when storage is unavailable.
        }
        setPageNumber(savedPage);
      } catch (caught) {
        console.error("PDF.js failed to open document", caught);
        callbacksRef.current.onError(
          caught instanceof Error ? caught.message : "This PDF could not be opened",
        );
        callbacksRef.current.onLoadingChange(false);
      }
    }

    void loadDocument();
    return () => {
      disposed = true;
      renderTaskRef.current?.cancel();
      textLayerTaskRef.current?.cancel();
      void loadingTask?.destroy();
      void pdfRef.current?.destroy();
      pdfRef.current = null;
      pdfjsRef.current = null;
    };
  }, [fileUrl, storageKey]);

  useEffect(() => {
    const document = pdfRef.current;
    const pdfjs = pdfjsRef.current;
    const canvas = canvasRef.current;
    const textLayerHost = textLayerRef.current;
    if (!document || !pdfjs || !canvas || !textLayerHost || !pageCount) return;
    if (hostSize.width < 100 || hostSize.height < 100) return;

    let disposed = false;
    async function renderPage() {
      setRendering(true);
      renderTaskRef.current?.cancel();
      textLayerTaskRef.current?.cancel();
      try {
        const page = await document!.getPage(pageNumber);
        if (disposed) return;
        const unscaled = page.getViewport({ scale: 1 });
        const availableWidth = Math.max(200, hostSize.width - 72);
        const availableHeight = Math.max(200, hostSize.height - 116);
        const fitScale = Math.min(
          availableWidth / unscaled.width,
          availableHeight / unscaled.height,
        );
        const viewport = page.getViewport({ scale: fitScale * zoom });
        const pixelRatio = Math.min(window.devicePixelRatio || 1, 2);
        canvas!.width = Math.floor(viewport.width * pixelRatio);
        canvas!.height = Math.floor(viewport.height * pixelRatio);
        canvas!.style.width = `${viewport.width}px`;
        canvas!.style.height = `${viewport.height}px`;
        textLayerHost!.style.width = `${viewport.width}px`;
        textLayerHost!.style.height = `${viewport.height}px`;
        textLayerHost!.replaceChildren();

        const context = canvas!.getContext("2d", { alpha: false });
        if (!context) throw new Error("Canvas rendering is unavailable");
        const renderTask = page.render({
          canvas: canvas!,
          canvasContext: context,
          viewport,
          transform: pixelRatio === 1 ? undefined : [pixelRatio, 0, 0, pixelRatio, 0, 0],
          background: "#ffffff",
        });
        renderTaskRef.current = renderTask;

        const textLayer = new pdfjs!.TextLayer({
          textContentSource: page.streamTextContent(),
          container: textLayerHost!,
          viewport,
        });
        textLayerTaskRef.current = textLayer;
        await Promise.all([renderTask.promise, textLayer.render()]);
        if (disposed) return;

        if (activeSearchTerm) {
          const needle = activeSearchTerm.toLocaleLowerCase();
          for (const span of textLayerHost!.querySelectorAll("span")) {
            if (span.textContent?.toLocaleLowerCase().includes(needle)) {
              span.classList.add("pdf-search-hit");
            }
          }
        }

        const fraction = pageCount <= 1 ? 1 : (pageNumber - 1) / (pageCount - 1);
        callbacksRef.current.onProgress(fraction, `Page ${pageNumber} of ${pageCount}`);
        callbacksRef.current.onLoadingChange(false);
        try {
          window.localStorage.setItem(
            storageKey,
            JSON.stringify({ page: pageNumber, fraction, updatedAt: new Date().toISOString() }),
          );
        } catch {
          // Reading must continue without persistence.
        }
      } catch (caught) {
        if (caught instanceof Error && caught.name === "RenderingCancelledException") return;
        console.error("PDF.js failed to render page", caught);
        callbacksRef.current.onError(
          caught instanceof Error ? caught.message : "This PDF page could not be rendered",
        );
        callbacksRef.current.onLoadingChange(false);
      } finally {
        if (!disposed) setRendering(false);
      }
    }

    void renderPage();
    return () => {
      disposed = true;
      renderTaskRef.current?.cancel();
      textLayerTaskRef.current?.cancel();
    };
  }, [activeSearchTerm, hostSize, pageCount, pageNumber, storageKey, zoom]);

  const movePage = useCallback((delta: number) => {
    setPageNumber((current) => Math.max(1, Math.min(pageCount || 1, current + delta)));
  }, [pageCount]);

  useEffect(() => {
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === "ArrowLeft" || event.key === "PageUp") movePage(-1);
      if (event.key === "ArrowRight" || event.key === "PageDown") movePage(1);
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [movePage]);

  return (
    <div
      ref={hostRef}
      className="pdf-reader-host"
      onMouseUp={() => {
        const selected = window.getSelection()?.toString().trim() || "";
        if (selected) {
          callbacksRef.current.onSelection({
            text: selected.slice(0, 2400),
            target: { kind: "pdf", page: pageNumber },
          });
        }
      }}
    >
      <div className="pdf-page-stage">
        <canvas ref={canvasRef} />
        <div ref={textLayerRef} className="pdf-text-layer textLayer" />
        {rendering && pageCount > 0 && (
          <div className="pdf-rendering-indicator"><Loader2 className="h-4 w-4 animate-spin" /></div>
        )}
      </div>

      {pageCount > 0 && (
        <div className="pdf-reader-controls">
          <button type="button" onClick={() => movePage(-1)} disabled={pageNumber <= 1} aria-label="Previous PDF page">
            <ChevronLeft className="h-5 w-5" />
          </button>
          <input
            type="range"
            min="1"
            max={pageCount}
            step="1"
            value={pageNumber}
            onChange={(event) => setPageNumber(Number(event.target.value))}
            aria-label="PDF page"
          />
          <span>{pageNumber} / {pageCount}</span>
          <button type="button" onClick={() => movePage(1)} disabled={pageNumber >= pageCount} aria-label="Next PDF page">
            <ChevronRight className="h-5 w-5" />
          </button>
          <div className="pdf-zoom-controls">
            <button type="button" onClick={() => setZoom((value) => Math.max(0.65, value - 0.15))} aria-label="Zoom out"><Minus className="h-3.5 w-3.5" /></button>
            <button type="button" onClick={() => setZoom((value) => Math.min(2.5, value + 0.15))} aria-label="Zoom in"><Plus className="h-3.5 w-3.5" /></button>
          </div>
        </div>
      )}
    </div>
  );
  },
);
