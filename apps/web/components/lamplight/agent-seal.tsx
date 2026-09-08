import { cn } from "@/lib/utils";
import {
  getAccessibilityProps,
  INK_VARS,
  type LamplightInk,
  type LamplightSvgProps,
} from "./shared";

interface AgentSealProps extends LamplightSvgProps {
  initial: string;
  ink?: LamplightInk;
}

export function AgentSeal({
  initial,
  ink = "ellis",
  className,
  title,
  ...props
}: AgentSealProps) {
  const label = title || `${initial.toUpperCase()} seal`;

  return (
    <svg
      viewBox="0 0 40 40"
      className={cn("h-5 w-5", className)}
      fill="none"
      {...getAccessibilityProps(label)}
      {...props}
    >
      <circle cx="20" cy="20" r="18" fill={INK_VARS[ink]} />
      <circle cx="20" cy="20" r="18" fill="url(#seal-highlight)" opacity="0.35" />
      <circle cx="20" cy="20" r="17.25" stroke="rgba(255,235,200,0.28)" strokeWidth="1.5" />
      <path
        d="M8 17.5C11.5 14 15.75 12.25 20.75 12.25C26.25 12.25 30.5 14.75 33 18.5"
        stroke="rgba(255,255,255,0.28)"
        strokeLinecap="round"
        strokeWidth="1.4"
      />
      <text
        x="20"
        y="24.25"
        textAnchor="middle"
        style={{ fontFamily: "var(--font-display)", fontWeight: 600 }}
        fill="var(--cream)"
        fontSize="17"
      >
        {initial.slice(0, 1).toUpperCase()}
      </text>
      <defs>
        <radialGradient id="seal-highlight" cx="0" cy="0" r="1" gradientTransform="translate(14 12) rotate(40) scale(18)">
          <stop stopColor="rgba(255,255,255,0.55)" />
          <stop offset="1" stopColor="rgba(255,255,255,0)" />
        </radialGradient>
      </defs>
    </svg>
  );
}
