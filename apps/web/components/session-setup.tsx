"use client";

import { useState, useEffect } from "react";
import {
  ArrowLeft,
  Clock,
  BookOpen,
  MessageSquare,
  HelpCircle,
  Scale,
  Feather,
  Sparkles,
  Check,
  Play,
  Loader2,
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { API_BASE, formatReadingTime } from "@/lib/utils";

interface Section {
  id: string;
  title: string;
  section_type: string;
  order_index: number;
  reading_time_min: number | null;
}

interface SessionSetupProps {
  bookId: string;
  onBack: () => void;
  onStartSession: (sessionId: string) => void;
}

const MODES = [
  {
    id: "conversation",
    name: "Just Talk",
    icon: MessageSquare,
    description: "Free-flowing discussion. Follow your curiosity wherever it goes.",
    color: "orange",
  },
  {
    id: "first_time",
    name: "First Time",
    icon: HelpCircle,
    description: "New to this book? We'll make it approachable and fun.",
    color: "blue",
  },
  {
    id: "deep_dive",
    name: "Deep Dive",
    icon: Feather,
    description: "Zoom in on language, patterns, and craft. For when you want to really dig in.",
    color: "purple",
  },
  {
    id: "big_picture",
    name: "Big Picture",
    icon: Scale,
    description: "Themes, connections, and what it all means.",
    color: "emerald",
  },
];

const TIME_OPTIONS = [10, 15, 20, 30, 45, 60];

const colorClasses: Record<string, { bg: string; border: string; text: string }> = {
  orange: { bg: "bg-orange-500/10", border: "border-orange-500/30", text: "text-orange-400" },
  blue: { bg: "bg-blue-500/10", border: "border-blue-500/30", text: "text-blue-400" },
  purple: { bg: "bg-purple-500/10", border: "border-purple-500/30", text: "text-purple-400" },
  emerald: { bg: "bg-emerald-500/10", border: "border-emerald-500/30", text: "text-emerald-400" },
};

export function SessionSetup({ bookId, onBack, onStartSession }: SessionSetupProps) {
  const [sections, setSections] = useState<Section[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedMode, setSelectedMode] = useState("conversation");
  const [timeBudget, setTimeBudget] = useState(20);
  const [selectedSections, setSelectedSections] = useState<string[]>([]);
  const [starting, setStarting] = useState(false);

  useEffect(() => {
    async function loadSections() {
      try {
        const res = await fetch(`${API_BASE}/v1/books/${bookId}/sections`);
        const data = await res.json();
        setSections(data.sections || []);
      } catch (e) {
        console.error("Failed to load sections:", e);
      } finally {
        setLoading(false);
      }
    }
    loadSections();
  }, [bookId]);

  function toggleSection(sectionId: string) {
    setSelectedSections((prev) =>
      prev.includes(sectionId)
        ? prev.filter((id) => id !== sectionId)
        : [...prev, sectionId]
    );
  }

  async function startSession() {
    setStarting(true);
    try {
      const res = await fetch(`${API_BASE}/v1/sessions/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          book_id: bookId,
          mode: selectedMode,
          time_budget_min: timeBudget,
          section_ids: selectedSections.length > 0 ? selectedSections : null,
        }),
      });
      const data = await res.json();
      if (data.session_id) {
        onStartSession(data.session_id);
      }
    } catch (e) {
      console.error("Failed to start session:", e);
    } finally {
      setStarting(false);
    }
  }

  const totalSelectedTime =
    selectedSections.length > 0
      ? sections
          .filter((s) => selectedSections.includes(s.id))
          .reduce((sum, s) => sum + (s.reading_time_min || 5), 0)
      : null;

  const selectedModeData = MODES.find((m) => m.id === selectedMode);

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-center gap-4">
        <Button variant="ghost" size="icon" onClick={onBack} className="shrink-0">
          <ArrowLeft className="w-5 h-5" />
        </Button>
        <div>
          <h2 className="text-2xl font-bold">Let's Read Together</h2>
          <p className="text-sm text-muted-foreground">
            How do you want to explore this book?
          </p>
        </div>
      </div>

      {/* Mode selection */}
      <div>
        <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
          <Sparkles className="w-5 h-5 text-primary" />
          What's the vibe?
        </h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {MODES.map((mode) => {
            const Icon = mode.icon;
            const isSelected = selectedMode === mode.id;
            const colors = colorClasses[mode.color];

            return (
              <Card
                key={mode.id}
                className={`cursor-pointer transition-all duration-200 hover:-translate-y-0.5 ${
                  isSelected
                    ? `${colors.border} ${colors.bg} ring-1 ring-offset-2 ring-offset-background ring-${mode.color}-500/50`
                    : "hover:border-border/80"
                }`}
                onClick={() => setSelectedMode(mode.id)}
              >
                <CardContent className="p-4">
                  <div className="flex items-start gap-3">
                    <div
                      className={`shrink-0 w-10 h-10 rounded-lg flex items-center justify-center ${
                        isSelected ? colors.bg : "bg-secondary"
                      }`}
                    >
                      <Icon
                        className={`w-5 h-5 ${isSelected ? colors.text : "text-muted-foreground"}`}
                      />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <h4 className="font-semibold">{mode.name}</h4>
                        {isSelected && (
                          <div className={`w-4 h-4 rounded-full ${colors.bg} flex items-center justify-center`}>
                            <Check className={`w-3 h-3 ${colors.text}`} />
                          </div>
                        )}
                      </div>
                      <p className="text-xs text-muted-foreground line-clamp-2">
                        {mode.description}
                      </p>
                    </div>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      </div>

      {/* Time budget */}
      <div>
        <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
          <Clock className="w-5 h-5 text-primary" />
          Time Budget
        </h3>
        <div className="flex flex-wrap gap-2">
          {TIME_OPTIONS.map((time) => (
            <Button
              key={time}
              variant={timeBudget === time ? "default" : "outline"}
              size="sm"
              onClick={() => setTimeBudget(time)}
              className={timeBudget === time ? "shadow-glow" : ""}
            >
              {formatReadingTime(time)}
            </Button>
          ))}
        </div>
        <p className="text-xs text-muted-foreground mt-2">
          We'll pick sections that fit your time
        </p>
      </div>

      {/* Section selection */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold flex items-center gap-2">
            <BookOpen className="w-5 h-5 text-primary" />
            Select Sections
          </h3>
          <span className="text-sm text-muted-foreground">
            {selectedSections.length === 0 ? (
              <Badge variant="outline">Auto-select based on time</Badge>
            ) : (
              <Badge variant="default">
                {selectedSections.length} selected
                {totalSelectedTime && ` (~${formatReadingTime(totalSelectedTime)})`}
              </Badge>
            )}
          </span>
        </div>
        {loading ? (
          <div className="text-center py-8">
            <Loader2 className="w-6 h-6 mx-auto animate-spin text-primary" />
            <p className="text-sm text-muted-foreground mt-2">Loading sections...</p>
          </div>
        ) : sections.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            <BookOpen className="w-8 h-8 mx-auto mb-2 opacity-50" />
            <p>No sections found in this book</p>
          </div>
        ) : (
          <div className="grid gap-2 max-h-80 overflow-y-auto pr-2">
            {sections.map((section) => {
              const isSelected = selectedSections.includes(section.id);
              return (
                <Card
                  key={section.id}
                  className={`cursor-pointer transition-all duration-200 ${
                    isSelected
                      ? "border-primary/50 bg-primary/5"
                      : "hover:border-border/80 hover:bg-muted/30"
                  }`}
                  onClick={() => toggleSection(section.id)}
                >
                  <CardContent className="p-3 flex items-center justify-between gap-3">
                    <div className="flex items-center gap-3 min-w-0">
                      <div
                        className={`w-5 h-5 rounded border flex items-center justify-center shrink-0 transition-colors ${
                          isSelected
                            ? "bg-primary border-primary"
                            : "border-border"
                        }`}
                      >
                        {isSelected && <Check className="w-3 h-3 text-white" />}
                      </div>
                      <div className="min-w-0">
                        <p className="font-medium text-sm truncate">
                          {section.title || `Section ${section.order_index + 1}`}
                        </p>
                        <p className="text-xs text-muted-foreground">
                          {section.section_type}
                        </p>
                      </div>
                    </div>
                    <Badge variant="outline" className="shrink-0">
                      {formatReadingTime(section.reading_time_min || 5)}
                    </Badge>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        )}
      </div>

      {/* Meet your book club */}
      <div>
        <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
          <Sparkles className="w-5 h-5 text-primary" />
          Your Book Club
        </h3>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <Card className="p-3 bg-amber-500/5 border-amber-500/20">
            <div className="flex items-center gap-2 mb-1.5">
              <div className="w-7 h-7 rounded-lg bg-amber-500/10 flex items-center justify-center">
                <Sparkles className="w-3.5 h-3.5 text-amber-400" />
              </div>
              <span className="font-medium text-sm text-amber-400">Sam</span>
            </div>
            <p className="text-xs text-muted-foreground">
              Your guide. Asks great questions and makes connections you might miss.
            </p>
          </Card>
          <Card className="p-3 bg-teal-500/5 border-teal-500/20">
            <div className="flex items-center gap-2 mb-1.5">
              <div className="w-7 h-7 rounded-lg bg-teal-500/10 flex items-center justify-center">
                <BookOpen className="w-3.5 h-3.5 text-teal-400" />
              </div>
              <span className="font-medium text-sm text-teal-400">Ellis</span>
            </div>
            <p className="text-xs text-muted-foreground">
              The reader. Catches details everyone else misses and breaks them down.
            </p>
          </Card>
          <Card className="p-3 bg-rose-500/5 border-rose-500/20">
            <div className="flex items-center gap-2 mb-1.5">
              <div className="w-7 h-7 rounded-lg bg-rose-500/10 flex items-center justify-center">
                <Scale className="w-3.5 h-3.5 text-rose-400" />
              </div>
              <span className="font-medium text-sm text-rose-400">Kit</span>
            </div>
            <p className="text-xs text-muted-foreground">
              Devil's advocate. Pushes back with charm to make everyone think harder.
            </p>
          </Card>
        </div>
      </div>

      {/* Start button */}
      <div className="flex items-center justify-between pt-4 border-t border-border">
        <div className="text-sm text-muted-foreground">
          {selectedModeData && (
            <span className="flex items-center gap-2">
              <selectedModeData.icon className="w-4 h-4" />
              {selectedModeData.name} mode • {formatReadingTime(timeBudget)}
            </span>
          )}
        </div>
        <Button
          size="lg"
          variant="gradient"
          onClick={startSession}
          disabled={starting || loading}
          className="gap-2"
        >
          {starting ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin" />
              Starting...
            </>
          ) : (
            <>
              <Play className="w-4 h-4" />
              Let's Go
            </>
          )}
        </Button>
      </div>
    </div>
  );
}
