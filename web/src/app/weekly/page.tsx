"use client";

import Link from "next/link";
import { Trophy, Skull } from "lucide-react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import { cn } from "@/lib/utils";

type WLD = { wins: number; losses: number; draws: number };
type PhaseStats = { moves: number; blunders: number; mistakes: number; inaccuracies: number };

type WeeklyDetails = {
  headline?: { games_played: number; elo_first: number | null; elo_last: number | null; elo_delta: number | null; puzzles_solved: number; rep_cards_reviewed: number; plans_completed: number; blunders: number };
  bilan?: WLD;
  by_color?: { white?: WLD; black?: WLD };
  by_time_class?: Record<string, WLD>;
  phase_quality?: { opening?: PhaseStats; middlegame?: PhaseStats; endgame?: PhaseStats };
  avg_out_of_book_ply?: number | null;
  top_blunders?: { game_id: number; played_at: string | null; ply: number; played_san: string; best_san: string | null; quality: string | null; cp_loss: number | null }[];
  best_win?: { game_id: number; opp_rating: number; color: string; opening: string | null; time_class: string | null; played_at: string | null } | null;
  worst_loss?: { game_id: number; opp_rating: number; color: string; opening: string | null; time_class: string | null; played_at: string | null } | null;
  days_played?: number;
  streak?: number;
  top_openings?: { name: string; eco: string | null; games: number; wins: number; losses: number; draws: number; winrate: number }[];
  vs_prev_week?: { games_played_prev: number; wins_prev: number; blunders_prev: number; games_delta: number; wins_delta: number; blunders_delta: number | null };
  current_top_weaknesses?: { category: string; phase: string | null; severity: number }[];
  weakness_deltas?: Record<string, number>;
};

type WeeklyReport = {
  id: number;
  week_start: string;
  week_end: string;
  generated_at: string;
  games_played: number;
  elo_delta: number | null;
  puzzles_solved: number | null;
  rep_cards_reviewed: number | null;
  plans_completed: number | null;
  blunders_this_week: number | null;
  weakness_deltas: Record<string, number> | null;
  top_focus_for_next_week: string | null;
  narrative: string | null;
  details: WeeklyDetails | null;
};

type WeeklyListResp = { count: number; reports: WeeklyReport[] };

export default function WeeklyPage() {
  const qc = useQueryClient();
  const q = useQuery<WeeklyListResp>({
    queryKey: ["weekly"],
    queryFn: () => api<WeeklyListResp>("/coach/me/weekly_reports"),
  });
  const gen = useMutation({
    mutationFn: (force: boolean) =>
      api("/coach/me/weekly_reports/generate", { method: "POST", query: { force: String(force) } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["weekly"] }),
  });

  return (
    <div className="px-4 py-6 md:px-8 md:py-8 max-w-6xl">
      <header className="mb-6 flex items-end justify-between flex-wrap gap-3">
        <div>
          <div className="text-xs uppercase tracking-widest text-[var(--muted)]">Outils</div>
          <h1 className="text-3xl font-semibold mt-1">Rapports hebdo</h1>
          {q.data && <div className="text-sm text-[var(--muted)] mt-1">{q.data.count} rapports</div>}
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => gen.mutate(false)}
            disabled={gen.isPending}
            className="text-xs px-3 py-1.5 rounded border bg-[var(--surface-2)] hover:bg-[var(--surface)] disabled:opacity-50"
          >
            {gen.isPending ? "..." : "Générer cette semaine"}
          </button>
          <button
            onClick={() => gen.mutate(true)}
            disabled={gen.isPending}
            className="text-xs px-3 py-1.5 rounded border bg-[var(--surface-2)] hover:bg-[var(--surface)] disabled:opacity-50"
          >
            Forcer regen
          </button>
        </div>
      </header>

      {q.data?.reports.length === 0 && (
        <Card>
          <div className="text-sm text-[var(--muted)]">Aucun rapport. Clique &laquo; Générer cette semaine &raquo;.</div>
        </Card>
      )}

      <div className="space-y-6">
        {q.data?.reports.map((r) => <ReportCard key={r.id} report={r} />)}
      </div>
    </div>
  );
}

