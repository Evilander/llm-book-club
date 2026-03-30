"use client";

import { use } from "react";
import { SessionSetup } from "@/components/session-setup";
import { useRouter } from "next/navigation";

export default function BookSetupPage({
  params,
}: {
  params: Promise<{ bookId: string }>;
}) {
  const { bookId } = use(params);
  const router = useRouter();

  return (
    <div className="container mx-auto px-4 py-8 animate-fade-up">
      <div className="max-w-4xl mx-auto">
        <SessionSetup
          bookId={bookId}
          onBack={() => router.push("/")}
          onStartSession={(sessionId) =>
            router.push(`/books/${bookId}/sessions/${sessionId}`)
          }
        />
      </div>
    </div>
  );
}
