"use client";

import { createElement, Fragment, useMemo, type ReactNode } from "react";
import { cn } from "@/lib/utils";
import type { ReaderNote } from "@/components/reader-companion";

interface ReadingMark {
  kind: "emphasis" | "strong" | "code" | "superscript" | "subscript" | "line_break" | "join";
  char_start: number; char_end: number;
}
export interface ReadingBlock {
  kind: "paragraph" | "heading" | "quote" | "list_item" | "preformatted";
  char_start: number; char_end: number; marks?: ReadingMark[];
  level?: number; list_label?: string | null; continued?: boolean;
}

export function applyBionicText(text: string, pct: number): ReactNode {
  const segmenter = new Intl.Segmenter(undefined, { granularity: "grapheme" });
  return text.split(/(\s+|[^\p{L}\p{M}\p{N}’']+)/u).map((part, idx) => {
    if (!/\p{L}/u.test(part) || part.length < 4) return part;
    const letters = Array.from(segmenter.segment(part), (item) => item.segment);
    const n = Math.max(1, Math.round((letters.length * pct) / 100));
    return <span key={idx}><b className="fr-b">{letters.slice(0, n).join("")}</b><span className="fr-r">{letters.slice(n).join("")}</span></span>;
  });
}

export function PageProse({ text, start = 0, blocks = [], notes = [], onSelectNote, focusOn, focusPct }: {
  text: string; start?: number; blocks?: ReadingBlock[]; notes?: ReaderNote[];
  onSelectNote?: (note: ReaderNote) => void; focusOn: boolean; focusPct: number;
}) {
  // All API coordinates count Unicode code points, not JavaScript UTF-16 units.
  const chars = useMemo(() => Array.from(text), [text]);
  const paragraphs = useMemo(() => {
    const result: ReadingBlock[] = [];
    const end = start + chars.length;
    function fallback(left: number, right: number) {
      let offset = left;
      for (const part of chars.slice(left - start, right - start).join("").split(/(\n\s*\n)/)) {
        const next = offset + Array.from(part).length;
        if (part.trim()) result.push({ kind: "paragraph", char_start: offset, char_end: next });
        offset = next;
      }
    }
    let cursor = start;
    for (const block of blocks) {
      const left = Math.max(start, block.char_start), right = Math.min(end, block.char_end);
      if (left < cursor || right <= left) continue;
      // Partial/absent metadata can never hide readable text.
      fallback(cursor, left);
      result.push({ ...block, char_start: left, char_end: right });
      cursor = right;
    }
    fallback(cursor, end);
    return result;
  }, [chars, start, blocks]);

  function renderBlock(block: ReadingBlock) {
    const left = block.char_start, right = block.char_end;
    const here = notes.filter((note) => note.char_start < right && note.char_end > left);
    const marks = (block.marks || []).filter(mark => mark.char_start < right && mark.char_end > left);
    const edges = [...new Set([left, right, ...[...here, ...marks].flatMap(item => [Math.max(left, item.char_start), Math.min(right, item.char_end)])])].sort((a, b) => a - b);
    const fragments = edges.slice(0, -1).map((edge, index) => {
      const next = edges[index + 1];
      const fragment = chars.slice(edge - start, next - start).join("");
      const active = new Set(marks.filter(mark => mark.char_start <= edge && mark.char_end >= next).map(mark => mark.kind));
      let value: ReactNode = focusOn && block.kind !== "preformatted" && !active.has("code") && !active.has("strong") ? applyBionicText(fragment, focusPct) : fragment;
      if (active.has("code")) value = <code>{value}</code>;
      if (active.has("emphasis")) value = <em>{value}</em>;
      if (active.has("strong")) value = <strong>{value}</strong>;
      if (active.has("superscript")) value = <sup>{value}</sup>;
      if (active.has("subscript")) value = <sub>{value}</sub>;
      if (active.has("line_break")) value = <span className="prose-line-break">{value}</span>;
      if (active.has("join")) value = <span hidden>{fragment}</span>;
      const note = here.find(item => item.char_start <= edge && item.char_end >= next);
      return { edge, note, value };
    });
    const content: ReactNode[] = [];
    for (let i = 0; i < fragments.length; i++) {
      const fragment = fragments[i], note = fragment.note;
      const values = [<Fragment key={fragment.edge}>{fragment.value}</Fragment>];
      while (note && fragments[i + 1]?.note === note) {
        const next = fragments[++i];
        values.push(<Fragment key={next.edge}>{next.value}</Fragment>);
      }
      content.push(note ? <button type="button" className="passage-mark" key={fragment.edge} onClick={() => onSelectNote?.(note)} title={note.question} aria-label={`Discuss highlighted passage: ${note.quote}`}>{values}</button> : <Fragment key={fragment.edge}>{values}</Fragment>);
    }
    const className = cn(`prose-${block.kind}`, block.continued && "prose-continued");
    if (block.kind === "heading") return createElement(`h${Math.min(6, Math.max(1, block.level || 1))}`, { className, key: left }, content);
    if (block.kind === "quote") return <blockquote className={className} key={left}>{content}</blockquote>;
    if (block.kind === "preformatted") return <pre className={className} key={left}>{content}</pre>;
    if (block.kind === "list_item") return <div role="listitem" className={className} key={left}><span className="prose-list-label" aria-hidden="true">{block.list_label}</span><div>{content}</div></div>;
    return <p className={className} key={left}>{content}</p>;
  }
  const elements: ReactNode[] = [];
  for (let i = 0; i < paragraphs.length; i++) {
    const block = paragraphs[i];
    if (block.kind !== "list_item") elements.push(renderBlock(block));
    else {
      const items = [renderBlock(block)];
      while (paragraphs[i + 1]?.kind === "list_item") items.push(renderBlock(paragraphs[++i]));
      elements.push(<div role="list" className="prose-list" key={`list-${block.char_start}`}>{items}</div>);
    }
  }
  return <div className={cn("lite-prose", focusOn && "is-focus")}>{elements}</div>;
}
