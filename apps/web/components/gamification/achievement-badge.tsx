"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

interface Achievement {
  id: string;
  name: string;
  description: string;
  xpReward: number;
  unlocked: boolean;
  progress?: number;
  target?: number;
}

interface AchievementBadgeProps {
  achievement: Achievement;
  size?: "sm" | "md" | "lg";
  showProgress?: boolean;
  className?: string;
}

const ACHIEVEMENT_ICONS: Record<string, string> = {
  first_insight: "💡",
  bookworm_7: "📚",
  bookworm_30: "🏆",
  completionist: "✅",
  speed_reader: "⚡",
  night_owl: "🦉",
  early_bird: "🐦",
  marathon_reader: "🏃",
  quiz_master: "🎯",
  deep_reader: "🔍",
  connection_hunter: "🔗",
  theme_tracker: "🎭",
};

export function AchievementBadge({
  achievement,
  size = "md",
  showProgress = false,
  className,
}: AchievementBadgeProps) {
  const icon = ACHIEVEMENT_ICONS[achievement.id] || "🏅";
  const progress =
    achievement.progress && achievement.target
      ? (achievement.progress / achievement.target) * 100
      : 0;

  const sizeClasses = {
    sm: "w-12 h-12 text-xl",
    md: "w-16 h-16 text-2xl",
    lg: "w-20 h-20 text-3xl",
  };

  return (
    <div
      className={cn(
        "relative flex flex-col items-center gap-1",
        className
      )}
    >
      <div
        className={cn(
          "relative flex items-center justify-center rounded-full transition-all",
          sizeClasses[size],
          achievement.unlocked
            ? "bg-gradient-to-br from-yellow-400 to-orange-500 shadow-lg"
            : "bg-gray-200 dark:bg-gray-700 grayscale opacity-50"
        )}
      >
        <span className={achievement.unlocked ? "" : "opacity-50"}>
          {icon}
        </span>
        {showProgress && !achievement.unlocked && progress > 0 && (
          <svg
            className="absolute inset-0 -rotate-90"
            viewBox="0 0 100 100"
          >
            <circle
              cx="50"
              cy="50"
              r="45"
              fill="none"
              stroke="currentColor"
              strokeWidth="4"
              className="text-gray-300 dark:text-gray-600"
            />
            <circle
              cx="50"
              cy="50"
              r="45"
              fill="none"
              stroke="currentColor"
              strokeWidth="4"
              strokeDasharray={`${progress * 2.83} 283`}
              className="text-purple-500"
            />
          </svg>
        )}
      </div>
      <span
        className={cn(
          "text-xs text-center font-medium max-w-[80px] line-clamp-2",
          !achievement.unlocked && "text-muted-foreground"
        )}
      >
        {achievement.name}
      </span>
      {showProgress && !achievement.unlocked && (
        <span className="text-[10px] text-muted-foreground">
          {achievement.progress}/{achievement.target}
        </span>
      )}
    </div>
  );
}

interface AchievementGridProps {
  achievements: Achievement[];
  className?: string;
}

export function AchievementGrid({
  achievements,
  className,
}: AchievementGridProps) {
  const unlockedFirst = [...achievements].sort(
    (a, b) => (b.unlocked ? 1 : 0) - (a.unlocked ? 1 : 0)
  );

  return (
    <div
      className={cn(
        "grid grid-cols-4 sm:grid-cols-6 gap-4",
        className
      )}
    >
      {unlockedFirst.map((achievement) => (
        <AchievementBadge
          key={achievement.id}
          achievement={achievement}
          size="md"
          showProgress
        />
      ))}
    </div>
  );
}
