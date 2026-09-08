import { Quote } from "lucide-react";
import { cn } from "@/lib/utils";
import { Card, CardContent } from "./card";

interface CitationData {
  chunk_id: string;
  text: string;
  char_start?: number | null;
  char_end?: number | null;
  verified?: boolean;
  match_type?: "exact" | "normalized" | "fuzzy" | null;
}

interface CitationCardProps {
  citation: CitationData;
  onSelect?: () => void;
  selected?: boolean;
  compact?: boolean;
}

function verificationDotColor(citation: CitationData) {
  if (citation.verified === false) return "bg-citation-unverified";
  if (citation.match_type === "exact") return "bg-citation-exact";
  if (citation.match_type === "fuzzy") return "bg-citation-fuzzy";
  return "bg-citation-normalized";
}

function verificationLabel(citation: CitationData) {
  if (citation.verified === false) return "Unverified";
  if (citation.match_type === "exact") return "Exact";
  if (citation.match_type === "normalized") return "Normalized";
  if (citation.match_type === "fuzzy") return "Fuzzy";
  return "Unchecked";
}

export function CitationCard({
  citation,
  onSelect,
  selected,
  compact = false,
}: CitationCardProps) {
  if (compact) {
    return (
      <button
        type="button"
        onClick={onSelect}
        className="flex w-full items-start gap-2 rounded-xl px-2 py-1 text-left text-xs transition-colors hover:bg-black/10"
      >
        <span
          className={cn(
            "mt-1 inline-block h-2 w-2 shrink-0 rounded-full",
            verificationDotColor(citation)
          )}
        />
        <span className="line-clamp-2 italic font-serif">
          &ldquo;{citation.text}&rdquo;{" "}
          <span className="not-italic text-muted-foreground font-label text-[10px]">
            {verificationLabel(citation)}
          </span>
        </span>
      </button>
    );
  }

  return (
    <Card
      className={cn(
        "border-white/10 transition-colors",
        selected ? "bg-primary/5 border-primary/30" : "bg-black/10"
      )}
    >
      <CardContent className="p-4">
        <div className="flex items-center gap-2 mb-2">
          <Quote className="h-3.5 w-3.5 text-primary" />
          <span
            className={cn(
              "inline-block h-2 w-2 rounded-full",
              verificationDotColor(citation)
            )}
          />
          <span className="text-[10px] font-label text-muted-foreground uppercase tracking-wider">
            {verificationLabel(citation)}
          </span>
        </div>
        <p className="text-sm italic font-serif">&ldquo;{citation.text}&rdquo;</p>
        <p className="mt-3 text-xs text-muted-foreground font-label">
          {citation.chunk_id.slice(0, 12)}...
          {citation.char_start != null && citation.char_end != null
            ? ` · chars ${citation.char_start}-${citation.char_end}`
            : ""}
        </p>
      </CardContent>
    </Card>
  );
}
