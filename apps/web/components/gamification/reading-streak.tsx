"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

interface ReadingStreakProps {
  currentStreak: number;
  longestStreak: number;
  className?: string;
}

export function ReadingStreak({
  currentStreak,
  longestStreak,
  className,
}: ReadingStreakProps) {
  const getStreakEmoji = (streak: number) => {
    if (streak >= 30) return "🔥🔥🔥";
    if (streak >= 14) return "🔥🔥";
    if (streak >= 7) return "🔥";
    if (streak >= 3) return "✨";
    return "📖";
  };

  const getStreakMessage = (streak: number) => {
    if (streak === 0) return "Start your streak today!";
    if (streak === 1) return "Day 1! Keep it going!";
    if (streak < 7) return "Building momentum...";
    if (streak === 7) return "One week! Amazing!";
    if (streak < 30) return "You're on fire!";
    if (streak === 30) return "30 days! Legendary!";
    return "Incredible dedication!";
  };

  return (
    <div
      className={cn(
        "flex items-center gap-4 p-4 rounded-lg bg-gradient-to-r from-orange-50 to-red-50 dark:from-orange-950/20 dark:to-red-950/20 border border-orange-200 dark:border-orange-800",
        className
      )}
    >
      <div className="text-4xl">{getStreakEmoji(currentStreak)}</div>
      <div className="flex-1">
        <div className="flex items-baseline gap-2">
          <span className="text-3xl font-bold text-orange-600 dark:text-orange-400">
            {currentStreak}
          </span>
          <span className="text-sm text-muted-foreground">day streak</span>
        </div>
        <p className="text-sm text-muted-foreground">
          {getStreakMessage(currentStreak)}
        </p>
      </div>
      {longestStreak > currentStreak && (
        <div className="text-right">
          <p className="text-xs text-muted-foreground">Best streak</p>
          <p className="text-lg font-semibold">{longestStreak} days</p>
        </div>
      )}
    </div>
  );
}

interface WeeklyActivityProps {
  activities: { date: string; readingTimeMin: number }[];
  className?: string;
}

export function WeeklyActivity({
  activities,
  className,
}: WeeklyActivityProps) {
  const days = ["S", "M", "T", "W", "T", "F", "S"];
  const today = new Date();

  // Create array of last 7 days
  const weekData = Array.from({ length: 7 }, (_, i) => {
    const date = new Date(today);
    date.setDate(date.getDate() - (6 - i));
    const dateStr = date.toISOString().split("T")[0];
    const activity = activities.find((a) => a.date === dateStr);
    return {
      day: days[date.getDay()],
      readingTime: activity?.readingTimeMin || 0,
      isToday: i === 6,
    };
  });

  const maxTime = Math.max(...weekData.map((d) => d.readingTime), 30);

  return (
    <div className={cn("space-y-2", className)}>
      <p className="text-sm font-medium">This Week</p>
      <div className="flex items-end justify-between gap-1 h-16">
        {weekData.map((day, i) => (
          <div key={i} className="flex flex-col items-center gap-1 flex-1">
            <div
              className={cn(
                "w-full rounded-t transition-all",
                day.readingTime > 0
                  ? "bg-green-500"
                  : "bg-gray-200 dark:bg-gray-700",
                day.isToday && "ring-2 ring-green-400 ring-offset-1"
              )}
              style={{
                height: `${Math.max(4, (day.readingTime / maxTime) * 48)}px`,
              }}
            />
            <span
              className={cn(
                "text-[10px]",
                day.isToday
                  ? "font-bold text-green-600"
                  : "text-muted-foreground"
              )}
            >
              {day.day}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
