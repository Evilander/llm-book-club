import { cn } from "@/lib/utils";
import { getAccessibilityProps, type LamplightSvgProps } from "./shared";

export function RuleOrnament({
  className,
  title,
  ...props
}: LamplightSvgProps) {
  return (
    <svg
      viewBox="0 0 220 24"
      className={cn("h-6 w-full", className)}
      fill="none"
      {...getAccessibilityProps(title)}
      {...props}
    >
      <path d="M0 12H88" stroke="url(#rule-left)" strokeWidth="1.2" />
      <path d="M132 12H220" stroke="url(#rule-right)" strokeWidth="1.2" />
      <path
        d="M110 4L114.5 12L110 20L101 16.5L101 7.5L110 4Z"
        fill="var(--foxed)"
        opacity="0.92"
      />
      <path
        d="M110 6.75L112.5 12L110 17.25L104.5 15L104.5 9L110 6.75Z"
        fill="var(--cream)"
        opacity="0.78"
      />
      <defs>
        <linearGradient id="rule-left" x1="0" y1="12" x2="88" y2="12" gradientUnits="userSpaceOnUse">
          <stop stopColor="transparent" />
          <stop offset="1" stopColor="rgba(196,154,74,0.45)" />
        </linearGradient>
        <linearGradient id="rule-right" x1="132" y1="12" x2="220" y2="12" gradientUnits="userSpaceOnUse">
          <stop stopColor="rgba(196,154,74,0.45)" />
          <stop offset="1" stopColor="transparent" />
        </linearGradient>
      </defs>
    </svg>
  );
}
