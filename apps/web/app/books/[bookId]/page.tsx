"use client";

import { use } from "react";
import { motion } from "motion/react";
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
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: "easeOut" }}
      className="container mx-auto px-4 py-8"
    >
      <div className="max-w-4xl mx-auto">
        <SessionSetup
          bookId={bookId}
          onBack={() => router.push("/")}
          onStartSession={(sessionId) =>
            router.push(`/books/${bookId}/sessions/${sessionId}`)
          }
        />
      </div>
    </motion.div>
  );
}
