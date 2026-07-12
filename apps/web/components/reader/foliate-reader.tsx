"use client";

import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from "react";
import type {
  ReaderInteractionHandle,
  ReaderSearchResult,
  ReaderSelection,
  ReaderTarget,
} from "./reader-interactions";

export type ReaderTheme = "paper" | "night" | "contrast";
export type ReaderFlow = "paginated" | "scrolled";

export interface ReaderPreferences {
  theme: ReaderTheme;
  flow: ReaderFlow;
  fontSize: number;
  lineHeight: number;
  maxWidth: number;
}

export interface ReaderLocation {
  fraction: number;
  cfi?: string;
  chapter?: string;
  page?: string;
}

export interface ReaderMetadata {
  title?: string;
  author?: string;
  toc: TocItem[];
}

export interface TocItem {
  label: string;
  href: string;
  depth: number;
}

export interface FoliateReaderHandle extends ReaderInteractionHandle {
  previous: () => void;
  next: () => void;
  goTo: (target: string) => void;
  goToFraction: (fraction: number) => void;
}

interface FoliateReaderProps {
  fileUrl: string;
  filename: string;
  storageKey: string;
  preferences: ReaderPreferences;
  highlights: string[];
  onLocationChange: (location: ReaderLocation) => void;
  onMetadata: (metadata: ReaderMetadata) => void;
  onSelection: (selection: ReaderSelection) => void;
  onLoadingChange: (loading: boolean) => void;
  onError: (message: string | null) => void;
}

interface FoliateBook {
  metadata?: {
    title?: unknown;
    author?: unknown;
  };
  toc?: unknown[];
  transformTarget?: EventTarget;
}

interface FoliateRenderer extends HTMLElement {
  setStyles?: (css: string) => void;
  getContents?: () => Array<{ doc: Document; index: number }>;
}

interface FoliateView extends HTMLElement {
  book: FoliateBook;
  renderer: FoliateRenderer;
  open: (file: File | string) => Promise<void>;
  init: (options: { lastLocation?: string | null; showTextStart: boolean }) => Promise<void>;
  close: () => void;
  goLeft: () => Promise<void>;
  goRight: () => Promise<void>;
  goTo: (target: string) => Promise<unknown>;
  goToFraction: (fraction: number) => Promise<void>;
  getCFI: (index: number, range: Range) => string;
  search: (options: { query: string }) => AsyncGenerator<FoliateSearchEvent | string>;
  clearSearch: () => void;
  addAnnotation: (annotation: { value: string }) => Promise<unknown>;
  deleteAnnotation: (annotation: { value: string }) => Promise<unknown>;
}

interface FoliateSearchEvent {
  progress?: number;
  label?: string;
  subitems?: Array<{
    cfi: string;
    excerpt: { pre: string; match: string; post: string };
  }>;
}

interface PersistedLocation {
  cfi?: string;
  fraction: number;
  updatedAt: string;
}

const PUBLICATION_CSP = [
  "default-src 'none'",
  "img-src blob: data:",
  "style-src 'unsafe-inline' blob:",
  "font-src blob: data:",
  "media-src blob: data:",
  "object-src 'none'",
  "frame-src 'none'",
  "form-action 'none'",
  "base-uri 'none'",
].join("; ");

function firstLocalized(value: unknown): string | undefined {
  if (typeof value === "string") return value;
  if (Array.isArray(value)) {
    const values = value.map(firstLocalized).filter(Boolean) as string[];
    return values.join(", ") || undefined;
  }
  if (value && typeof value === "object") {
    const object = value as Record<string, unknown>;
    if ("name" in object) return firstLocalized(object.name);
    for (const item of Object.values(object)) {
      const formatted = firstLocalized(item);
      if (formatted) return formatted;
    }
  }
  return undefined;
}

function flattenToc(items: unknown[], depth = 0): TocItem[] {
  const output: TocItem[] = [];
  for (const rawItem of items) {
    if (!rawItem || typeof rawItem !== "object") continue;
    const item = rawItem as Record<string, unknown>;
    const label = firstLocalized(item.label) || "Untitled section";
    if (typeof item.href === "string") {
      output.push({ label, href: item.href, depth });
    }
    if (Array.isArray(item.subitems)) {
      output.push(...flattenToc(item.subitems, depth + 1));
    }
  }
  return output;
}

