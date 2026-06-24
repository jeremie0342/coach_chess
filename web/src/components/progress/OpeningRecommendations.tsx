"use client";

import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import { cn } from "@/lib/utils";
import type { OpeningRecommendations } from "@/types/coach";

export function OpeningRecommendationsCard({ data }: { data: OpeningRecommendations }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Ouvertures recommandées</CardTitle>
        <span className="text-xs text-[var(--muted)]">en accord avec ton style</span>
      </CardHeader>
      <ul className="space-y-3">
        {data.recommendations.slice(0, 6).map((r, i) => (
          <li key={i} className={cn(
            "border-l-2 pl-3",
            r.color === "white" ? "border-white/60" : "border-black/80",
          )}>
            <div className="flex items-baseline justify-between gap-2">
              <div className="font-medium text-sm">{r.name}</div>
              <div className="text-xs text-[var(--accent)] tabular-nums font-mono">
                fit {Math.round(r.fit_score * 100)}%
              </div>
            </div>
            <div className="text-xs text-[var(--muted)] mt-0.5">
              <span className="font-mono">{r.eco ?? ""}</span> · {r.role}
            </div>
            <div className="text-xs mt-1 text-[var(--foreground)]/80">{r.short_pitch}</div>
            {r.rationale && <div className="text-xs text-[var(--muted)] italic mt-1">{r.rationale}</div>}
          </li>
        ))}
      </ul>
    </Card>
  );
}
