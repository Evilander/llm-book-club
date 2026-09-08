import { cn } from "@/lib/utils";
import { getAccessibilityProps, type LamplightSvgProps } from "./shared";

interface RibbonBookmarkProps extends LamplightSvgProps {
  percent: number;
}

export function RibbonBookmark({
  percent,
  className,
  title,
  ...props
}: RibbonBookmarkProps) {
  return (
    <svg
      viewBox="0 0 32 108"
      className={cn("h-20 w-6", className)}
      fill="none"
      {...getAccessibilityProps(title || `Bookmark at ${percent}%`)}
      {...props}
    >
      <path
        d="M5 2H27V79L16 92L5 79V2Z"
        fill="url(#ribbon-fill)"
        stroke="rgba(0,0,0,0.28)"
        strokeWidth="1.25"
      />
      <path d="M23.5 4V78.5" stroke="rgba(255,255,255,0.08)" strokeWidth="1.4" />
      <path d="M8.5 4V78.5" stroke="rgba(0,0,0,0.18)" strokeWidth="1.4" />
      <text
        x="17"
        y="46"
        textAnchor="middle"
        transform="rotate(-90 17 46)"
        style={{ fontFamily: "var(--font-mono)", letterSpacing: "0.18em" }}
        fill="var(--lamp-glow)"
        fontSize="6.25"
      >
        {`${Math.max(0, Math.min(100, Math.round(percent)))}%`}
      </text>
      <defs>
        <linearGradient id="ribbon-fill" x1="16" y1="2" x2="16" y2="92" gradientUnits="userSpaceOnUse">
          <stop stopColor="var(--ink-sable)" />
          <stop offset="1" stopColor="#3A0E18" />
        </linearGradient>
      </defs>
    </svg>
  );
}
