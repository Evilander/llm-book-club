export type ReaderTarget =
  | { kind: "foliate"; cfi: string }
  | { kind: "pdf"; page: number }
  | { kind: "text"; offset: number; fraction: number; length?: number };

export interface ReaderSelection {
  text: string;
  target: ReaderTarget;
}

export interface ReaderSearchResult {
  id: string;
  label: string;
  pre: string;
  match: string;
  post: string;
  target: ReaderTarget;
}

export interface ReaderInteractionHandle {
  search: (
    query: string,
    onProgress?: (fraction: number) => void,
  ) => Promise<ReaderSearchResult[]>;
  clearSearch: () => void;
  goToSearchResult: (searchResult: ReaderSearchResult) => void;
  goToTarget: (target: ReaderTarget) => void;
}

export interface TextMatch {
  start: number;
  end: number;
  pre: string;
  match: string;
  post: string;
}

function excerptPart(textPart: string): string {
  return textPart.replace(/\s+/g, " ").trim();
}

export function findTextMatches(
  text: string,
  query: string,
  limit = 250,
  contextLength = 58,
): TextMatch[] {
  const needle = query.trim();
  if (!needle) return [];

  const escapedNeedle = needle.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const matcher = new RegExp(escapedNeedle, "giu");
  const matches: TextMatch[] = [];

  for (const regexMatch of text.matchAll(matcher)) {
    if (matches.length >= limit) break;
    const matchStart = regexMatch.index;
    const matchEnd = matchStart + regexMatch[0].length;
    matches.push({
      start: matchStart,
      end: matchEnd,
      pre: excerptPart(text.slice(Math.max(0, matchStart - contextLength), matchStart)),
      match: text.slice(matchStart, matchEnd),
      post: excerptPart(text.slice(matchEnd, matchEnd + contextLength)),
    });
  }

  return matches;
}
