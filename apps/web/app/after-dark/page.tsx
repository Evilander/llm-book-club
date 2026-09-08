"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import {
  AFTER_DARK_PERSONAS,
  breakSeal,
  filterAfterDarkFolders,
  readSeal,
  writeSeal,
  type SealRecord,
} from "@/lib/after-dark";
import { API_BASE } from "@/lib/utils";
import type { LocalBook, LocalFolderEntry } from "@/types/api";

/** Curated shelf seeds — literary fallback when no library is reachable. */
const FALLBACK_SHELVES = [
  {
    invitation: "Books where the architecture is the seduction.",
    spines: [
      { title: "The Voss Inheritance", author: "Hale", shade: "wine", height: "tall" },
      { title: "Wetlands", author: "Roche", shade: "aubergine", height: "" },
      { title: "Story of O", author: "Réage", shade: "oxblood", height: "tall" },
      { title: "Delta of Venus", author: "Nin", shade: "foxed", height: "" },
      { title: "In the Cut", author: "Moore", shade: "plum", height: "short" },
      { title: "The Lover's Discourse", author: "Barthes", shade: "ink", height: "tall" },
      { title: "Eros the Bittersweet", author: "Carson", shade: "brass", height: "short" },
    ],
  },
  {
    invitation: "Books that take their time with the gloves.",
    spines: [
      { title: "The Awakening", author: "Chopin", shade: "cream", height: "tall" },
      { title: "Lady Chatterley's Lover", author: "Lawrence", shade: "wine", height: "" },
      { title: "The Sexual Life of Catherine M.", author: "Millet", shade: "oxblood", height: "short" },
      { title: "The Lover", author: "Duras", shade: "aubergine", height: "tall" },
      { title: "The Piano Teacher", author: "Jelinek", shade: "foxed", height: "short" },
      { title: "The Pure and the Impure", author: "Colette", shade: "plum", height: "" },
    ],
  },
  {
    invitation: "Books that make you read what you weren't planning to read.",
    spines: [
      { title: "Trois Filles de leur Mère", author: "Louÿs", shade: "aubergine", height: "tall" },
      { title: "Nightwood", author: "Barnes", shade: "ink", height: "" },
      { title: "In Praise of the Stepmother", author: "Vargas Llosa", shade: "wine", height: "short" },
      { title: "Tropisms", author: "Sarraute", shade: "plum", height: "tall" },
      { title: "The Hearing Trumpet", author: "Carrington", shade: "foxed", height: "" },
    ],
  },
];

const SPINE_SHADES = ["wine", "aubergine", "plum", "oxblood", "brass", "foxed", "ink", "cream"] as const;
const SPINE_HEIGHTS = ["", "tall", "short", "", "tall"] as const;

function pickShade(seed: string, idx: number): string {
  let hash = idx;
  for (let i = 0; i < seed.length; i++) hash = (hash * 31 + seed.charCodeAt(i)) >>> 0;
  return SPINE_SHADES[hash % SPINE_SHADES.length];
}
function pickHeight(seed: string, idx: number): string {
  let hash = idx;
  for (let i = 0; i < seed.length; i++) hash = (hash * 17 + seed.charCodeAt(i)) >>> 0;
  return SPINE_HEIGHTS[hash % SPINE_HEIGHTS.length];
}

/**
 * Clean a raw filename-ish title for spine display:
 *   - strip the file extension
 *   - strip leading numbering ("02 - " / "120 - " / "[Goosebumps 02] - ")
 *   - replace underscores with spaces
 *   - collapse repeated whitespace
 *   - truncate over ~26 chars with an ellipsis so vertical text doesn't run
 *     past the spine height
 */
function tidyTitle(raw: string): string {
  let t = raw.replace(/\.(epub|pdf|txt|mobi|azw3?|fb2)$/i, "");
  t = t.replace(/^\[[^\]]+\]\s*[-—]?\s*/, ""); // [Series Name] - prefix
  t = t.replace(/^\d+\s*[-—.]\s*/, ""); // 02 - / 02. / 02 — prefix
  t = t.replace(/_/g, " ");
  t = t.replace(/\s+/g, " ").trim();
  if (t.length > 26) t = t.slice(0, 25).replace(/[\s,.;:-]+$/, "") + "…";
  return t;
}

