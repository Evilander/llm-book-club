import type { Metadata } from "next";
import { Suspense } from "react";
import { Headphones } from "lucide-react";
import { AudiobookRoom } from "@/components/audiobook-room";

export const metadata: Metadata = {
  title: "Listening Room · LLM Book Club",
  description: "Listen to local audiobooks with synced progress and chapter controls.",
};

export const dynamic = "force-dynamic";

function ListeningFallback() {
  return (
    <div className="grid min-h-screen place-items-center bg-background text-muted-foreground">
      <div className="text-center">
        <Headphones className="mx-auto mb-3 h-8 w-8 animate-pulse text-primary" />
        Opening the listening room…
      </div>
    </div>
  );
}

export default function ListenPage() {
  return (
    <Suspense fallback={<ListeningFallback />}>
      <AudiobookRoom />
    </Suspense>
  );
}
