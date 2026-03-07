"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { XPDisplay } from "./xp-display";
import { ReadingStreak, WeeklyActivity } from "./reading-streak";
import { AchievementGrid } from "./achievement-badge";
import { ReadingProgress } from "./reading-progress";

interface Achievement {
  id: string;
  name: string;
  description: string;
  xpReward: number;
  unlocked: boolean;
  progress?: number;
  target?: number;
}

interface ReadingUnit {
  id: string;
  title: string;
  orderIndex: number;
  status: "unread" | "in_progress" | "completed";
  readingTimeMin: number;
  tokenEstimate: number;
  narrativeThread?: string;
}

interface DailyActivity {
  date: string;
  readingTimeMin: number;
}

interface ReaderDashboardProps {
  bookTitle: string;
  xp: number;
  level: number;
  xpToNextLevel: number;
  currentStreak: number;
  longestStreak: number;
  achievements: Achievement[];
  units: ReadingUnit[];
  currentUnitId?: string;
  weeklyActivity: DailyActivity[];
  className?: string;
}

export function ReaderDashboard({
  bookTitle,
  xp,
  level,
  xpToNextLevel,
  currentStreak,
  longestStreak,
  achievements,
  units,
  currentUnitId,
  weeklyActivity,
  className,
}: ReaderDashboardProps) {
  const unlockedAchievements = achievements.filter((a) => a.unlocked);
  const nextAchievements = achievements
    .filter((a) => !a.unlocked && a.progress && a.target)
    .sort(
      (a, b) =>
        (b.progress! / b.target!) - (a.progress! / a.target!)
    )
    .slice(0, 3);

  return (
    <div className={cn("space-y-6", className)}>
      {/* Header with level and XP */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-xl">{bookTitle}</CardTitle>
          <CardDescription>Your reading journey</CardDescription>
        </CardHeader>
        <CardContent>
          <XPDisplay
            xp={xp}
            level={level}
            xpToNextLevel={xpToNextLevel}
          />
        </CardContent>
      </Card>

      {/* Reading streak */}
      <ReadingStreak
        currentStreak={currentStreak}
        longestStreak={longestStreak}
      />

      {/* Weekly activity */}
      <Card>
        <CardContent className="pt-6">
          <WeeklyActivity activities={weeklyActivity} />
        </CardContent>
      </Card>

      {/* Reading progress */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Reading Progress</CardTitle>
        </CardHeader>
        <CardContent>
          <ReadingProgress units={units} currentUnitId={currentUnitId} />
        </CardContent>
      </Card>

      {/* Achievements */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="text-lg">Achievements</CardTitle>
            <span className="text-sm text-muted-foreground">
              {unlockedAchievements.length} / {achievements.length}
            </span>
          </div>
        </CardHeader>
        <CardContent>
          <AchievementGrid achievements={achievements} />
        </CardContent>
      </Card>

      {/* Next achievements */}
      {nextAchievements.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Almost There...</CardTitle>
            <CardDescription>
              You&apos;re close to unlocking these
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              {nextAchievements.map((achievement) => (
                <div
                  key={achievement.id}
                  className="flex items-center gap-4"
                >
                  <div className="flex-1">
                    <p className="text-sm font-medium">{achievement.name}</p>
                    <p className="text-xs text-muted-foreground">
                      {achievement.description}
                    </p>
                  </div>
                  <div className="text-right">
                    <p className="text-sm font-medium">
                      {achievement.progress} / {achievement.target}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      +{achievement.xpReward} XP
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
