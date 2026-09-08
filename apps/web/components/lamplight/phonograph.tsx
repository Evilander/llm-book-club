import { cn } from "@/lib/utils";
import { getAccessibilityProps, type LamplightSvgProps } from "./shared";

interface PhonographProps extends LamplightSvgProps {
  spinning?: boolean;
}

export function Phonograph({
  spinning = false,
  className,
  title,
  ...props
}: PhonographProps) {
  return (
    <svg
      viewBox="0 0 96 96"
      className={cn("h-10 w-10", className)}
      fill="none"
      {...getAccessibilityProps(title || "Phonograph")}
      {...props}
    >
      <path
        d="M62 18C74 14 84 18 88 28C80 35 68 38 56 36L50 30C52 24 56 20 62 18Z"
        fill="url(#horn-fill)"
        stroke="var(--brass)"
        strokeWidth="2"
      />
      <path
        d="M58 33L47 44"
        stroke="var(--brass)"
        strokeLinecap="round"
        strokeWidth="2.2"
      />
      <rect x="18" y="44" width="44" height="26" rx="3" fill="var(--ink-ellis)" />
      <rect x="22" y="48" width="36" height="18" rx="2" fill="var(--ink)" opacity="0.55" />
      <rect x="31" y="68" width="18" height="4" rx="1" fill="var(--brass)" opacity="0.85" />
      <circle
        cx="40"
        cy="57"
        r="10"
        fill="var(--ink-kit)"
        className={cn(spinning && "animate-spin-slow motion-reduce:animate-none")}
        style={{ transformOrigin: "40px 57px" }}
      />
      <circle cx="40" cy="57" r="2.5" fill="var(--cream)" opacity="0.9" />
      <path
        d="M48 52C54 52 58 48 59 44"
        stroke="var(--lamp-glow)"
        strokeLinecap="round"
        strokeWidth="2"
      />
      <path
        d="M59 44L61 47"
        stroke="var(--lamp-glow)"
        strokeLinecap="round"
        strokeWidth="2"
      />
      <defs>
        <linearGradient id="horn-fill" x1="56" y1="24" x2="88" y2="28" gradientUnits="userSpaceOnUse">
          <stop stopColor="var(--lamp-glow)" />
          <stop offset="1" stopColor="var(--brass)" />
        </linearGradient>
      </defs>
    </svg>
  );
}
