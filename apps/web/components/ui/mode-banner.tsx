import { cn } from "@/lib/utils";

interface ModeBannerProps {
  variant: "after-dark" | "standard";
  title: string;
  description: string;
  className?: string;
  children?: React.ReactNode;
}

export function ModeBanner({
  variant,
  title,
  description,
  className,
  children,
}: ModeBannerProps) {
  if (variant === "standard") return null;

  return (
    <div
      className={cn(
        "rounded-2xl px-4 py-3 text-sm",
        variant === "after-dark" &&
          "border border-rose-500/20 bg-[radial-gradient(circle_at_top_left,rgba(244,63,94,0.16),transparent_35%),rgba(20,16,22,0.92)] text-rose-50/90",
        className
      )}
    >
      <p className="font-medium text-white font-label text-xs uppercase tracking-wider">
        {title}
      </p>
      <p className="mt-1 leading-6 text-rose-50/80">{description}</p>
      {children}
    </div>
  );
}
