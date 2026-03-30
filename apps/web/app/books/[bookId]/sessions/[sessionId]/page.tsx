"use client";

import { use, useCallback, useEffect, useState } from "react";
import { DiscussionStage } from "@/components/discussion-stage";
import { SessionOpener } from "@/components/session-opener";
import { useRouter } from "next/navigation";
import { API_BASE } from "@/lib/utils";

export default function DiscussionPage({
  params,
}: {
  params: Promise<{ bookId: string; sessionId: string }>;
}) {
  const { bookId, sessionId } = use(params);
  const router = useRouter();
  const [showOpener, setShowOpener] = useState(true);
  const [openerData, setOpenerData] = useState<{
    bookTitle: string;
    mode: string;
    style: string | null;
    sectionTitle: string | null;
    isAfterDark: boolean;
  } | null>(null);

  useEffect(() => {
    async function loadOpenerData() {
      try {
        const [sessionRes, bookRes] = await Promise.all([
          fetch(`${API_BASE}/v1/sessions/${sessionId}`),
          fetch(`${API_BASE}/v1/books/${bookId}`),
        ]);
        const session = await sessionRes.json();
        const book = await bookRes.json();
        const style = session.preferences?.discussion_style || null;
        setOpenerData({
          bookTitle: book.title || "Your book",
          mode: session.mode || "conversation",
          style,
          sectionTitle: session.sections?.[0]?.title || null,
          isAfterDark: style === "sexy",
        });
      } catch {
        setShowOpener(false);
      }
    }
    loadOpenerData();
  }, [bookId, sessionId]);

  const handleOpenerComplete = useCallback(() => setShowOpener(false), []);

  if (showOpener && openerData) {
    return (
      <SessionOpener
        bookTitle={openerData.bookTitle}
        mode={openerData.mode}
        style={openerData.style}
        sectionTitle={openerData.sectionTitle}
        isAfterDark={openerData.isAfterDark}
        onComplete={handleOpenerComplete}
      />
    );
  }

  return (
    <div className="h-[calc(100vh-73px)] animate-fade-in">
      <DiscussionStage sessionId={sessionId} onBack={() => router.back()} />
    </div>
  );
}
