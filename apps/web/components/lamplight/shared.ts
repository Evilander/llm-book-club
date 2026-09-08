import type { SVGProps } from "react";

export type LamplightInk = "sam" | "ellis" | "kit" | "sable" | "pencil";

export interface LamplightSvgProps extends Omit<SVGProps<SVGSVGElement>, "color"> {
  title?: string;
}

export const INK_VARS: Record<LamplightInk, string> = {
  sam: "var(--ink-sam)",
  ellis: "var(--ink-ellis)",
  kit: "var(--ink-kit)",
  sable: "var(--ink-sable)",
  pencil: "var(--ink-pencil)",
};

export function getAccessibilityProps(title?: string) {
  return title
    ? {
        role: "img" as const,
        "aria-label": title,
      }
    : {
        "aria-hidden": true,
      };
}
