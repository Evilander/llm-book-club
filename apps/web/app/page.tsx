"use client";

import { BookOpen, Sparkles } from "lucide-react";
import { useRouter } from "next/navigation";
import { BookShelf } from "@/components/book-shelf";

export default function Home() {
  const router = useRouter();

  function handleSelectBook(bookId: string) {
    router.push(`/books/${bookId}`);
  }

  return (
    <div className="container mx-auto px-4 py-8 animate-fade-up">
      <div className="max-w-6xl mx-auto">
        <div className="mb-10 overflow-hidden rounded-[2rem] border border-white/10 bg-[radial-gradient(circle_at_top_left,rgba(249,115,22,0.18),transparent_28%),radial-gradient(circle_at_bottom_right,rgba(244,63,94,0.14),transparent_26%),rgba(7,7,10,0.9)] px-6 py-8 shadow-2xl">
          <div className="grid gap-8 lg:grid-cols-[1.15fr_0.85fr] lg:items-end">
            <div className="max-w-3xl">
              <p className="text-xs uppercase tracking-[0.28em] text-primary/80 font-label">
                Daily reading ritual
              </p>
              <h2 className="mt-3 text-4xl font-bold tracking-tight text-white md:text-5xl font-serif">
                Make your shelf feel alive, seductive, and argumentative again.
              </h2>
              <p className="mt-4 max-w-2xl text-base leading-7 text-white/75">
                Browse the books you already own, open a live room around a chosen slice,
                and let a cast of readers turn the page back toward you with voice, evidence,
                chemistry, and real-time critical pressure.
              </p>
            </div>

            <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-1">
              <div className="rounded-2xl border border-white/10 bg-white/[0.04] px-4 py-4">
                <p className="text-xs uppercase tracking-[0.24em] text-white/45 font-label">Feels like</p>
                <p className="mt-2 text-sm leading-6 text-white/80">
                  A salon, not a chatbot.
                </p>
              </div>
              <div className="rounded-2xl border border-white/10 bg-white/[0.04] px-4 py-4">
                <p className="text-xs uppercase tracking-[0.24em] text-white/45 font-label">Built for</p>
                <p className="mt-2 text-sm leading-6 text-white/80">
                  Curiosity, close reading, disagreement, and pleasure.
                </p>
              </div>
              <div className="rounded-2xl border border-white/10 bg-white/[0.04] px-4 py-4">
                <p className="text-xs uppercase tracking-[0.24em] text-white/45 font-label">Modes</p>
                <p className="mt-2 text-sm leading-6 text-white/80">
                  Rigorous, playful, cozy, Socratic, and after-dark.
                </p>
              </div>
            </div>
          </div>
        </div>
        <BookShelf onSelectBook={handleSelectBook} />
      </div>
    </div>
  );
}
