import { cn } from "@/lib/utils";

interface PromptChipRailProps {
  prompts: string[];
  onSelect: (prompt: string) => void;
  disabled?: boolean;
  variant?: "inline" | "stacked";
  className?: string;
}

export function PromptChipRail({
  prompts,
  onSelect,
  disabled,
  variant = "inline",
  className,
}: PromptChipRailProps) {
  return (
    <div
      className={cn(
        variant === "inline" ? "flex flex-wrap gap-2" : "space-y-2",
        className
      )}
    >
      {prompts.map((prompt) => (
        <button
          key={prompt}
          type="button"
          disabled={disabled}
          onClick={() => onSelect(prompt)}
          className={cn(
            "text-left text-xs leading-5 text-foreground/85 transition-colors",
            "hover:border-primary/40 hover:bg-primary/10 disabled:opacity-50",
            variant === "inline"
              ? "rounded-full border border-white/10 bg-white/[0.04] px-3 py-2"
              : "w-full rounded-2xl border border-white/10 bg-white/[0.03] px-3 py-3"
          )}
        >
          {prompt}
        </button>
      ))}
    </div>
  );
}
