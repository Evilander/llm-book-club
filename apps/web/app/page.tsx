"use client";

import { useMemo } from "react";
import { useRouter } from "next/navigation";
import { motion } from "motion/react";
import { BookShelf } from "@/components/book-shelf";

function getTimeOfDayGreeting(): { label: string; headline: string; body: string } {
  const hour = new Date().getHours();
  if (hour >= 5 && hour < 12) {
    return {
      label: "Morning reading",
      headline: "Start the day with a page that talks back.",
      body: "Morning sessions tend toward precision — the mind is fresh, the room can push harder. Pick a slice and let the cast wake up with you.",
    };
  }
  if (hour >= 12 && hour < 17) {
    return {
      label: "Afternoon session",
      headline: "Open a room while the light is still good.",
      body: "Afternoon is for themes and big-picture thinking. The shelf is ready when you are.",
    };
  }
  if (hour >= 17 && hour < 21) {
    return {
      label: "Evening ritual",
      headline: "The shelf has been waiting for you.",
      body: "Evening sessions are where the best conversations happen — unhurried, curious, ready to argue about what the page is really doing.",
    };
  }
  return {
    label: "Late-night reading",
    headline: "The room is quieter now. The books are louder.",
    body: "Late-night sessions can go deeper, get cosier, or get hotter. The after-dark room is open if you want it.",
  };
}

export default function Home() {
  const router = useRouter();
  const greeting = useMemo(getTimeOfDayGreeting, []);

  function handleSelectBook(bookId: string) {
    router.push(`/books/${bookId}`);
  }

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="max-w-6xl mx-auto">
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, ease: "easeOut" }}
          className="mb-10 overflow-hidden rounded-[2rem] border border-white/10 bg-[radial-gradient(circle_at_top_left,rgba(249,115,22,0.18),transparent_28%),radial-gradient(circle_at_bottom_right,rgba(244,63,94,0.14),transparent_26%),rgba(7,7,10,0.9)] px-6 py-8 shadow-2xl"
        >
          <div className="max-w-3xl">
            <motion.p
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.2 }}
              className="text-xs uppercase tracking-[0.28em] text-primary/80 font-label"
            >
              {greeting.label}
            </motion.p>
            <motion.h2
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.3, duration: 0.5 }}
              className="mt-3 text-3xl font-bold tracking-tight text-white md:text-4xl lg:text-5xl font-serif"
            >
              {greeting.headline}
            </motion.h2>
            <motion.p
              initial={{ opacity: 0 }}
              animate={{ opacity: 0.75 }}
              transition={{ delay: 0.5, duration: 0.4 }}
              className="mt-4 max-w-2xl text-base leading-7 text-white/75"
            >
              {greeting.body}
            </motion.p>
          </div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.4, duration: 0.5 }}
        >
          <BookShelf onSelectBook={handleSelectBook} />
        </motion.div>
      </div>
    </div>
  );
}
