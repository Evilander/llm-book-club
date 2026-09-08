/**
 * ReadAgain wordmark + colophon — replaces the old "LLM Book Club" banner.
 *
 * Glyph: pilcrow ¶ with a flame inside the counter (cream stems, brass flame).
 * Wordmark: italic Cormorant Garamond, "Read" in cream, "Again" in brass.
 * Tagline: JetBrains Mono small caps, "a private library at night".
 *
 * Sourced from claude-design-mcp design bb9d9486645d (2026-05-12).
 */

interface ReadAgainLockupProps {
  size?: "full" | "compact";
  className?: string;
}

export function ReadAgainLockup({ size = "compact", className }: ReadAgainLockupProps) {
  const isCompact = size === "compact";
  return (
    <div className={`readagain-lockup ${isCompact ? "is-compact" : "is-full"} ${className ?? ""}`}>
      <svg
        className="readagain-glyph"
        viewBox="0 0 38 46"
        aria-hidden="true"
        width={isCompact ? 28 : 38}
        height={isCompact ? 34 : 46}
      >
        {/* Pilcrow stems */}
        <rect x="24" y="6" width="2" height="36" fill="#F2E6D0" />
        <rect x="18" y="6" width="2" height="36" fill="#F2E6D0" />
        {/* Bowl */}
        <path
          d="M 18 6 L 10 6 A 8 8 0 0 0 10 22 L 18 22"
          fill="none"
          stroke="#F2E6D0"
          strokeWidth="2"
          strokeLinecap="square"
        />
        {/* Flame */}
        <path
          d="M 13.5 9.5 C 12 12, 14.5 13.5, 13.5 16 C 13 17.5, 14.8 18.2, 15.3 16.6 C 15.7 15.3, 14.6 14.6, 14.9 13.2 C 15.1 12.2, 14.5 11, 13.5 9.5 Z"
          fill="#C49A4A"
        />
        <rect x="13.4" y="17.4" width="1.2" height="1.6" fill="#C49A4A" opacity="0.85" />
        {/* Serifs */}
        <rect x="16" y="41" width="12" height="1.6" fill="#F2E6D0" />
        <rect x="14" y="5" width="14" height="1.6" fill="#F2E6D0" />
      </svg>
      <div className="readagain-wordmark">
        <span className="readagain-wordmark-read">Read</span>
        <span className="readagain-wordmark-again">Again</span>
      </div>
      {!isCompact ? (
        <div className="readagain-tagline">a private library at night</div>
      ) : null}
    </div>
  );
}
