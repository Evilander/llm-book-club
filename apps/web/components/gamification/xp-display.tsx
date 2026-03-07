"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import { Progress } from "@/components/ui/progress";

interface XPDisplayProps {
  xp: number;
  level: number;
  xpToNextLevel: number;
  className?: string;
  compact?: boolean;
}

export function XPDisplay({
  xp,
  level,
  xpToNextLevel,
  className,
  compact = false,
}: XPDisplayProps) {
  const xpInLevel = xp % 500;
  const progress = (xpInLevel / 500) * 100;

  if (compact) {
    return (
      <div className={cn("flex items-center gap-2", className)}>
        <div className="flex items-center justify-center w-8 h-8 rounded-full bg-gradient-to-br from-purple-500 to-pink-500 text-white text-sm font-bold">
          {level}
        </div>
        <div className="flex-1">
          <Progress value={progress} variant="xp" size="sm" />
        </div>
        <span className="text-xs text-muted-foreground">{xp} XP</span>
      </div>
    );
  }

  return (
    <div className={cn("space-y-2", className)}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="flex items-center justify-center w-12 h-12 rounded-full bg-gradient-to-br from-purple-500 to-pink-500 text-white text-lg font-bold shadow-lg">
            {level}
          </div>
          <div>
            <p className="text-sm font-medium">Level {level}</p>
            <p className="text-xs text-muted-foreground">{xp} total XP</p>
          </div>
        </div>
        <div className="text-right">
          <p className="text-sm font-medium">{xpToNextLevel} XP</p>
          <p className="text-xs text-muted-foreground">to level {level + 1}</p>
        </div>
      </div>
      <Progress value={progress} variant="xp" size="lg" />
    </div>
  );
}
