import { cn } from "@/lib/utils";
import { getAccessibilityProps, type LamplightSvgProps } from "./shared";

interface WaxSealProps extends LamplightSvgProps {
  sealed?: boolean;
}

export function WaxSeal({
  sealed = true,
  className,
  title,
  ...props
}: WaxSealProps) {
  return (
    <svg
      viewBox="0 0 64 64"
      className={cn("h-10 w-10", className)}
      fill="none"
      {...getAccessibilityProps(title || (sealed ? "Wax seal intact" : "Wax seal broken"))}
      {...props}
    >
      <path
        d="M32 7L39 12L47 10L52 17L58 22L56 30L59 38L54 45L52 53L43 55L37 59L29 56L21 58L15 52L7 49L8 40L5 32L9 25L11 17L20 14L26 9L32 7Z"
        fill="url(#wax-fill)"
        stroke="rgba(88,18,28,0.8)"
        strokeWidth="1.4"
      />
      <circle cx="32" cy="31.5" r="15.25" fill="rgba(255,255,255,0.08)" />
      <path
        d="M24 26.5C27 24 29.75 22.75 32.25 22.75C35.75 22.75 39 24.5 41 27.5"
        stroke="rgba(255,255,255,0.26)"
        strokeLinecap="round"
        strokeWidth="1.6"
      />
      {sealed ? (
        <>
          <circle cx="32" cy="32" r="10.75" stroke="rgba(255,230,200,0.22)" strokeWidth="1.25" />
          <text
            x="32"
            y="36"
            textAnchor="middle"
            style={{ fontFamily: "var(--font-display)", fontWeight: 700 }}
            fill="var(--cream)"
            fontSize="14"
          >
            18+
          </text>
        </>
      ) : (
        <>
          <path
            d="M23 18L29 27L24.5 34L31 41L28 49"
            stroke="rgba(255,235,200,0.9)"
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth="2.2"
          />
          <path
            d="M41 17L36 25L39.5 31L33 39L35 49"
            stroke="rgba(255,235,200,0.82)"
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth="2.2"
          />
        </>
      )}
      <defs>
        <radialGradient id="wax-fill" cx="0" cy="0" r="1" gradientTransform="translate(26 20) rotate(36) scale(34)">
          <stop stopColor="#C65B3F" />
          <stop offset="0.62" stopColor="#8B2231" />
          <stop offset="1" stopColor="#5B101C" />
        </radialGradient>
      </defs>
    </svg>
  );
}
