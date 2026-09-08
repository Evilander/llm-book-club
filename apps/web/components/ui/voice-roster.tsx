import {
  Eye,
  Flame,
  Sparkles,
  User,
  MessageCircle,
} from "lucide-react";
import { cn } from "@/lib/utils";

type AgentRole =
  | "facilitator"
  | "close_reader"
  | "skeptic"
  | "after_dark_guide"
  | "user";

interface AgentInfo {
  name: string;
  subtitle: string;
  icon: React.ElementType;
  color: string;
  bgColor: string;
}

const AGENT_ROSTER: Record<AgentRole, AgentInfo> = {
  user: {
    name: "You",
    subtitle: "",
    icon: User,
    color: "text-blue-400",
    bgColor: "bg-blue-500/10",
  },
  facilitator: {
    name: "Sam",
    subtitle: "guide",
    icon: Sparkles,
    color: "text-amber-400",
    bgColor: "bg-amber-500/10",
  },
  close_reader: {
    name: "Ellis",
    subtitle: "close reader",
    icon: Eye,
    color: "text-teal-400",
    bgColor: "bg-teal-500/10",
  },
  skeptic: {
    name: "Kit",
    subtitle: "skeptic",
    icon: Flame,
    color: "text-rose-400",
    bgColor: "bg-rose-500/10",
  },
  after_dark_guide: {
    name: "After dark",
    subtitle: "erotic lens",
    icon: Sparkles,
    color: "text-fuchsia-300",
    bgColor: "bg-fuchsia-500/10",
  },
};

const AFTER_DARK_PERSONAS: Record<string, { name: string; subtitle: string }> = {
  woman: { name: "Sable", subtitle: "after-dark guide" },
  gay_man: { name: "Lucian", subtitle: "after-dark guide" },
  trans_woman: { name: "Vesper", subtitle: "after-dark guide" },
};

interface VoiceRosterProps {
  roles: readonly string[];
  activeAgent?: string | null;
  desireLens?: string | null;
  className?: string;
}

export function getAgentInfo(
  role: string,
  desireLens?: string | null
): AgentInfo {
  if (role === "after_dark_guide") {
    const persona = desireLens ? AFTER_DARK_PERSONAS[desireLens] : null;
    return {
      ...AGENT_ROSTER.after_dark_guide,
      name: persona?.name || AGENT_ROSTER.after_dark_guide.name,
      subtitle: persona?.subtitle || AGENT_ROSTER.after_dark_guide.subtitle,
    };
  }

  return (
    AGENT_ROSTER[role as AgentRole] || {
      name: role,
      subtitle: "",
      icon: MessageCircle,
      color: "text-muted-foreground",
      bgColor: "bg-muted",
    }
  );
}

export function VoiceRoster({
  roles,
  activeAgent,
  desireLens,
  className,
}: VoiceRosterProps) {
  return (
    <div className={cn("space-y-2", className)}>
      <h3 className="mb-3 text-sm font-semibold font-label">Book club voices</h3>
      {roles.map((role) => {
        const info = getAgentInfo(role, desireLens);
        const Icon = info.icon;
        return (
          <div
            key={role}
            className={cn(
              "flex items-center gap-3 rounded-2xl border border-white/10 px-3 py-3 transition-colors",
              activeAgent === role && info.bgColor
            )}
          >
            <div
              className={cn(
                "flex h-8 w-8 items-center justify-center rounded-xl",
                info.bgColor
              )}
            >
              <Icon className={cn("h-4 w-4", info.color)} />
            </div>
            <div>
              <p className="text-sm font-medium">{info.name}</p>
              <p className="text-xs text-muted-foreground">{info.subtitle}</p>
            </div>
          </div>
        );
      })}
    </div>
  );
}
