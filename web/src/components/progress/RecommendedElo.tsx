"use client";

import Link from "next/link";
import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import type { RecommendedElo } from "@/types/coach";

export function RecommendedEloCard({ data }: { data: RecommendedElo }) {
  const delta = data.last_elo != null ? data.next_elo - data.last_elo : 0;
  return (
    <Card className="border-l-4 border-l-[var(--accent)]">
      <CardHeader>
        <CardTitle>Prochaine partie vs Stockfish</CardTitle>
        <span className="text-xs text-[var(--muted)] tabular-nums">basé sur {data.sessions_used} session(s)</span>
      </CardHeader>
      <div className="flex items-baseline gap-4">
        <div className="text-5xl font-bold tabular-nums">{data.next_elo}</div>
        {delta !== 0 && (
          <div className={`text-sm tabular-nums ${delta > 0 ? "text-[var(--accent)]" : "text-[var(--danger)]"}`}>
            {delta > 0 ? "+" : ""}{delta} vs précédent
          </div>
        )}
        <div className="ml-auto">
          <Link
            href={`/play`}
            className="text-xs px-3 py-1.5 rounded bg-[var(--accent)] text-black font-medium"
          >
            Jouer →
          </Link>
        </div>
      </div>
      <div className="text-xs text-[var(--muted)] mt-3">{data.reason}</div>
      <div className="mt-3 flex gap-4 text-xs tabular-nums">
        {data.recent_score != null && (
          <span><span className="text-[var(--muted)]">Score récent</span> <b>{Math.round(data.recent_score * 100)}%</b></span>
        )}
        {data.win_streak > 0 && <span className="text-[var(--accent)]">série W: {data.win_streak}</span>}
        {data.loss_streak > 0 && <span className="text-[var(--danger)]">série L: {data.loss_streak}</span>}
      </div>
    </Card>
  );
}
