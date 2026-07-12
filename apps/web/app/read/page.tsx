import type { Metadata } from "next";
import { Suspense } from "react";
import { BookOpenText } from "lucide-react";
import { ReadingRoom } from "@/components/reader/reading-room";
import "./reader.css";

export const metadata: Metadata = {
  title: "Reading Room · LLM Book Club",
  description: "Read from your private library and bring exact passages into a grounded discussion.",
};

export const dynamic = "force-dynamic";

function ReaderFallback() {
  return (
    <div className="reader-shell reader-empty-state">
      <BookOpenText className="h-9 w-9 animate-pulse" />
      <h1>Opening the reading room…</h1>
    </div>
  );
}

export default function ReadPage() {
  return (
    <Suspense fallback={<ReaderFallback />}>
      <ReadingRoom />
    </Suspense>
  );
}
