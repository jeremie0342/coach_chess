"use client";

import { useMemo, useState } from "react";
import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import { cn } from "@/lib/utils";
import type { ContextualPatterns } from "@/types/coach";

export function ContextualPatternsCard({ data }: { data: ContextualPatterns }) {
  const metrics = useMemo(() => {
    const map = new Map<string, ContextualPatterns["insights"]>();
    for (const i of data.insights) {
      if (!map.has(i.metric)) map.set(i.metric, []);
      map.get(i.metric)!.push(i);
    }
    return map;
  }, [data.insights]);

  const metricNames = Array.from(metrics.keys());
  const [active, setActive] = useState(metricNames[0]);
  const slice = active ? metrics.get(active) ?? [] : [];
  const maxRate = Math.max(...slice.map((i) => i.blunder_rate), data.baseline_blunder_rate);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Quand je blunders</CardTitle>
        <span className="text-xs text-[var(--muted)] tabular-nums">
          baseline {Math.round(data.baseline_blunder_rate * 100)}% · {data.total_moves} coups
        </span>
      </CardHeader>

      <div className="flex gap-1.5 mb-4 flex-wrap">
        {metricNames.map((m) => (
          <button
            key={m}
            onClick={() => setActive(m)}
            className={cn(
              "text-xs px-2 py-1 rounded border capitalize",
              active === m ? "bg-[var(--accent)] text-black border-[var(--accent)]" : "bg-[var(--surface-2)] text-[var(--muted)]",
            )}
          >
            {m.replace(/_/g, " ")}
          </button>
        ))}
      </div>

      <div className="space-y-2">
        {slice.map((i) => {
          const pct = (i.blunder_rate / maxRate) * 100;
          const above = i.relative_to_baseline > 1.15;
          const below = i.relative_to_baseline < 0.85;
          return (
            <div key={i.bucket} className="text-sm">
              <div className="flex items-baseline justify-between mb-0.5">
                <span className={cn("capitalize", above && "text-[var(--danger)]", below && "text-[var(--accent)]")}>
                  {i.bucket}
                </span>
                <span className="text-xs text-[var(--muted)] tabular-nums font-mono">
                  {Math.round(i.blunder_rate * 100)}% ·{" "}
                  <span className={cn(above && "text-[var(--danger)]", below && "text-[var(--accent)]")}>
                    ×{i.relative_to_baseline.toFixed(2)}
                  </span>
                </span>
              </div>
              <div className="h-2 bg-[var(--surface-2)] rounded overflow-hidden relative">
                <div
                  className={cn(
                    "h-full transition-all",
                    above ? "bg-[var(--danger)]" : below ? "bg-[var(--accent)]" : "bg-[var(--muted)]",
                  )}
                  style={{ width: `${pct}%` }}
                />
                <div
                  className="absolute top-0 bottom-0 w-px bg-[var(--foreground)]/40"
                  style={{ left: `${(data.baseline_blunder_rate / maxRate) * 100}%` }}
                  title={`baseline ${Math.round(data.baseline_blunder_rate * 100)}%`}
                />
              </div>
              {i.comment && <div className="text-xs text-[var(--muted)] mt-0.5 italic">{i.comment}</div>}
            </div>
          );
        })}
      </div>
    </Card>
  );
}