function readerCss(preferences: ReaderPreferences): string {
  const palette = {
    paper: { background: "#f2eadb", foreground: "#211a12", link: "#8c5a17" },
    night: { background: "#171312", foreground: "#ded5c7", link: "#d6a34f" },
    contrast: { background: "#ffffff", foreground: "#111111", link: "#7a3f00" },
  }[preferences.theme];

  return `
    @namespace epub "http://www.idpf.org/2007/ops";
    :root {
      color-scheme: ${preferences.theme === "night" ? "dark" : "light"};
      --theme-bg-color: ${palette.background};
      --theme-fg-color: ${palette.foreground};
    }
    html, body {
      background: ${palette.background} !important;
      color: ${palette.foreground} !important;
      font-family: "Literata", Georgia, serif !important;
      font-size: ${preferences.fontSize}px !important;
    }
    body { padding-inline: clamp(8px, 2vw, 28px) !important; }
    p, li, blockquote, dd {
      line-height: ${preferences.lineHeight} !important;
      text-rendering: optimizeLegibility;
      hanging-punctuation: first allow-end last;
      widows: 2;
      orphans: 2;
    }
    p { margin-block: 0 0.85em; }
    h1, h2, h3, h4 { line-height: 1.2 !important; text-wrap: balance; }
    a { color: ${palette.link} !important; }
    img, svg { max-inline-size: 100% !important; block-size: auto; }
    pre { white-space: pre-wrap !important; }
    ::selection { background: rgba(200, 134, 31, 0.32); }
  `;
}

function sanitizePublicationMarkup(data: unknown, type: string): unknown {
  if (typeof data !== "string") return data;
  if (!/(html|xhtml|svg\+xml)/i.test(type)) return data;

  const parserType = /svg/i.test(type)
    ? "image/svg+xml"
    : /xhtml/i.test(type)
      ? "application/xhtml+xml"
      : "text/html";
  const document = new DOMParser().parseFromString(data, parserType);
  document.querySelectorAll("script, iframe, object, embed").forEach((node) => node.remove());
  document.querySelectorAll("*").forEach((element) => {
    for (const attribute of Array.from(element.attributes)) {
      if (attribute.name.toLowerCase().startsWith("on") || attribute.name === "srcdoc") {
        element.removeAttribute(attribute.name);
      }
    }
  });

  if (parserType !== "image/svg+xml") {
    const namespace = "http://www.w3.org/1999/xhtml";
    let head = document.querySelector("head");
    if (!head) {
      head = document.createElementNS(namespace, "head");
      document.documentElement.prepend(head);
    }
    const meta = document.createElementNS(namespace, "meta");
    meta.setAttribute("http-equiv", "Content-Security-Policy");
    meta.setAttribute("content", PUBLICATION_CSP);
    head.prepend(meta);
  }

  return new XMLSerializer().serializeToString(document);
}

function mimeFor(filename: string): string {
  const extension = filename.split(".").pop()?.toLowerCase();
  return {
    epub: "application/epub+zip",
    mobi: "application/x-mobipocket-ebook",
    azw: "application/vnd.amazon.ebook",
    azw3: "application/vnd.amazon.ebook",
    prc: "application/x-mobipocket-ebook",
    fb2: "application/x-fictionbook+xml",
    cbz: "application/vnd.comicbook+zip",
  }[extension || ""] || "application/octet-stream";
}

function loadSavedLocation(storageKey: string): PersistedLocation | null {
  try {
    const raw = window.localStorage.getItem(storageKey);
    return raw ? (JSON.parse(raw) as PersistedLocation) : null;
  } catch {
    return null;
  }
}

