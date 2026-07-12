const DISCUSSION_FOCUS_PREFIX = "lbc-discussion-focus-v1:";
const MAX_FOCUS_AGE_MS = 24 * 60 * 60 * 1000;

export interface DiscussionFocus {
  quote: string;
  question?: string;
  chapter?: string;
  page?: string;
  fraction?: number;
  created_at: string;
}

function storageKey(bookId: string): string {
  return `${DISCUSSION_FOCUS_PREFIX}${bookId}`;
}

export function saveDiscussionFocus(bookId: string, focus: DiscussionFocus): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.setItem(storageKey(bookId), JSON.stringify(focus));
  } catch {
    // The setup still works without a handoff when browser storage is blocked.
  }
}

export function loadDiscussionFocus(bookId: string): DiscussionFocus | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.sessionStorage.getItem(storageKey(bookId));
    if (!raw) return null;
    const focus = JSON.parse(raw) as Partial<DiscussionFocus>;
    const createdAt = new Date(focus.created_at || "").getTime();
    if (
      typeof focus.quote !== "string" ||
      focus.quote.trim().length < 8 ||
      !Number.isFinite(createdAt) ||
      Date.now() - createdAt > MAX_FOCUS_AGE_MS
    ) {
      clearDiscussionFocus(bookId);
      return null;
    }
    return {
      quote: focus.quote.slice(0, 4000),
      question: focus.question?.slice(0, 1000),
      chapter: focus.chapter?.slice(0, 500),
      page: focus.page?.slice(0, 200),
      fraction:
        typeof focus.fraction === "number"
          ? Math.max(0, Math.min(1, focus.fraction))
          : undefined,
      created_at: focus.created_at!,
    };
  } catch {
    clearDiscussionFocus(bookId);
    return null;
  }
}

export function clearDiscussionFocus(bookId: string): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.removeItem(storageKey(bookId));
  } catch {
    // Nothing else needs cleanup when browser storage is unavailable.
  }
}
