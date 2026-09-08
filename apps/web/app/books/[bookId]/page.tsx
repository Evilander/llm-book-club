"use client";

import { use } from "react";
import { useRouter } from "next/navigation";
import { BookOverview } from "@/components/book-overview";

export default function BookSetupPage({ params }: { params: Promise<{ bookId: string }> }) {
  const { bookId } = use(params);
  const router = useRouter();
  return <BookOverview bookId={bookId} onStartSession={(sessionId) => router.push(`/books/${bookId}/sessions/${sessionId}`)} />;
}