function ReportCard({ report: r }: { report: WeeklyReport }) {
  const d = r.details ?? {};
  const elo = r.elo_delta ?? 0;
  const h = d.headline;

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>
            Semaine du {new Date(r.week_start).toLocaleDateString("fr-FR", { day: "numeric", month: "long" })}
          </CardTitle>
          <div className="text-xs text-[var(--muted)] mt-0.5">
            générée {new Date(r.generated_at).toLocaleString("fr-FR")}
          </div>
        </div>
        <div className={cn("text-3xl font-bold tabular-nums",
          elo > 0 ? "text-[var(--accent)]" : elo < 0 ? "text-[var(--danger)]" : "text-[var(--muted)]")}>
          {elo > 0 ? "+" : ""}{elo}
          <div className="text-xs font-normal text-[var(--muted)] uppercase tracking-widest">Δ ELO</div>
        </div>
      </CardHeader>

      {/* Headline strip */}
      <div className="grid grid-cols-3 md:grid-cols-6 gap-3 mb-5 text-sm">
        <Stat label="Parties" value={r.games_played} />
        <Stat label="Puzzles" value={r.puzzles_solved} />
        <Stat label="Cartes rép." value={r.rep_cards_reviewed} />
        <Stat label="Plans" value={r.plans_completed} />
        <Stat label="Blunders" value={r.blunders_this_week} tone={(r.blunders_this_week ?? 0) > 10 ? "text-[var(--danger)]" : undefined} />
        <Stat label="Jours actifs" value={d.days_played} sub={d.streak ? `${d.streak}j streak` : ""} />
      </div>

      {/* Bilan W/L/D */}
      {d.bilan && (
        <div className="mb-5">
          <SectionLabel>Bilan W/L/D</SectionLabel>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <BilanCard title="Total" wld={d.bilan} />
            {d.by_color?.white && <BilanCard title="En blancs" wld={d.by_color.white} />}
            {d.by_color?.black && <BilanCard title="En noirs" wld={d.by_color.black} />}
          </div>
        </div>
      )}

      {/* Par cadence */}
      {d.by_time_class && Object.keys(d.by_time_class).length > 0 && (
        <div className="mb-5">
          <SectionLabel>Par cadence</SectionLabel>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {Object.entries(d.by_time_class).map(([tc, w]) => (
              <BilanCard key={tc} title={tc} wld={w} compact />
            ))}
          </div>
        </div>
      )}

      {/* Force par phase */}
      {d.phase_quality && (
        <div className="mb-5">
          <SectionLabel>Force par phase (tes coups)</SectionLabel>
          <table className="w-full text-sm">
            <thead className="text-xs text-[var(--muted)] uppercase tracking-wider">
              <tr><th className="text-left py-1">Phase</th><th className="text-right py-1">Coups</th><th className="text-right py-1">Blunders</th><th className="text-right py-1">Mistakes</th><th className="text-right py-1">Inaccs</th><th className="text-right py-1">Taux blunder</th></tr>
            </thead>
            <tbody>
              {(["opening", "middlegame", "endgame"] as const).map((p) => {
                const ph = d.phase_quality?.[p];
                if (!ph) return null;
                const rate = ph.moves > 0 ? ph.blunders / ph.moves : 0;
                return (
                  <tr key={p} className="border-t border-[var(--border)]">
                    <td className="py-1.5 capitalize">{p}</td>
                    <td className="py-1.5 text-right tabular-nums text-[var(--muted)]">{ph.moves}</td>
                    <td className="py-1.5 text-right text-[var(--danger)] tabular-nums">{ph.blunders}</td>
                    <td className="py-1.5 text-right text-[var(--warning)] tabular-nums">{ph.mistakes}</td>
                    <td className="py-1.5 text-right text-[var(--info)] tabular-nums">{ph.inaccuracies}</td>
                    <td className="py-1.5 text-right tabular-nums font-mono">{(rate * 100).toFixed(1)}%</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {d.avg_out_of_book_ply != null && (
            <div className="text-xs text-[var(--muted)] mt-2">
              Tu sors du livre en moyenne au ply <b className="text-[var(--foreground)]">{d.avg_out_of_book_ply}</b>.
            </div>
          )}
        </div>
      )}

      {/* Top 5 pires coups */}
      {d.top_blunders && d.top_blunders.length > 0 && (
        <div className="mb-5">
          <SectionLabel>Top 5 pires coups de la semaine</SectionLabel>
          <ul className="space-y-2">
            {d.top_blunders.map((b, i) => (
              <li key={i} className="border-l-2 border-[var(--danger)]/50 pl-3 text-sm">
                <div className="flex items-baseline gap-3 flex-wrap font-mono">
                  <Link href={`/games/${b.game_id}`} className="text-[var(--info)] hover:underline">
                    #{b.game_id} ply {b.ply}
                  </Link>
                  <span>{b.played_san}</span>
                  <span className="text-[var(--muted)]">→ attendu</span>
                  <span className="text-[var(--accent)]">{b.best_san ?? "?"}</span>
                  <span className={cn("text-xs uppercase",
                    (b.quality ?? "").includes("blunder") ? "text-[var(--danger)]" : "text-[var(--warning)]")}>
                    {b.quality?.split(".").pop()}
                  </span>
                  <span className="text-xs text-[var(--muted)] tabular-nums">−{b.cp_loss ?? 0}cp</span>
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Best win + Worst loss */}
      {(d.best_win || d.worst_loss) && (
        <div className="mb-5 grid grid-cols-1 md:grid-cols-2 gap-3">
          {d.best_win && (
            <Card className="border-l-4 border-l-[var(--accent)]">
              <div className="text-xs uppercase tracking-widest text-[var(--accent)] inline-flex items-center gap-1.5">
                <Trophy className="size-3.5" /> Meilleure victoire
              </div>
              <div className="text-sm mt-1">
                <Link href={`/games/${d.best_win.game_id}`} className="text-[var(--info)] hover:underline font-mono">#{d.best_win.game_id}</Link>
                {" — "}
                {d.best_win.color === "white" ? "Blancs" : "Noirs"} vs {d.best_win.opp_rating} ELO
              </div>
              {d.best_win.opening && <div className="text-xs text-[var(--muted)] mt-1">{d.best_win.opening}</div>}
              <div className="text-xs text-[var(--muted)]">{d.best_win.time_class}{d.best_win.played_at && ` · ${new Date(d.best_win.played_at).toLocaleDateString("fr-FR")}`}</div>
            </Card>
          )}
          {d.worst_loss && (
            <Card className="border-l-4 border-l-[var(--danger)]">
              <div className="text-xs uppercase tracking-widest text-[var(--danger)] inline-flex items-center gap-1.5">
                <Skull className="size-3.5" /> Pire défaite
              </div>
              <div className="text-sm mt-1">
                <Link href={`/games/${d.worst_loss.game_id}`} className="text-[var(--info)] hover:underline font-mono">#{d.worst_loss.game_id}</Link>
                {" — "}
                {d.worst_loss.color === "white" ? "Blancs" : "Noirs"} vs {d.worst_loss.opp_rating} ELO
              </div>
              {d.worst_loss.opening && <div className="text-xs text-[var(--muted)] mt-1">{d.worst_loss.opening}</div>}
              <div className="text-xs text-[var(--muted)]">{d.worst_loss.time_class}{d.worst_loss.played_at && ` · ${new Date(d.worst_loss.played_at).toLocaleDateString("fr-FR")}`}</div>
            </Card>
          )}
        </div>
      )}

      {/* Top ouvertures */}
      {d.top_openings && d.top_openings.length > 0 && (
        <div className="mb-5">
          <SectionLabel>Ouvertures les plus jouées</SectionLabel>
          <table className="w-full text-sm">
            <thead className="text-xs text-[var(--muted)] uppercase tracking-wider">
              <tr><th className="text-left py-1">Ouverture</th><th className="text-right py-1">ECO</th><th className="text-right py-1">Parties</th><th className="text-right py-1">W/L/D</th><th className="text-right py-1">Winrate</th></tr>
            </thead>
            <tbody>
              {d.top_openings.map((o, i) => (
                <tr key={i} className="border-t border-[var(--border)]">
                  <td className="py-1.5 truncate max-w-[280px]">{o.name}</td>
                  <td className="py-1.5 text-right text-xs font-mono text-[var(--muted)]">{o.eco ?? "—"}</td>
                  <td className="py-1.5 text-right tabular-nums">{o.games}</td>
                  <td className="py-1.5 text-right tabular-nums text-xs">
                    <span className="text-[var(--accent)]">{o.wins}</span>{"/"}
                    <span className="text-[var(--danger)]">{o.losses}</span>{"/"}
                    <span className="text-[var(--muted)]">{o.draws}</span>
                  </td>
                  <td className={cn("py-1.5 text-right tabular-nums font-mono",
                    o.winrate >= 0.6 ? "text-[var(--accent)]" : o.winrate <= 0.4 ? "text-[var(--danger)]" : "")}>
                    {Math.round(o.winrate * 100)}%
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Comparaison N-1 */}
      {d.vs_prev_week && (
        <div className="mb-5">
          <SectionLabel>Vs semaine précédente</SectionLabel>
          <div className="grid grid-cols-3 gap-3 text-sm">
            <DeltaCard label="Parties" current={r.games_played} prev={d.vs_prev_week.games_played_prev} delta={d.vs_prev_week.games_delta} betterIfHigher />
            <DeltaCard label="Victoires" current={d.bilan?.wins ?? 0} prev={d.vs_prev_week.wins_prev} delta={d.vs_prev_week.wins_delta} betterIfHigher />
            <DeltaCard label="Blunders" current={r.blunders_this_week ?? 0} prev={d.vs_prev_week.blunders_prev} delta={d.vs_prev_week.blunders_delta ?? 0} betterIfHigher={false} />
          </div>
        </div>
      )}

      {/* Narrative */}
      {r.narrative && (
        <div className="text-sm leading-relaxed whitespace-pre-wrap text-[var(--foreground)]/90 border-l-2 border-[var(--accent)] pl-3 my-4">
          {r.narrative}
        </div>
      )}

      {r.top_focus_for_next_week && (
        <div className="text-sm">
          <span className="text-xs uppercase tracking-wider text-[var(--muted)]">Focus semaine prochaine </span>
          <span className="text-[var(--accent)] font-mono">{r.top_focus_for_next_week}</span>
        </div>
      )}

      {r.weakness_deltas && Object.keys(r.weakness_deltas).length > 0 && (
        <details className="mt-3 text-xs">
          <summary className="text-[var(--muted)] cursor-pointer">Évolution des faiblesses</summary>
          <ul className="mt-2 space-y-1">
            {Object.entries(r.weakness_deltas).map(([k, dx]) => (
              <li key={k} className="flex justify-between">
                <span className="text-[var(--muted)]">{k}</span>
                <span className={cn("font-mono tabular-nums",
                  dx < -0.05 ? "text-[var(--accent)]" : dx > 0.05 ? "text-[var(--danger)]" : "")}>
                  {dx > 0 ? "+" : ""}{(dx * 100).toFixed(0)}%
                </span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </Card>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return <div className="text-xs uppercase tracking-widest text-[var(--muted)] mb-2">{children}</div>;
}

function Stat({ label, value, tone, sub }: { label: string; value: number | null | undefined; tone?: string; sub?: string }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wider text-[var(--muted)]">{label}</div>
      <div className={cn("text-xl font-semibold tabular-nums mt-0.5", tone)}>{value ?? "—"}</div>
      {sub && <div className="text-[10px] text-[var(--muted)]">{sub}</div>}
    </div>
  );
}

function BilanCard({ title, wld, compact }: { title: string; wld: WLD; compact?: boolean }) {
  const total = wld.wins + wld.losses + wld.draws;
  const wr = total > 0 ? (wld.wins + 0.5 * wld.draws) / total : 0;
  return (
    <div className="rounded border bg-[var(--surface-2)] p-3">
      <div className="text-xs uppercase tracking-widest text-[var(--muted)]">{title}</div>
      <div className={cn("font-mono tabular-nums mt-1", compact ? "text-sm" : "text-lg")}>
        <span className="text-[var(--accent)]">{wld.wins}W</span>
        <span className="mx-1 text-[var(--muted)]">/</span>
        <span className="text-[var(--danger)]">{wld.losses}L</span>
        <span className="mx-1 text-[var(--muted)]">/</span>
        <span className="text-[var(--muted)]">{wld.draws}D</span>
      </div>
      <div className="text-xs text-[var(--muted)] tabular-nums">{total} parties · {Math.round(wr * 100)}% wr</div>
      <div className="mt-2 flex h-1.5 rounded overflow-hidden">
        <div style={{ width: `${(wld.wins / Math.max(total, 1)) * 100}%` }} className="bg-[var(--accent)]" />
        <div style={{ width: `${(wld.draws / Math.max(total, 1)) * 100}%` }} className="bg-[var(--muted)]" />
        <div style={{ width: `${(wld.losses / Math.max(total, 1)) * 100}%` }} className="bg-[var(--danger)]" />
      </div>
    </div>
  );
}

function DeltaCard({ label, current, prev, delta, betterIfHigher }: { label: string; current: number; prev: number; delta: number; betterIfHigher: boolean }) {
  const good = betterIfHigher ? delta > 0 : delta < 0;
  const bad = betterIfHigher ? delta < 0 : delta > 0;
  return (
    <div className="rounded border bg-[var(--surface-2)] p-3">
      <div className="text-xs uppercase tracking-widest text-[var(--muted)]">{label}</div>
      <div className="text-xl font-semibold tabular-nums mt-1">{current}</div>
      <div className="text-xs text-[var(--muted)] tabular-nums">prev : {prev}</div>
      <div className={cn("text-xs font-mono tabular-nums",
        good ? "text-[var(--accent)]" : bad ? "text-[var(--danger)]" : "text-[var(--muted)]")}>
        {delta > 0 ? "+" : ""}{delta}
      </div>
    </div>
  );
}
