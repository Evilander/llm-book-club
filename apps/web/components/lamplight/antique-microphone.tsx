import { cn } from "@/lib/utils";
import { getAccessibilityProps, type LamplightSvgProps } from "./shared";

export function AntiqueMicrophone({
  className,
  title,
  ...props
}: LamplightSvgProps) {
  return (
    <svg
      viewBox="0 0 72 72"
      className={cn("h-8 w-8", className)}
      fill="none"
      {...getAccessibilityProps(title || "Antique microphone")}
      {...props}
    >
      <rect x="20" y="8" width="32" height="30" rx="14" fill="var(--ink-ellis)" stroke="var(--brass)" strokeWidth="2" />
      <path d="M27 16H45" stroke="var(--cream)" strokeLinecap="round" strokeWidth="1.4" opacity="0.9" />
      <path d="M25 21H47" stroke="var(--cream)" strokeLinecap="round" strokeWidth="1.4" opacity="0.85" />
      <path d="M25 26H47" stroke="var(--cream)" strokeLinecap="round" strokeWidth="1.4" opacity="0.8" />
      <path d="M27 31H45" stroke="var(--cream)" strokeLinecap="round" strokeWidth="1.4" opacity="0.75" />
      <path d="M36 38V52" stroke="var(--brass)" strokeLinecap="round" strokeWidth="2.2" />
      <path d="M26 48C28.5 51.3333 31.8333 53 36 53C40.1667 53 43.5 51.3333 46 48" stroke="var(--brass)" strokeLinecap="round" strokeWidth="2" />
      <path d="M24 60H48" stroke="var(--ink-pencil)" strokeLinecap="round" strokeWidth="2.6" />
      <path d="M36 52V60" stroke="var(--ink-pencil)" strokeLinecap="round" strokeWidth="2.2" />
    </svg>
  );
}
