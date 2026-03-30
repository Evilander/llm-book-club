"use client";

import { use } from "react";
import { DiscussionStage } from "@/components/discussion-stage";
import { useRouter } from "next/navigation";

export default function DiscussionPage({
  params,
}: {
  params: Promise<{ bookId: string; sessionId: string }>;
}) {
  const { sessionId } = use(params);
  const router = useRouter();

  return (
    <div className="h-[calc(100vh-73px)] animate-fade-in">
      <DiscussionStage sessionId={sessionId} onBack={() => router.back()} />
    </div>
  );
}
