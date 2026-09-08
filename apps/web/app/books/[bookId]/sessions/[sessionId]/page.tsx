"use client";

import { use } from "react";
import { DiscussionStage } from "@/components/discussion-stage";
import { useRouter } from "next/navigation";

export default function DiscussionPage({ params }: { params: Promise<{ bookId: string; sessionId: string }> }) {
  const { bookId, sessionId } = use(params);
  const router = useRouter();
  return <div className="discussion-page"><DiscussionStage key={sessionId} sessionId={sessionId} onBack={() => router.push(`/books/${bookId}`)} /></div>;
}
