"use client";

import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import { cn } from "@/lib/utils";
import type { EloCalibration } from "@/types/coach";

export function EloCalibrationCard({ data }: { data: EloCalibration }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>ELO calibré</CardTitle>
        <span className={cn("text-xs uppercase tracking-wider",
          data.confidence === "high" ? "text-[var(--accent)]" :
          data.confidence === "medium" ? "text-[var(--warning)]" :
          "text-[var(--muted)]")}>
          confiance {data.confidence}
        </span>
      </CardHeader>
      <div className="flex items-baseline gap-3 mb-3">
        <div className="text-4xl font-bold tabular-nums">{data.estimated_elo ?? "—"}</div>
        <div className="text-xs text-[var(--muted)]">{data.total_games} parties vs SF</div>
      </div>
      <div className="text-xs text-[var(--muted)] mb-3">{data.reason}</div>

      {data.buckets.length > 0 && (
        <table className="w-full text-xs">
          <thead className="text-[var(--muted)] uppercase tracking-wider">
            <tr className="border-b border-[var(--border)]">
              <th className="text-left py-1">ELO SF</th>
              <th className="text-right py-1">G</th>
              <th className="text-right py-1">W/D/L</th>
              <th className="text-right py-1">Score</th>
            </tr>
          </thead>
          <tbody>
            {data.buckets.map((b) => (
              <tr key={b.sf_elo} className="border-b border-[var(--border)] last:border-0">
                <td className="py-1.5 font-mono tabular-nums">{b.sf_elo}</td>
                <td className="py-1.5 text-right tabular-nums">{b.games}</td>
                <td className="py-1.5 text-right tabular-nums font-mono text-[var(--muted)]">
                  {b.wins}/{b.draws}/{b.losses}
                </td>
                <td className="py-1.5 text-right tabular-nums font-mono">
                  {Math.round(b.score * 100)}%
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Card>
  );
}