interface RealShelf {
  invitation: string;
  folder: LocalFolderEntry;
  /** Real LocalBook entries with paths + ingested book_ids — these power the spine click handler. */
  books: LocalBook[];
}

export default function AfterDarkPage() {
  const router = useRouter();
  const [seal, setSeal] = useState<SealRecord | null>(null);
  const [cracking, setCracking] = useState(false);
  const [realShelves, setRealShelves] = useState<RealShelf[] | null>(null);
  const [hydrated, setHydrated] = useState(false);
  const [spineBusy, setSpineBusy] = useState<string | null>(null);

  // Hydrate seal state on mount (client-only)
  useEffect(() => {
    setSeal(readSeal());
    setHydrated(true);
  }, []);

  // Fetch real adult-flagged folders + their first N books with full paths
  useEffect(() => {
    if (!seal) return;
    let cancelled = false;

    async function loadAdultShelves() {
      try {
        const foldersRes = await fetch(`${API_BASE}/v1/library/local/folders`);
        if (!foldersRes.ok) return;
        const foldersData = (await foldersRes.json()) as { folders: LocalFolderEntry[] };
        const adult = filterAfterDarkFolders(foldersData.folders).slice(0, 3);
        if (adult.length === 0 || cancelled) return;

        const shelves: RealShelf[] = [];
        for (let idx = 0; idx < adult.length; idx++) {
          const folder = adult[idx];
          const res = await fetch(
            `${API_BASE}/v1/library/local?folder=${encodeURIComponent(folder.name)}&limit=7`
          );
          if (!res.ok) continue;
          const data = (await res.json()) as { books: LocalBook[] };
          if (cancelled) return;
          shelves.push({
            invitation: FALLBACK_SHELVES[idx]?.invitation ?? `From ${folder.name}.`,
            folder,
            books: data.books ?? [],
          });
        }
        if (!cancelled && shelves.length > 0) {
          setRealShelves(shelves);
        }
      } catch {
        // No real library; fall back to literary seeds.
      }
    }
    loadAdultShelves();
    return () => {
      cancelled = true;
    };
  }, [seal]);

  /** Spine click — route to ingested book or queue ingestion and navigate. */
  const onSpineClick = useCallback(
    async (book: LocalBook) => {
      if (spineBusy) return;
      if (book.book_id && book.already_ingested) {
        router.push(`/books/${book.book_id}/read`);
        return;
      }
      setSpineBusy(book.path);
      const t = toast.loading(`Binding ${book.title_guess}…`);
      try {
        const res = await fetch(`${API_BASE}/v1/library/local/ingest`, {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ path: book.path }),
        });
        if (!res.ok) throw new Error(`${res.status}`);
        const j = (await res.json()) as { book_id?: string };
        toast.success("In the bindery — opening when ready.", { id: t });
        if (j.book_id) {
          // Route to /books/{id} which will show the binding progress and
          // unlock the reader as soon as ingestion completes.
          router.push(`/books/${j.book_id}`);
        }
      } catch (err) {
        toast.error("Couldn't queue that one. Try again in a moment.", { id: t });
      } finally {
        setSpineBusy(null);
      }
    },
    [router, spineBusy]
  );

  const onBreakSeal = useCallback(() => {
    if (cracking) return;
    setCracking(true);
    window.setTimeout(() => {
      setSeal(writeSeal());
      setCracking(false);
    }, 320);
  }, [cracking]);

  const onRevoke = useCallback(() => {
    breakSeal();
    setSeal(null);
  }, []);

  const shelves = useMemo(() => {
    if (realShelves && realShelves.length > 0) {
      return realShelves.map((r) => ({
        invitation: r.invitation,
        spines: r.books.slice(0, 7).map((book, i) => ({
          title: tidyTitle(book.title_guess || book.filename),
          author: null as string | null,
          shade: pickShade(r.folder.name, i),
          height: pickHeight(r.folder.name, i),
          // Carry the LocalBook so spine clicks can route or queue ingestion.
          book,
        })),
        folderName: r.folder.name,
        bookCount: r.folder.book_count,
      }));
    }
    return FALLBACK_SHELVES.map((s) => ({
      ...s,
      spines: s.spines.map((sp) => ({
        ...sp,
        author: sp.author as string | null,
        book: null as LocalBook | null,
      })),
      folderName: null as string | null,
      bookCount: null as number | null,
    }));
  }, [realShelves]);

  // Until hydrated, render nothing to avoid age-gate hydration mismatches
  if (!hydrated) {
    return (
      <div className="ad-shell">
        <div className="ad-content-locked-skeleton" />
      </div>
    );
  }

  if (!seal) {
    return <AgeGate cracking={cracking} onBreak={onBreakSeal} />;
  }

  return (
    <div className="ad-shell">
      <div className="ad-room">
        <header className="ad-topbar">
          <span>The Private Library &nbsp;·&nbsp; After Dark</span>
          <button type="button" onClick={onRevoke} className="ad-topbar-leave">
            return to daylight ↩
          </button>
        </header>

        <section className="ad-hero">
          <h1>
            The library has rooms it doesn&rsquo;t open during the day.
            <span className="ad-hero-b">This is one of them.</span>
          </h1>
          <div className="ad-hero-status">
            <span className="ad-hero-rule" />
            After Dark &nbsp;·&nbsp; By Appointment &nbsp;·&nbsp; Reading Room III
          </div>
        </section>

        <section className="ad-cast">
          <div className="ad-cast-label">Tonight&rsquo;s readers in residence</div>
          <div className="ad-cast-row">
            {AFTER_DARK_PERSONAS.map((p, idx) => (
              <div
                key={p.id}
                className={`ad-player ad-player-${p.id}`}
                style={{ marginTop: `${idx * 52}px` }}
              >
                <div className={`ad-wax ad-wax-${p.id}`}>
                  <div className="ad-wax-glyph" aria-hidden="true">
                    {personaGlyph(p.id)}
                  </div>
                </div>
                <div className={`ad-name ad-name-${p.id}`}>
                  {p.name}
                  <span className="ad-name-lens">{personaLens(p.id)}</span>
                </div>
                <div className="ad-invite">&ldquo;{p.invitation}&rdquo;</div>
              </div>
            ))}
          </div>
        </section>

        {shelves.map((shelf, sidx) => (
          <section key={sidx} className="ad-shelf-block">
            <h3>{shelf.invitation}</h3>
            {shelf.folderName ? (
              <div className="ad-shelf-source">
                from <em>{shelf.folderName}</em> &nbsp;·&nbsp; {shelf.bookCount?.toLocaleString() ?? "?"} volumes
              </div>
            ) : null}
            <div className="ad-shelf" role="list">
              {shelf.spines.map((spine, spidx) => {
                const book = spine.book;
                const busy = book !== null && spineBusy === book.path;
                const tooltip = book
                  ? book.already_ingested
                    ? `Open ${spine.title}`
                    : `Bind ${spine.title} into the room`
                  : spine.author
                    ? `${spine.title} — ${spine.author}`
                    : spine.title;
                const className = [
                  "ad-spine",
                  `ad-spine-${spine.shade}`,
                  spine.height ? `ad-spine-${spine.height}` : "",
                  book ? "ad-spine-clickable" : "",
                  busy ? "ad-spine-busy" : "",
                ]
                  .filter(Boolean)
                  .join(" ");
                if (book) {
                  return (
                    <button
                      key={spidx}
                      type="button"
                      className={className}
                      title={tooltip}
                      onClick={() => onSpineClick(book)}
                      disabled={busy}
                    >
                      <span className="ad-spine-title">{spine.title}</span>
                      {spine.author ? <span className="ad-spine-au">{spine.author}</span> : null}
                    </button>
                  );
                }
                return (
                  <div
                    key={spidx}
                    className={className}
                    role="listitem"
                    title={tooltip}
                  >
                    <span className="ad-spine-title">{spine.title}</span>
                    {spine.author ? <span className="ad-spine-au">{spine.author}</span> : null}
                  </div>
                );
              })}
            </div>
          </section>
        ))}

        <section className="ad-invite-card">
          <div className="ad-envelope" aria-hidden="true">
            <div className="ad-envelope-seal">S</div>
          </div>
          <div className="ad-invite-text">
            <div className="ad-invite-tag">— a sealed invitation</div>
            <p>
              Read a character into the room.{" "}
              <span className="ad-invite-em">Sable</span> can speak as someone
              in the book you&rsquo;re holding — grounded in cited spans, never
              inventing past the page.{" "}
              <Link href="/" className="ad-invite-link">
                pick a book →
              </Link>
            </p>
          </div>
        </section>

        <div className="ad-privacy">
          <span className="ad-privacy-line">
            what you read here stays separate from your daylight history.
          </span>
          <span className="ad-privacy-peg" />
          <button type="button" onClick={onRevoke} className="ad-privacy-leave">
            see daylight history
          </button>
          <span className="ad-privacy-peg" />
        </div>
      </div>
    </div>
  );
}

