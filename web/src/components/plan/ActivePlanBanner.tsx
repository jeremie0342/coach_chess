"use client";

import Link from "next/link";
import { X, CheckCircle2 } from "lucide-react";
import type { ActivePlanItem } from "@/hooks/useActivePlanItem";
import { cn } from "@/lib/utils";

export function ActivePlanBanner({
  item,
  onClear,
}: {
  item: ActivePlanItem | null;
  onClear: () => void;
}) {
  if (!item) return null;
  const done = item.completed_at != null || item.completed_count >= item.target_count;
  const pct = Math.min(100, Math.round((item.completed_count / Math.max(item.target_count, 1)) * 100));

  return (
    <div className={cn(
      "mb-4 rounded-lg border bg-[var(--surface)] px-4 py-3 flex items-center gap-3",
      done ? "border-[var(--accent)]" : "border-[var(--info)]/40",
    )}>
      {done ? <CheckCircle2 className="size-4 text-[var(--accent)] shrink-0" /> : <span className="size-2 rounded-full bg-[var(--info)] shrink-0" />}
      <div className="flex-1 min-w-0">
        <div className="text-xs text-[var(--muted)] uppercase tracking-wider">Plan du jour</div>
        <div className="text-sm font-medium truncate">{item.title}</div>
        <div className="mt-1.5 h-1 bg-[var(--surface-2)] rounded overflow-hidden">
          <div
            className={cn("h-full transition-all", done ? "bg-[var(--accent)]" : "bg-[var(--info)]")}
            style={{ width: `${pct}%` }}
          />
        </div>
      </div>
      <div className="text-sm font-mono tabular-nums text-[var(--muted)] shrink-0">
        {item.completed_count}/{item.target_count}
      </div>
      {done && (
        <Link href="/today" className="text-xs px-3 py-1.5 rounded bg-[var(--accent)] text-black font-medium">
          Retour au plan
        </Link>
      )}
      <button
        onClick={onClear}
        aria-label="Quitter ce drill"
        className="p-1.5 rounded hover:bg-[var(--surface-2)] text-[var(--muted)] hover:text-[var(--foreground)] shrink-0"
        title="Quitter le drill (le compteur backend est conservé)"
      >
        <X className="size-4" />
      </button>
    </div>
  );
}