export const FoliateReader = forwardRef<FoliateReaderHandle, FoliateReaderProps>(
  function FoliateReader(
    {
      fileUrl,
      filename,
      storageKey,
      preferences,
      highlights,
      onLocationChange,
      onMetadata,
      onSelection,
      onLoadingChange,
      onError,
    },
    ref,
  ) {
    const hostRef = useRef<HTMLDivElement>(null);
    const viewRef = useRef<FoliateView | null>(null);
    const preferencesRef = useRef(preferences);
    const highlightsRef = useRef(highlights);
    const renderedHighlightsRef = useRef(new Set<string>());
    const searchTokenRef = useRef(0);
    const callbacksRef = useRef({
      onLocationChange,
      onMetadata,
      onSelection,
      onLoadingChange,
      onError,
    });
    const [ready, setReady] = useState(false);

    preferencesRef.current = preferences;
    highlightsRef.current = highlights;
    callbacksRef.current = {
      onLocationChange,
      onMetadata,
      onSelection,
      onLoadingChange,
      onError,
    };

    useImperativeHandle(ref, () => ({
      previous: () => void viewRef.current?.goLeft(),
      next: () => void viewRef.current?.goRight(),
      goTo: (target) => void viewRef.current?.goTo(target),
      goToFraction: (fraction) => void viewRef.current?.goToFraction(fraction),
      goToTarget: (target: ReaderTarget) => {
        if (target.kind === "foliate") void viewRef.current?.goTo(target.cfi);
      },
      goToSearchResult: (searchResult) => {
        if (searchResult.target.kind === "foliate") {
          void viewRef.current?.goTo(searchResult.target.cfi);
        }
      },
      clearSearch: () => {
        searchTokenRef.current += 1;
        viewRef.current?.clearSearch();
      },
      search: async (query, onProgress) => {
        const view = viewRef.current;
        if (!view || !query.trim()) return [];
        const token = ++searchTokenRef.current;
        const searchResults: ReaderSearchResult[] = [];
        for await (const searchEvent of view.search({ query: query.trim() })) {
          if (token !== searchTokenRef.current) break;
          if (typeof searchEvent === "string") continue;
          if (typeof searchEvent.progress === "number") {
            onProgress?.(searchEvent.progress);
          }
          for (const searchMatch of searchEvent.subitems || []) {
            searchResults.push({
              id: `foliate-${searchMatch.cfi}`,
              label: searchEvent.label || "Book text",
              pre: searchMatch.excerpt.pre,
              match: searchMatch.excerpt.match,
              post: searchMatch.excerpt.post,
              target: { kind: "foliate", cfi: searchMatch.cfi },
            });
            if (searchResults.length >= 250) return searchResults;
          }
        }
        return searchResults;
      },
    }), []);

    useEffect(() => {
      let disposed = false;
      const host = hostRef.current;
      if (!host) return;

      async function openBook(hostElement: HTMLDivElement) {
        callbacksRef.current.onLoadingChange(true);
        callbacksRef.current.onError(null);
        setReady(false);

        try {
          const [, { Overlayer }] = await Promise.all([
            import("foliate-js/view.js"),
            import("foliate-js/overlayer.js"),
          ]);
          if (disposed) return;

          const response = await fetch(fileUrl);
          if (!response.ok) throw new Error(`Could not open book (HTTP ${response.status})`);
          const blob = await response.blob();
          if (disposed) return;

          const file = new File([blob], filename, {
            type: response.headers.get("content-type") || mimeFor(filename),
          });
          const view = document.createElement("foliate-view") as FoliateView;
          view.className = "foliate-book-view";
          hostElement.replaceChildren(view);
          viewRef.current = view;

          await view.open(file);
          if (disposed) {
            view.close();
            return;
          }

          view.book.transformTarget?.addEventListener("data", (event) => {
            const detail = (event as CustomEvent).detail as {
              data: unknown;
              type: string;
            };
            detail.data = Promise.resolve(detail.data).then((publicationMarkup) =>
              sanitizePublicationMarkup(publicationMarkup, detail.type),
            );
          });

          const wiredDocuments = new WeakSet<Document>();
          view.addEventListener("external-link", (event) => event.preventDefault());
          view.addEventListener("load", (event) => {
            const detail = (event as CustomEvent).detail as { doc?: Document };
            const document = detail.doc;
            if (!document || wiredDocuments.has(document)) return;
            wiredDocuments.add(document);
            document.addEventListener("keydown", (keyEvent) => {
              if (keyEvent.key === "ArrowLeft") void view.goLeft();
              if (keyEvent.key === "ArrowRight") void view.goRight();
            });
            document.addEventListener("mouseup", () => {
              const selected = document.getSelection();
              const text = selected?.toString().trim() || "";
              if (!selected || !text || selected.rangeCount === 0) return;
              const activeSection = view.renderer
                .getContents?.()
                .find((content) => content.doc === document);
              if (!activeSection) return;
              const cfi = view.getCFI(
                activeSection.index,
                selected.getRangeAt(0).cloneRange(),
              );
              callbacksRef.current.onSelection({
                text: text.slice(0, 2400),
                target: { kind: "foliate", cfi },
              });
            });
          });
          view.addEventListener("draw-annotation", (event) => {
            const detail = (event as CustomEvent).detail as {
              draw: (
                renderer: typeof Overlayer.highlight,
                options: { color: string; padding: number },
              ) => void;
            };
            detail.draw(Overlayer.highlight, { color: "#dca84f", padding: 1 });
          });
          view.addEventListener("create-overlay", () => {
            for (const cfi of highlightsRef.current) {
              void view.addAnnotation({ value: cfi });
            }
          });
          view.addEventListener("relocate", (event) => {
            const detail = (event as CustomEvent).detail as {
              fraction?: number;
              cfi?: string;
              tocItem?: { label?: string };
              pageItem?: { label?: string };
            };
            const location: ReaderLocation = {
              fraction: Math.max(0, Math.min(1, detail.fraction ?? 0)),
              cfi: detail.cfi,
              chapter: detail.tocItem?.label,
              page: detail.pageItem?.label,
            };
            callbacksRef.current.onLocationChange(location);
            try {
              window.localStorage.setItem(
                storageKey,
                JSON.stringify({
                  cfi: location.cfi,
                  fraction: location.fraction,
                  updatedAt: new Date().toISOString(),
                } satisfies PersistedLocation),
              );
            } catch {
              // Reading must continue even when browser storage is disabled.
            }
          });

          const activePreferences = preferencesRef.current;
          view.renderer.setStyles?.(readerCss(activePreferences));
          view.renderer.setAttribute("flow", activePreferences.flow);
          view.renderer.setAttribute("max-inline-size", `${activePreferences.maxWidth}px`);
          view.renderer.setAttribute("max-column-count", "2");
          view.renderer.setAttribute("gap", "7%");
          view.renderer.setAttribute("margin", "36px");

          callbacksRef.current.onMetadata({
            title: firstLocalized(view.book.metadata?.title),
            author: firstLocalized(view.book.metadata?.author),
            toc: flattenToc(view.book.toc || []),
          });

          const saved = loadSavedLocation(storageKey);
          await view.init({
            lastLocation: saved?.cfi || null,
            showTextStart: true,
          });
          for (const cfi of highlightsRef.current) {
            void view.addAnnotation({ value: cfi });
          }
          renderedHighlightsRef.current = new Set(highlightsRef.current);
          setReady(true);
        } catch (error) {
          console.error("Reader failed to open publication", error);
          callbacksRef.current.onError(
            error instanceof Error ? error.message : "This publication could not be opened",
          );
        } finally {
          callbacksRef.current.onLoadingChange(false);
        }
      }

      void openBook(host);
      return () => {
        disposed = true;
        setReady(false);
        const retiringView = viewRef.current;
        viewRef.current = null;
        renderedHighlightsRef.current.clear();
        if (retiringView) {
          // foliate-js queues layout work in ResizeObserver, rAF, and
          // document.fonts.ready. Removing its iframe synchronously can leave
          // one of those callbacks holding a null document. Let the queued
          // layout settle before releasing the publication resources.
          Object.assign(retiringView.style, {
            position: "fixed",
            inset: "0",
            zIndex: "-1",
            visibility: "hidden",
            pointerEvents: "none",
          });
          document.body.append(retiringView);
          window.setTimeout(() => {
            retiringView.close();
            retiringView.remove();
          }, 1000);
        }
      };
    }, [fileUrl, filename, storageKey]);

    useEffect(() => {
      const view = viewRef.current;
      if (!view || !ready) return;
      const nextHighlights = new Set(highlights);
      for (const cfi of renderedHighlightsRef.current) {
        if (!nextHighlights.has(cfi)) void view.deleteAnnotation({ value: cfi });
      }
      for (const cfi of nextHighlights) {
        if (!renderedHighlightsRef.current.has(cfi)) {
          void view.addAnnotation({ value: cfi });
        }
      }
      renderedHighlightsRef.current = nextHighlights;
    }, [highlights, ready]);

    useEffect(() => {
      const view = viewRef.current;
      if (!view || !ready) return;
      view.renderer.setStyles?.(readerCss(preferences));
      view.renderer.setAttribute("flow", preferences.flow);
      view.renderer.setAttribute("max-inline-size", `${preferences.maxWidth}px`);
    }, [preferences, ready]);

    return <div ref={hostRef} className="foliate-reader-host" aria-label="Book text" />;
  },
);
