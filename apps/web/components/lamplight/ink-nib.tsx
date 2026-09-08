import { cn } from "@/lib/utils";
import { getAccessibilityProps, type LamplightSvgProps } from "./shared";

interface InkNibProps extends LamplightSvgProps {
  blinking?: boolean;
}

export function InkNib({
  blinking = false,
  className,
  title,
  ...props
}: InkNibProps) {
  return (
    <svg
      viewBox="0 0 64 64"
      className={cn("h-6 w-6", className)}
      fill="none"
      {...getAccessibilityProps(title || "Ink nib")}
      {...props}
    >
      <path
        d="M32 7L50 22L39 51L32 57L25 51L14 22L32 7Z"
        fill="var(--ink-ellis)"
        stroke="var(--brass)"
        strokeWidth="1.6"
      />
      <path d="M32 14V46" stroke="var(--cream)" strokeLinecap="round" strokeWidth="1.4" />
      <path d="M22 28H42" stroke="var(--cream)" strokeLinecap="round" strokeWidth="1.1" />
      <path
        d="M32 45C34.2 45 36 43.2 36 41C36 38.8 34.2 37 32 37C29.8 37 28 38.8 28 41C28 43.2 29.8 45 32 45Z"
        fill="rgba(255,255,255,0.08)"
      />
      <path d="M32 45L28 53H36L32 45Z" fill="var(--cream)" opacity="0.92" />
      <circle
        cx="49"
        cy="16"
        r="4"
        fill="var(--lamp-glow)"
        className={cn(blinking && "motion-safe:animate-pulse motion-reduce:animate-none")}
      />
    </svg>
  );
}
