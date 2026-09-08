import { BookOpen, Clock, MessageCircle, Quote, Sparkles } from "lucide-react";
import { Badge } from "./badge";
import { Card, CardContent } from "./card";
import { cn } from "@/lib/utils";

interface SessionRecapProps {
  bookTitle: string;
  mode: string;
  style?: string | null;
  messageCount: number;
  duration: number;
  topCitations?: Array<{ text: string; verified?: boolean }>;
  className?: string;
}

function formatDuration(seconds: number) {
  const mins = Math.floor(seconds / 60);
  if (mins < 1) return "< 1 min";
  if (mins < 60) return `${mins} min`;
  const hours = Math.floor(mins / 60);
  const remaining = mins % 60;
  return remaining > 0 ? `${hours}h ${remaining}m` : `${hours}h`;
}

export function SessionRecap({
  bookTitle,
  mode,
  style,
  messageCount,
  duration,
  topCitations = [],
  className,
}: SessionRecapProps) {
  return (
    <Card className={cn("border-white/10 bg-black/20 overflow-hidden", className)}>
      <CardContent className="p-5">
        <div className="flex items-start justify-between gap-3 mb-4">
          <div>
            <p className="text-xs uppercase tracking-[0.28em] text-primary/80 font-label">
              Session recap
            </p>
            <h4 className="mt-1 text-base font-semibold font-serif line-clamp-1">
              {bookTitle}
            </h4>
          </div>
          <Sparkles className="h-4 w-4 text-primary shrink-0" />
        </div>

        <div className="flex flex-wrap gap-2 mb-4">
          <Badge variant="secondary" className="gap-1">
            <BookOpen className="w-3 h-3" />
            {mode.replace("_", " ")}
          </Badge>
          {style && (
            <Badge variant="secondary" className="gap-1">
              {style.replace("_", " ")}
            </Badge>
          )}
          <Badge variant="outline" className="gap-1">
            <MessageCircle className="w-3 h-3" />
            {messageCount} turns
          </Badge>
          <Badge variant="outline" className="gap-1">
            <Clock className="w-3 h-3" />
            {formatDuration(duration)}
          </Badge>
        </div>

        {topCitations.length > 0 && (
          <div className="space-y-2">
            <p className="flex items-center gap-1 text-xs font-medium text-muted-foreground font-label">
              <Quote className="h-3 w-3" />
              Key passages
            </p>
            {topCitations.slice(0, 3).map((citation, i) => (
              <div
                key={i}
                className="rounded-xl border border-white/8 bg-white/[0.02] px-3 py-2 text-xs italic font-serif leading-5 text-foreground/80"
              >
                &ldquo;{citation.text.length > 120
                  ? citation.text.slice(0, 120) + "..."
                  : citation.text}&rdquo;
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
