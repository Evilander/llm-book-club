"use client";

import { useState } from "react";
import { BookOpen, Sparkles } from "lucide-react";
import { BookShelf } from "@/components/book-shelf";
import { SessionSetup } from "@/components/session-setup";
import { DiscussionStage } from "@/components/discussion-stage";

type View = "library" | "setup" | "discussion";

export default function Home() {
  const [view, setView] = useState<View>("library");
  const [selectedBookId, setSelectedBookId] = useState<string | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);

  function handleSelectBook(bookId: string) {
    setSelectedBookId(bookId);
    setView("setup");
  }

  function handleStartSession(newSessionId: string) {
    setSessionId(newSessionId);
    setView("discussion");
  }

  function handleBack() {
    if (view === "discussion") {
      setView("setup");
      setSessionId(null);
    } else if (view === "setup") {
      setView("library");
      setSelectedBookId(null);
    }
  }

  return (
    <div className="min-h-screen flex flex-col relative">
      {/* Ambient background */}
      <div className="ambient-bg" />

      {/* Header */}
      <header className="sticky top-0 z-50 glass border-b border-border/50">
        <div className="container mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="relative">
                <div className="w-11 h-11 rounded-xl gradient-primary flex items-center justify-center shadow-glow">
                  <BookOpen className="w-5 h-5 text-white" />
                </div>
                <div className="absolute -top-1 -right-1 w-4 h-4 rounded-full bg-emerald-500 border-2 border-background flex items-center justify-center">
                  <Sparkles className="w-2 h-2 text-white" />
                </div>
              </div>
              <div>
                <h1 className="text-xl font-bold tracking-tight font-serif">
                  <span className="gradient-text">LLM Book Club</span>
                </h1>
                <p className="text-xs text-muted-foreground font-label tracking-wide">
                  Open a book. Hear it think back.
                </p>
              </div>
            </div>

            {/* Future: User menu, settings, etc. */}
            <div className="flex items-center gap-2">
              {view !== "library" && (
                <span className="text-xs text-muted-foreground px-3 py-1.5 rounded-full bg-secondary/50">
                  {view === "setup" ? "Setting up session" : "In discussion"}
                </span>
              )}
            </div>
          </div>
        </div>
      </header>

      {/* Main content */}
      <main className="flex-1">
        {view === "library" && (
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
        )}

        {view === "setup" && selectedBookId && (
          <div className="container mx-auto px-4 py-8 animate-fade-up">
            <div className="max-w-4xl mx-auto">
              <SessionSetup
                bookId={selectedBookId}
                onBack={handleBack}
                onStartSession={handleStartSession}
              />
            </div>
          </div>
        )}

        {view === "discussion" && sessionId && (
          <div className="h-[calc(100vh-73px)] animate-fade-in">
            <DiscussionStage sessionId={sessionId} onBack={handleBack} />
          </div>
        )}
      </main>
    </div>
  );
}
