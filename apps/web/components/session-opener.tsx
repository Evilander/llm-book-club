"use client";

import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { BookOpen, Eye, Flame, Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";

interface SessionOpenerProps {
  bookTitle: string;
  mode: string;
  style?: string | null;
  sectionTitle?: string | null;
  isAfterDark?: boolean;
  onComplete: () => void;
}

const CAST = [
  {
    role: "facilitator",
    name: "Sam",
    line: "I'll keep the room moving and the questions sharp.",
    icon: Sparkles,
    color: "text-amber-400",
  },
  {
    role: "close_reader",
    name: "Ellis",
    line: "I'll slow down for the language that matters.",
    icon: Eye,
    color: "text-teal-400",
  },
  {
    role: "skeptic",
    name: "Kit",
    line: "I'll make sure every claim earns its place.",
    icon: Flame,
    color: "text-rose-400",
  },
];

const AFTER_DARK_CAST_MEMBER = {
  role: "after_dark_guide",
  name: "Sable",
  line: "I'll trace what the page makes you feel before it tells you why.",
  icon: Sparkles,
  color: "text-fuchsia-300",
};

export function SessionOpener({
  bookTitle,
  mode,
  style,
  sectionTitle,
  isAfterDark,
  onComplete,
}: SessionOpenerProps) {
  const [phase, setPhase] = useState(0);
  const cast = isAfterDark ? [...CAST, AFTER_DARK_CAST_MEMBER] : CAST;

  useEffect(() => {
    const timers = [
      setTimeout(() => setPhase(1), 400),
      setTimeout(() => setPhase(2), 1200),
      setTimeout(() => setPhase(3), 2000),
      setTimeout(() => setPhase(4), 2800),
      setTimeout(() => setPhase(5), isAfterDark ? 3600 : 3200),
      setTimeout(() => onComplete(), isAfterDark ? 4800 : 4200),
    ];
    return () => timers.forEach(clearTimeout);
  }, [isAfterDark, onComplete]);

  return (
    <div
      className={cn(
        "fixed inset-0 z-[60] flex items-center justify-center",
        isAfterDark
          ? "bg-[radial-gradient(circle_at_center,rgba(244,63,94,0.08),rgba(12,10,9,0.98)_70%)]"
          : "bg-[radial-gradient(circle_at_center,rgba(217,119,6,0.08),rgba(12,10,9,0.98)_70%)]"
      )}
    >
      <div className="max-w-2xl w-full px-6 text-center space-y-8">
        <AnimatePresence>
          {phase >= 0 && (
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, ease: "easeOut" }}
            >
              <div className="flex items-center justify-center gap-2 mb-4">
                <BookOpen className={cn("w-5 h-5", isAfterDark ? "text-rose-400" : "text-primary")} />
                <span className="text-xs uppercase tracking-[0.3em] font-label text-muted-foreground">
                  {isAfterDark ? "After-dark room" : "Opening room"}
                </span>
              </div>
            </motion.div>
          )}

          {phase >= 1 && (
            <motion.h2
              key="title"
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ duration: 0.8, ease: "easeOut" }}
              className="text-3xl md:text-4xl font-bold font-serif text-white"
            >
              {bookTitle}
            </motion.h2>
          )}

          {phase >= 2 && sectionTitle && (
            <motion.p
              key="section"
              initial={{ opacity: 0 }}
              animate={{ opacity: 0.7 }}
              transition={{ duration: 0.5 }}
              className="text-sm text-muted-foreground font-label"
            >
              Tonight&apos;s slice: {sectionTitle}
            </motion.p>
          )}
        </AnimatePresence>

        <div className="space-y-3 mt-8">
          {cast.map((member, i) => (
            <AnimatePresence key={member.role}>
              {phase >= i + 2 && (
                <motion.div
                  initial={{ opacity: 0, x: -20 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ duration: 0.4, delay: 0.1, ease: "easeOut" }}
                  className="flex items-center gap-3 rounded-2xl border border-white/8 bg-white/[0.02] px-4 py-3"
                >
                  <div className={cn("flex h-8 w-8 shrink-0 items-center justify-center rounded-xl",
                    member.role === "after_dark_guide" ? "bg-fuchsia-500/10" :
                    member.role === "facilitator" ? "bg-amber-500/10" :
                    member.role === "close_reader" ? "bg-teal-500/10" : "bg-rose-500/10"
                  )}>
                    <member.icon className={cn("h-4 w-4", member.color)} />
                  </div>
                  <div className="text-left">
                    <p className={cn("text-sm font-medium", member.color)}>{member.name}</p>
                    <p className="text-xs text-muted-foreground">{member.line}</p>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          ))}
        </div>

        <AnimatePresence>
          {phase >= (isAfterDark ? 5 : 4) && (
            <motion.div
              key="entering"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.4 }}
              className="pt-4"
            >
              <motion.div
                animate={{ opacity: [0.4, 1, 0.4] }}
                transition={{ duration: 1.5, repeat: Infinity }}
                className={cn("text-sm font-label", isAfterDark ? "text-rose-300/60" : "text-primary/60")}
              >
                Entering the room...
              </motion.div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
