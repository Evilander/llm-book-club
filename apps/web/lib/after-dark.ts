/**
 * After-dark portal helpers.
 *
 * Two concerns live here:
 *   1. Age-gate state machine (localStorage-backed, 30-day re-prompt).
 *   2. Folder classification heuristic — decide which BOOKS_DIR folders
 *      belong in the after-dark portal vs the daylight library.
 *
 * The "private from daylight" promise in the spec is enforced through a
 * different `X-Reader-Id` cookie value when in after-dark mode, so the
 * backend never co-mingles reading-prefs or reading-progress between the
 * two contexts.
 */

const SEAL_KEY = "readagain.after-dark.seal";
const SEAL_TTL_MS = 30 * 24 * 60 * 60 * 1000; // 30 days

export interface SealRecord {
  /** Unix ms when the user confirmed they are 18+. */
  confirmedAt: number;
  /** Stable per-browser reader id used for after-dark reading prefs. */
  afterDarkReaderId: string;
}

export function readSeal(): SealRecord | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(SEAL_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as SealRecord;
    if (Date.now() - parsed.confirmedAt > SEAL_TTL_MS) {
      // Expired; clear and re-prompt
      window.localStorage.removeItem(SEAL_KEY);
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

export function writeSeal(): SealRecord {
  const record: SealRecord = {
    confirmedAt: Date.now(),
    afterDarkReaderId: `ad-${cryptoRandomId()}`,
  };
  if (typeof window !== "undefined") {
    window.localStorage.setItem(SEAL_KEY, JSON.stringify(record));
  }
  return record;
}

export function breakSeal(): void {
  if (typeof window !== "undefined") {
    window.localStorage.removeItem(SEAL_KEY);
  }
}

function cryptoRandomId(): string {
  if (typeof crypto !== "undefined" && crypto.randomUUID) {
    return crypto.randomUUID().replace(/-/g, "").slice(0, 16);
  }
  return Math.random().toString(36).slice(2, 18);
}

// ── Folder classification ────────────────────────────────────────────────

/**
 * Folder-name heuristic for after-dark relevance.
 *
 * STRATEGY: prefer false negatives over false positives. A folder
 * classified as after-dark that ISN'T actually adult feels wrong; a folder
 * classified as daylight that IS adult is fine — the user can opt in
 * explicitly.
 *
 * Tokens are matched case-insensitively against the folder name only.
 * No file-content inspection. No author lookup. Pure folder-name.
 *
 * To tune: add tokens to ADULT_TOKENS for inclusion; add to SAFE_TOKENS
 * for explicit exclusion when an adult token also matches innocently
 * (e.g. "lesbian poetry" is poetry, not erotica).
 */
/**
 * Adult tokens. Word-boundary matched against the lowercased folder name.
 * A token is a single word OR a multi-word phrase; phrases are matched
 * with word boundaries on both ends.
 *
 * SAFETY: tokens that occur as a substring of an innocent word (e.g.
 * "adult" inside "young adult") MUST be word-boundary anchored, not
 * substring-checked. The previous implementation pulled Children's & YA
 * folders into the portal because "young adult".includes("adult") is true.
 */
const ADULT_TOKENS = [
  "erotic", "erotica", "erotique", "erotic fiction", "erotic romance",
  "porn", "porno", "pornography",
  "smut",
  "explicit",
  "adult fiction", "adults only", "adult only", "for adults", "adult erotica",
  "after dark", "after-dark",
  "kink", "kinky",
  "bdsm",
  "fetish",
  "lust",
  "seduction",
  "sex", // word-boundary anchored: matches "sex" / "sex education" but NOT "sextant", "Wessex", "essex"
  // Indicative author/series tokens (phrases, word-boundary anchored)
  "lesbian ebook archive",
  "anaïs nin",
  "anais nin",
  "henry miller",
  "marquis de sade",
  "story of o",
  "delta of venus",
];

const SAFE_TOKENS = [
  // explicit overrides — folders that match an adult token but are NOT after-dark
  "young adult", "young-adult",
  "ya fiction", "ya romance",
  "children", "children's", "childrens",
  "juvenile", "middle grade", "middle-grade",
  "kids", "kid's",
  "picture book", "early reader",
  "academic", "textbook",
  "sex therapy", "sex education", "sexual health",
  "lesbian poetry", "lesbian history",
  "queer theory", "gender studies",
  "biography", "history", "religion", "theology",
];

export interface FolderClassification {
  isAfterDark: boolean;
  matchedToken: string | null;
  safelisted: string | null;
}

/**
 * Build a word-boundary regex for a token. Escapes regex metacharacters
 * in the token, then anchors with \b on either side. Unicode-aware so
 * accented characters in author names match correctly.
 */
function wordBoundaryRegex(token: string): RegExp {
  const escaped = token.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  // \b in JS regex is ASCII-only; emulate Unicode-friendly word boundary
  // with lookarounds against word chars + apostrophes.
  return new RegExp(`(^|[^\\p{L}\\p{N}'])${escaped}($|[^\\p{L}\\p{N}'])`, "iu");
}

const ADULT_REGEX = ADULT_TOKENS.map((t) => ({ token: t, regex: wordBoundaryRegex(t) }));
const SAFE_REGEX = SAFE_TOKENS.map((t) => ({ token: t, regex: wordBoundaryRegex(t) }));

export function classifyFolder(folderName: string): FolderClassification {
  const lower = folderName.toLowerCase();

  // Safe overrides first — any safe token wins even if an adult token also matches.
  for (const { token, regex } of SAFE_REGEX) {
    if (regex.test(lower)) {
      return { isAfterDark: false, matchedToken: null, safelisted: token };
    }
  }

  for (const { token, regex } of ADULT_REGEX) {
    if (regex.test(lower)) {
      return { isAfterDark: true, matchedToken: token, safelisted: null };
    }
  }

  return { isAfterDark: false, matchedToken: null, safelisted: null };
}

/** Filter a list of folders to just the after-dark ones. */
export function filterAfterDarkFolders<T extends { name: string }>(folders: T[]): T[] {
  return folders.filter((f) => classifyFolder(f.name).isAfterDark);
}

// ── Cast personas (matches the discussion-stage personas) ───────────────

export interface AfterDarkPersona {
  id: "sable" | "lucian" | "vesper";
  name: string;
  initial: string;
  ink: "sable" | "lucian" | "vesper";
  invitation: string;
}

export const AFTER_DARK_PERSONAS: AfterDarkPersona[] = [
  {
    id: "sable",
    name: "Sable",
    initial: "v",
    ink: "sable",
    invitation:
      "I'll trace what the page makes you feel before it tells you why.",
  },
  {
    id: "lucian",
    name: "Lucian",
    initial: "L",
    ink: "lucian",
    invitation:
      "Two men in a room is half the room and all the weather. Let me show you.",
  },
  {
    id: "vesper",
    name: "Vesper",
    initial: "V",
    ink: "vesper",
    invitation:
      "I read for the pressure under the surface. Bring me the careful sentences.",
  },
];