function AgeGate({ cracking, onBreak }: { cracking: boolean; onBreak: () => void }) {
  return (
    <div className={`ad-gate${cracking ? " ad-gate-cracked" : ""}`} role="dialog" aria-modal="true">
      <div className="ad-gate-inner">
        <div className="ad-gate-pre">
          — The Private Library &nbsp;·&nbsp; Reading Room III —
        </div>
        <p className="ad-gate-line">
          Behind this door is reading for adults only.
        </p>
        <p className="ad-gate-sub">
          Click the seal to confirm you are eighteen or older. Your
          confirmation is remembered for thirty days.
        </p>
        <button
          type="button"
          className="ad-seal"
          onClick={onBreak}
          aria-label="Break the wax seal to enter"
        >
          <div className="ad-seal-half ad-seal-l">
            <div className="ad-seal-disc" />
          </div>
          <div className="ad-seal-half ad-seal-r">
            <div className="ad-seal-disc" />
          </div>
        </button>
        <div className="ad-gate-foot">
          Break the seal &nbsp;·&nbsp; Enter quietly
        </div>
      </div>
    </div>
  );
}

function personaGlyph(id: "sable" | "lucian" | "vesper") {
  if (id === "sable") {
    return (
      <svg viewBox="0 0 32 32" stroke="currentColor" strokeWidth="1.2" fill="none" strokeLinecap="round" strokeLinejoin="round">
        <path d="M6 22 C10 12, 22 12, 26 22" />
        <path d="M10 22 L10 17" />
        <path d="M14 22 L14 14" />
        <path d="M18 22 L18 14" />
        <path d="M22 22 L22 17" />
      </svg>
    );
  }
  if (id === "lucian") {
    return (
      <svg viewBox="0 0 32 32" stroke="currentColor" strokeWidth="1.2" fill="none" strokeLinecap="round" strokeLinejoin="round">
        <path d="M6 10 L26 10 L26 22 L6 22 Z" />
        <path d="M6 10 L16 18 L26 10" />
        <path d="M11 15 L11 22" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 32 32" stroke="currentColor" strokeWidth="1.2" fill="none" strokeLinecap="round" strokeLinejoin="round">
      <rect x="6" y="9" width="20" height="14" />
      <path d="M6 9 L16 17 L26 9" />
      <rect x="19" y="5" width="7" height="7" fill="rgba(242,230,208,.15)" />
      <path d="M19 5 L26 12" />
      <path d="M26 5 L19 12" />
    </svg>
  );
}

function personaLens(id: "sable" | "lucian" | "vesper"): string {
  switch (id) {
    case "sable":
      return "Woman lens · wine ink";
    case "lucian":
      return "Gay man lens · aubergine ink";
    case "vesper":
      return "Trans woman lens · plum ink";
  }
}
