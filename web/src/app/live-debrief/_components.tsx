"use client";

import Link from "next/link";
import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import { cn } from "@/lib/utils";

export type DebriefPayload = {
  debrief_id?: number;
  created_at?: string;
  title?: string | null;
  game_id: number | null;
  pgn_hash: string;
  me: string | null;
  my_color: string | null;
  opening: string | null;
  eco: string | null;
  my_out_of_book_ply: number | null;
  moves_analyzed: number;
  phases: Record<string, { blunders: number; mistakes: number; inaccuracies: number }>;
  top_blunders: {
    ply: number;
    side: string;
    played_san: string;
    best_san: string;
    quality: string;
    cp_loss: number;
    explanation: string | null;
    exercise_id: number | null;
  }[];
  exercises_generated: number;
  elapsed_s: number;
};

export function DebriefResult({ data }: { data: DebriefPayload }) {
  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Résumé</CardTitle>
          <span className="text-xs text-[var(--muted)] tabular-nums">{data.elapsed_s}s · {data.moves_analyzed} coups</span>
        </CardHeader>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
          <Stat label="Ouverture" value={data.opening ?? "—"} sub={data.eco ?? ""} />
          <Stat label="Ma couleur" value={data.my_color ?? "—"} />
          <Stat label="Out-of-book" value={data.my_out_of_book_ply != null ? `ply ${data.my_out_of_book_ply}` : "—"} />
          <Stat label="Puzzles générés" value={String(data.exercises_generated)} />
        </div>
      </Card>

      <Card>
        <CardHeader><CardTitle>Phases</CardTitle></CardHeader>
        <table className="w-full text-sm">
          <thead className="text-xs text-[var(--muted)] uppercase tracking-wider">
            <tr><th className="text-left py-1">Phase</th><th className="text-right py-1">Blunders</th><th className="text-right py-1">Mistakes</th><th className="text-right py-1">Inaccs</th></tr>
          </thead>
          <tbody>
            {Object.entries(data.phases).map(([phase, p]) => (
              <tr key={phase} className="border-t border-[var(--border)]">
                <td className="py-2 capitalize">{phase}</td>
                <td className="py-2 text-right text-[var(--danger)] tabular-nums">{p.blunders}</td>
                <td className="py-2 text-right text-[var(--warning)] tabular-nums">{p.mistakes}</td>
                <td className="py-2 text-right text-[var(--info)] tabular-nums">{p.inaccuracies}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Coups problématiques</CardTitle>
          {data.game_id && <Link href={`/games/${data.game_id}`} className="text-xs text-[var(--info)] hover:underline">Ouvrir la review →</Link>}
        </CardHeader>
        <ul className="space-y-3">
          {data.top_blunders.map((b) => (
            <li key={b.ply} className="border-l-2 border-[var(--danger)]/50 pl-3">
              <div className="flex items-baseline gap-3 text-sm font-mono flex-wrap">
                <span className="text-[var(--muted)] tabular-nums w-12">ply {b.ply}</span>
                <span>{b.played_san}</span>
                <span className="text-[var(--muted)]">→ attendu</span>
                <span className="text-[var(--accent)]">{b.best_san}</span>
                <span className={cn(
                  "text-xs uppercase",
                  b.quality.includes("blunder") ? "text-[var(--danger)]" : "text-[var(--warning)]",
                )}>{b.quality}</span>
                <span className="text-xs text-[var(--muted)] tabular-nums">−{b.cp_loss}cp</span>
              </div>
              {b.explanation && <div className="text-sm mt-1 text-[var(--muted)]">{b.explanation}</div>}
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}

export function Stat({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div>
      <div className="text-xs uppercase tracking-wider text-[var(--muted)]">{label}</div>
      <div className="text-base mt-1">{value}</div>
      {sub && <div className="text-xs text-[var(--muted)] font-mono">{sub}</div>}
    </div>
  );
}
