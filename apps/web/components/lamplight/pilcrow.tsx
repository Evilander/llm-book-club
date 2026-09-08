import { cn } from "@/lib/utils";
import { getAccessibilityProps, type LamplightSvgProps } from "./shared";

export function Pilcrow({ className, title, ...props }: LamplightSvgProps) {
  return (
    <svg
      viewBox="0 0 64 64"
      className={cn("h-5 w-5", className)}
      fill="none"
      {...getAccessibilityProps(title)}
      {...props}
    >
      <text
        x="32"
        y="45"
        textAnchor="middle"
        style={{ fontFamily: "var(--font-display)", fontWeight: 600 }}
        fill="var(--brass)"
        fontSize="42"
      >
        ¶
      </text>
    </svg>
  );
}
