import { cn } from "@/lib/utils";

interface ScreenIntroProps {
  label: string;
  title: string;
  description?: string;
  className?: string;
  variant?: "default" | "after-dark";
  children?: React.ReactNode;
}

export function ScreenIntro({
  label,
  title,
  description,
  className,
  variant = "default",
  children,
}: ScreenIntroProps) {
  return (
    <div className={cn("space-y-3", className)}>
      <p
        className={cn(
          "text-xs uppercase tracking-[0.28em] font-label",
          variant === "after-dark" ? "text-rose-200/80" : "text-primary/80"
        )}
      >
        {label}
      </p>
      <h2
        className={cn(
          "text-2xl font-semibold font-serif md:text-3xl",
          variant === "after-dark" ? "text-white" : "text-white"
        )}
      >
        {title}
      </h2>
      {description && (
        <p className="max-w-2xl text-sm leading-7 text-white/75">{description}</p>
      )}
      {children}
    </div>
  );
}
