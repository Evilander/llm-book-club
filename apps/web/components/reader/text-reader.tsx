"use client";

import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from "react";
import type { ReaderPreferences } from "./foliate-reader";
import {
  findTextMatches,
  type ReaderInteractionHandle,
  type ReaderSelection,
} from "./reader-interactions";

interface TextReaderProps {
  fileUrl: string;
  storageKey: string;
  preferences: ReaderPreferences;
  onProgress: (fraction: number) => void;
  onSelection: (selection: ReaderSelection) => void;
  onLoadingChange: (loading: boolean) => void;
  onError: (message: string | null) => void;
}

export const TextReader = forwardRef<ReaderInteractionHandle, TextReaderProps>(
  function TextReader(
    {
      fileUrl,
      storageKey,
      preferences,
      onProgress,
      onSelection,
      onLoadingChange,
      onError,
    },
    ref,
  ) {
  const [text, setText] = useState("");
  const [activeMatch, setActiveMatch] = useState<{ start: number; end: number } | null>(null);
  const scrollerRef = useRef<HTMLDivElement>(null);
  const activeMatchRef = useRef<HTMLElement>(null);

  const scrollToOffset = useCallback((offset: number, fraction?: number) => {
    const scroller = scrollerRef.current;
    if (!scroller || !text) return;
    const targetFraction = fraction ?? offset / Math.max(1, text.length);
    requestAnimationFrame(() => {
      scroller.scrollTop = targetFraction * (scroller.scrollHeight - scroller.clientHeight);
    });
  }, [text]);

  useImperativeHandle(ref, () => ({
    clearSearch: () => setActiveMatch(null),
    goToSearchResult: (searchResult) => {
      if (searchResult.target.kind !== "text") return;
      setActiveMatch({
        start: searchResult.target.offset,
        end: searchResult.target.offset
          + (searchResult.target.length || searchResult.match.length),
      });
      scrollToOffset(searchResult.target.offset, searchResult.target.fraction);
    },
    goToTarget: (target) => {
      if (target.kind !== "text") return;
      setActiveMatch(
        target.length
          ? { start: target.offset, end: target.offset + target.length }
          : null,
      );
      scrollToOffset(target.offset, target.fraction);
    },
    search: async (query, onProgress) => {
      const matches = findTextMatches(text, query);
      onProgress?.(1);
      return matches.map((match) => ({
        id: `text-${match.start}`,
        label: `${Math.round((match.start / Math.max(1, text.length)) * 100)}% through the book`,
        pre: match.pre,
        match: match.match,
        post: match.post,
        target: {
          kind: "text" as const,
          offset: match.start,
          fraction: match.start / Math.max(1, text.length),
          length: match.end - match.start,
        },
      }));
    },
  }), [scrollToOffset, text]);

  useEffect(() => {
    let disposed = false;
    onLoadingChange(true);
    onError(null);
    fetch(fileUrl)
      .then((httpResponse) => {
        if (!httpResponse.ok) {
          throw new Error(`Could not open text (HTTP ${httpResponse.status})`);
        }
        return httpResponse.text();
      })
      .then((publicationText) => {
        if (!disposed) setText(publicationText);
      })
      .catch((error) => {
        if (!disposed) {
          onError(error instanceof Error ? error.message : "This text could not be opened");
        }
      })
      .finally(() => {
        if (!disposed) onLoadingChange(false);
      });
    return () => {
      disposed = true;
    };
  }, [fileUrl, onError, onLoadingChange]);

  useEffect(() => {
    const scroller = scrollerRef.current;
    if (!scroller || !text) return;
    try {
      const raw = window.localStorage.getItem(storageKey);
      const saved = raw ? (JSON.parse(raw) as { fraction?: number }) : null;
      if (typeof saved?.fraction === "number") {
        requestAnimationFrame(() => {
          scroller.scrollTop = saved.fraction! * (scroller.scrollHeight - scroller.clientHeight);
        });
      }
    } catch {
      // Ignore malformed or unavailable local storage.
    }
  }, [storageKey, text]);

  useEffect(() => {
    activeMatchRef.current?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [activeMatch]);

  function updateProgress() {
    const scroller = scrollerRef.current;
    if (!scroller) return;
    const range = Math.max(1, scroller.scrollHeight - scroller.clientHeight);
    const fraction = Math.max(0, Math.min(1, scroller.scrollTop / range));
    onProgress(fraction);
    try {
      window.localStorage.setItem(
        storageKey,
        JSON.stringify({ fraction, updatedAt: new Date().toISOString() }),
      );
    } catch {
      // Reading must work with storage disabled.
    }
  }

  const paletteClass = {
    paper: "reader-text-paper",
    night: "reader-text-night",
    contrast: "reader-text-contrast",
  }[preferences.theme];

  return (
    <div
      ref={scrollerRef}
      className={`text-reader-scroll ${paletteClass}`}
      onScroll={updateProgress}
      onMouseUp={() => {
        const selected = window.getSelection();
        const selectedText = selected?.toString().trim() || "";
        const scroller = scrollerRef.current;
        const article = scroller?.querySelector("article");
        if (!selected || !selectedText || !scroller || !article || selected.rangeCount === 0) return;
        const selectedRange = selected.getRangeAt(0);
        if (!article.contains(selectedRange.commonAncestorContainer)) return;
        const prefix = selectedRange.cloneRange();
        prefix.selectNodeContents(article);
        prefix.setEnd(selectedRange.startContainer, selectedRange.startOffset);
        const offset = prefix.toString().length;
        const scrollRange = Math.max(1, scroller.scrollHeight - scroller.clientHeight);
        onSelection({
          text: selectedText.slice(0, 2400),
          target: {
            kind: "text",
            offset,
            fraction: Math.max(0, Math.min(1, scroller.scrollTop / scrollRange)),
            length: selectedText.length,
          },
        });
      }}
    >
      <article
        className="text-reader-page"
        style={{
          fontSize: preferences.fontSize,
          lineHeight: preferences.lineHeight,
          maxWidth: preferences.maxWidth,
        }}
      >
        {activeMatch ? (
          <>
            {text.slice(0, activeMatch.start)}
            <mark ref={activeMatchRef} className="text-search-hit">
              {text.slice(activeMatch.start, activeMatch.end)}
            </mark>
            {text.slice(activeMatch.end)}
          </>
        ) : text}
      </article>
    </div>
  );
  },
);
