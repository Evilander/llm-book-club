"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import { Progress } from "@/components/ui/progress";

interface ReadingUnit {
  id: string;
  title: string;
  orderIndex: number;
  status: "unread" | "in_progress" | "completed";
  readingTimeMin: number;
  tokenEstimate: number;
  narrativeThread?: string;
}

interface ReadingProgressProps {
  units: ReadingUnit[];
  currentUnitId?: string;
  className?: string;
  compact?: boolean;
}

export function ReadingProgress({
  units,
  currentUnitId,
  className,
  compact = false,
}: ReadingProgressProps) {
  const completedCount = units.filter((u) => u.status === "completed").length;
  const totalCount = units.length;
  const progressPct = totalCount > 0 ? (completedCount / totalCount) * 100 : 0;

  const totalReadingTime = units.reduce(
    (acc, u) => acc + (u.readingTimeMin || 0),
    0
  );
  const completedReadingTime = units
    .filter((u) => u.status === "completed")
    .reduce((acc, u) => acc + (u.readingTimeMin || 0), 0);

  if (compact) {
    return (
      <div className={cn("space-y-1", className)}>
        <div className="flex items-center justify-between text-sm">
          <span className="text-muted-foreground">Progress</span>
          <span className="font-medium">
            {completedCount} / {totalCount} sections
          </span>
        </div>
        <Progress value={progressPct} variant="success" size="sm" />
      </div>
    );
  }

  return (
    <div className={cn("space-y-4", className)}>
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-medium">Reading Progress</p>
          <p className="text-xs text-muted-foreground">
            {completedReadingTime} of {totalReadingTime} min read
          </p>
        </div>
        <div className="text-right">
          <p className="text-2xl font-bold">{progressPct.toFixed(0)}%</p>
          <p className="text-xs text-muted-foreground">
            {completedCount} of {totalCount}
          </p>
        </div>
      </div>
      <Progress value={progressPct} variant="success" size="lg" />
    </div>
  );
}

interface ChapterListProps {
  units: ReadingUnit[];
  currentUnitId?: string;
  onSelectUnit: (unitId: string) => void;
  className?: string;
}

export function ChapterList({
  units,
  currentUnitId,
  onSelectUnit,
  className,
}: ChapterListProps) {
  // Group by narrative thread if present
  const threads = new Map<string | undefined, ReadingUnit[]>();
  units.forEach((unit) => {
    const thread = unit.narrativeThread;
    if (!threads.has(thread)) {
      threads.set(thread, []);
    }
    threads.get(thread)!.push(unit);
  });

  const renderUnit = (unit: ReadingUnit) => {
    const isCurrent = unit.id === currentUnitId;
    const statusColors = {
      unread: "bg-gray-200 dark:bg-gray-700",
      in_progress: "bg-yellow-400",
      completed: "bg-green-500",
    };

    return (
      <button
        key={unit.id}
        onClick={() => onSelectUnit(unit.id)}
        className={cn(
          "flex items-center gap-3 p-3 rounded-lg transition-all w-full text-left",
          "hover:bg-accent",
          isCurrent && "ring-2 ring-primary bg-primary/5"
        )}
      >
        <div
          className={cn(
            "w-3 h-3 rounded-full shrink-0",
            statusColors[unit.status]
          )}
        />
        <div className="flex-1 min-w-0">
          <p
            className={cn(
              "text-sm truncate",
              unit.status === "completed"
                ? "text-muted-foreground"
                : "font-medium"
            )}
          >
            {unit.title}
          </p>
          <p className="text-xs text-muted-foreground">
            {unit.readingTimeMin} min read
          </p>
        </div>
        {unit.status === "completed" && (
          <span className="text-green-500 text-sm">✓</span>
        )}
      </button>
    );
  };

  if (threads.size === 1 && threads.has(undefined)) {
    // No narrative threads, simple list
    return (
      <div className={cn("space-y-1", className)}>
        {units.map(renderUnit)}
      </div>
    );
  }

  // Multiple narrative threads
  return (
    <div className={cn("space-y-4", className)}>
      {Array.from(threads.entries()).map(([thread, threadUnits]) => (
        <div key={thread || "main"}>
          {thread && (
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-2 px-3">
              {thread}
            </p>
          )}
          <div className="space-y-1">{threadUnits.map(renderUnit)}</div>
        </div>
      ))}
    </div>
  );
}

interface TimelineViewProps {
  units: ReadingUnit[];
  currentUnitId?: string;
  onSelectUnit: (unitId: string) => void;
  className?: string;
}

export function TimelineView({
  units,
  currentUnitId,
  onSelectUnit,
  className,
}: TimelineViewProps) {
  return (
    <div className={cn("relative", className)}>
      {/* Timeline line */}
      <div className="absolute left-4 top-0 bottom-0 w-0.5 bg-gray-200 dark:bg-gray-700" />

      <div className="space-y-4">
        {units.map((unit, index) => {
          const isCurrent = unit.id === currentUnitId;
          const isCompleted = unit.status === "completed";

          return (
            <button
              key={unit.id}
              onClick={() => onSelectUnit(unit.id)}
              className={cn(
                "relative flex items-start gap-4 pl-10 pr-4 py-2 w-full text-left",
                "hover:bg-accent rounded-lg transition-all",
                isCurrent && "bg-primary/5"
              )}
            >
              {/* Timeline dot */}
              <div
                className={cn(
                  "absolute left-2 w-5 h-5 rounded-full border-2 flex items-center justify-center",
                  isCompleted
                    ? "bg-green-500 border-green-500"
                    : isCurrent
                    ? "bg-primary border-primary"
                    : "bg-background border-gray-300 dark:border-gray-600"
                )}
              >
                {isCompleted && (
                  <svg
                    className="w-3 h-3 text-white"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={3}
                      d="M5 13l4 4L19 7"
                    />
                  </svg>
                )}
              </div>

              <div className="flex-1">
                <p
                  className={cn(
                    "text-sm",
                    isCompleted
                      ? "text-muted-foreground"
                      : isCurrent
                      ? "font-semibold text-primary"
                      : "font-medium"
                  )}
                >
                  {unit.title}
                </p>
                <p className="text-xs text-muted-foreground">
                  {unit.readingTimeMin} min
                  {unit.narrativeThread && ` • ${unit.narrativeThread}`}
                </p>
              </div>

              {index < units.length - 1 && (
                <span className="text-xs text-muted-foreground self-center">
                  {index + 1}
                </span>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}
