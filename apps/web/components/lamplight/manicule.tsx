import { cn } from "@/lib/utils";
import { getAccessibilityProps, type LamplightSvgProps } from "./shared";

export function Manicule({ className, title, ...props }: LamplightSvgProps) {
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
        y="43"
        textAnchor="middle"
        style={{ fontFamily: "var(--font-display)", fontStyle: "italic" }}
        fill="var(--ink-sam)"
        fontSize="42"
      >
        ☞
      </text>
    </svg>
  );
}
