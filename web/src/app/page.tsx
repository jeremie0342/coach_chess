"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { motion } from "framer-motion";
import { Sparkles, Swords, TrendingUp, TrendingDown } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { Card, CardHeader, CardTitle, CardValue } from "@/components/ui/Card";
import { cn } from "@/lib/utils";
import type { DashboardResponse } from "@/types/dashboard";
import type { RecommendedElo, Personality, ContextualPatterns } from "@/types/coach";
import { resolveItemAction } from "@/lib/plan-items";

type PlanItem = {
  id: number;
  order: number;
  kind: string;
  title: string;
  target_count: number;
  estimated_minutes: number;
  filters: Record<string, unknown> | null;
  completed_count: number;
  completed_at: string | null;
};
type TodayPlan = {
  date: string;
  target_minutes: number;
  weakness_focus: string | null;
  coach_message: string | null;
  completed_at: string | null;
  items: PlanItem[];
};
type ProgressResp = {
  snapshot_count: number;
  series: {
    taken_at: string;
    rating_rapid: number | null;
    rating_blitz: number | null;
    rating_bullet: number | null;
    games_7d: number | null;
    exercises_solved_7d: number | null;
    rep_cards_reviewed_7d: number | null;
    plans_completed_7d: number | null;
  }[];
};

export default function DashboardPage() {
  const dash = useQuery<DashboardResponse>({
    queryKey: ["dashboard"],
    queryFn: () => api<DashboardResponse>("/coach/me/dashboard"),
  });
  const today = useQuery<TodayPlan>({
    queryKey: ["today", "dash"],
    queryFn: () => api<TodayPlan>("/coach/me/today", { query: { generate_message_llm: false } }),
  });
  const recElo = useQuery<RecommendedElo>({
    queryKey: ["recommended_elo"],
    queryFn: () => api<RecommendedElo>("/coach/me/recommended_elo"),
  });
  const personality = useQuery<Personality>({
    queryKey: ["personality"],
    queryFn: () => api<Personality>("/coach/me/personality"),
  });
  const progress = useQuery<ProgressResp>({
    queryKey: ["progress-7"],
    queryFn: () => api<ProgressResp>("/coach/me/progress", { query: { days: 14 } }),
  });
  const ctx = useQuery<ContextualPatterns>({
    queryKey: ["contextual"],
    queryFn: () => api<ContextualPatterns>("/coach/me/contextual_patterns"),
  });

  return (
    <div className="px-4 py-6 md:px-8 md:py-8 max-w-7xl">
      <header className="mb-6 flex items-end justify-between gap-3">
        <div>
          <div className="text-xs uppercase tracking-widest text-[var(--muted)]">Coach</div>
          <h1 className="text-3xl font-semibold mt-1">Bonjour, {dash.data?.player.chesscom_username ?? "…"}.</h1>
        </div>
        <div className="text-sm text-[var(--muted)] text-right">
          {new Date().toLocaleDateString("fr-FR", { weekday: "long", day: "numeric", month: "long" })}
        </div>
      </header>

      {dash.isLoading && <SkeletonGrid />}

      {dash.isError && (
        <Card className="border-[var(--danger)]/40">
          <div className="text-[var(--danger)] font-medium">Backend injoignable</div>
          <div className="text-sm text-[var(--muted)] mt-1">
            {dash.error instanceof ApiError ? `HTTP ${dash.error.status}` : String(dash.error)}
          </div>
          <div className="text-xs text-[var(--muted)] mt-3 font-mono">
            Lance le backend : <span className="text-[var(--foreground)]">.\start.ps1</span>
          </div>
        </Card>
      )}

      {dash.data && (
        <div className="space-y-6">
          {/* Coach message */}
          {today.data?.coach_message && (
            <motion.div initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.25 }}>
              <Card className="border-l-4 border-l-[var(--accent)]">
                <div className="flex items-start gap-3">
                  <Sparkles className="size-4 text-[var(--accent)] mt-0.5 shrink-0" />
                  <div className="flex-1 min-w-0">
                    <div className="text-xs uppercase tracking-widest text-[var(--muted)] mb-1">Message du coach</div>
                    <div className="text-sm leading-relaxed whitespace-pre-wrap">{today.data.coach_message}</div>
                  </div>
                </div>
              </Card>
            </motion.div>
          )}

          {/* Stats strip */}
          <RatingStrip dash={dash.data} progress={progress.data} />

          {/* Plan + side */}
          <section className="grid lg:grid-cols-3 gap-4">
            <Card className="lg:col-span-2">
              <CardHeader>
                <div>
                  <CardTitle>Plan du jour</CardTitle>
                  {today.data && (
                    <div className="text-xs text-[var(--muted)] mt-0.5">
                      {today.data.target_minutes} min visées
                      {today.data.weakness_focus && <> · focus <span className="text-[var(--foreground)]">{today.data.weakness_focus}</span></>}
                    </div>
                  )}
                </div>
                <Link href="/today" className="text-xs text-[var(--info)] hover:underline">Ouvrir →</Link>
              </CardHeader>

              <div className="grid grid-cols-2 gap-3 mb-4">
                <TrainingTile
                  label="Répertoire dus"
                  value={dash.data.training.repertoire_due}
                  extra={`${dash.data.training.repertoire_new_available} nouveaux`}
                  href="/repertoire"
                />
                <TrainingTile
                  label="Puzzles dus"
                  value={dash.data.training.exercises_due}
                  extra={`${dash.data.training.exercises_new_available} nouveaux`}
                  href="/puzzles"
                />
              </div>

              {today.data?.items && today.data.items.length > 0 && (
                <ul className="space-y-1.5 border-t border-[var(--border)] pt-3">
                  {today.data.items.slice(0, 4).map((it) => {
                    const done = it.completed_at != null;
                    const action = resolveItemAction(it.kind, it.filters);
                    const href = action.type === "link" ? action.href : "/today";
                    return (
                      <li key={it.id} className={cn("flex items-center gap-3 text-sm", done && "opacity-50")}>
                        <span className={cn("inline-block size-2 rounded-full shrink-0",
                          done ? "bg-[var(--accent)]" : "bg-[var(--muted)]/60")} />
                        <span className="flex-1 truncate">{it.title}</span>
                        <span className="text-xs text-[var(--muted)] tabular-nums">{it.completed_count}/{it.target_count}</span>
                        <Link href={href} className="text-xs text-[var(--info)] hover:underline">→</Link>
                      </li>
                    );
                  })}
                  {today.data.items.length > 4 && (
                    <li className="text-xs text-[var(--muted)] pl-5">+ {today.data.items.length - 4} autres…</li>
                  )}
                </ul>
              )}
            </Card>

            <div className="space-y-4">
              {recElo.data && <RecommendedEloMini data={recElo.data} />}
              {personality.data && <PersonalityMini data={personality.data} />}
            </div>
          </section>

          {/* Activity 7d */}
          {progress.data && progress.data.series.length > 0 && (
            <ActivityStrip series={progress.data.series} />
          )}

          {/* Context insight + Faiblesses */}
          <section className="grid lg:grid-cols-3 gap-4">
            {ctx.data && <ContextInsight data={ctx.data} />}
            <Card className={cn(ctx.data ? "lg:col-span-2" : "lg:col-span-3")}>
              <CardHeader>
                <CardTitle>Faiblesses top</CardTitle>
                <Link href="/weaknesses" className="text-xs text-[var(--info)] hover:underline">Détail →</Link>
              </CardHeader>
              <ul className="space-y-2">
                {dash.data.weaknesses.length === 0 && <li className="text-sm text-[var(--muted)]">Pas encore détecté</li>}
                {dash.data.weaknesses.slice(0, 6).map((w, i) => (
                  <li key={i} className="flex items-center justify-between text-sm">
                    <div className="truncate">
                      <span className="text-[var(--foreground)]">{w.category}</span>
                      {w.phase && <span className="text-[var(--muted)] text-xs ml-2">{w.phase}</span>}
                      <span className="text-xs text-[var(--muted)] ml-2 tabular-nums">{w.occurrences} occ.</span>
                    </div>
                    <SeverityBar value={w.severity} />
                  </li>
                ))}
              </ul>
            </Card>
          </section>

          {/* Recent games */}
          <section>
            <Card>
              <CardHeader>
                <CardTitle>Dernières parties</CardTitle>
                <Link href="/games" className="text-xs text-[var(--info)] hover:underline">Toutes →</Link>
              </CardHeader>
              <ul className="divide-y divide-[var(--border)]">
                {dash.data.recent_games.length === 0 && <li className="py-4 text-sm text-[var(--muted)]">Aucune partie importée</li>}
                {dash.data.recent_games.map((g) => (
                  <li key={g.id} className="py-3 flex items-center gap-4">
                    <ResultDot result={g.result} />
                    <div className="w-12 text-xs uppercase text-[var(--muted)]">{g.color}</div>
                    <div className="flex-1 min-w-0">
                      <div className="text-sm truncate">{g.opening ?? "—"}</div>
                      <div className="text-xs text-[var(--muted)] font-mono">{g.eco ?? ""} · OOB ply {g.my_out_of_book_ply ?? "—"}</div>
                    </div>
                    <div className="text-xs tabular-nums text-[var(--muted)] hidden sm:block">{g.my_rating ?? ""}</div>
                    <Link href={`/games/${g.id}`} className="text-xs text-[var(--info)] hover:underline">Review</Link>
                  </li>
                ))}
              </ul>
            </Card>
          </section>
        </div>
      )}
    </div>
  );
}

/* ---------- Subcomponents ---------- */

function RatingStrip({ dash, progress }: { dash: DashboardResponse; progress: ProgressResp | undefined }) {
  const series = progress?.series ?? [];
  const last = series[series.length - 1];
  const first = series[0];
  const ratingDelta =
    last?.rating_rapid != null && first?.rating_rapid != null && series.length > 1
      ? last.rating_rapid - first.rating_rapid
      : null;

  return (
    <section className="grid grid-cols-2 md:grid-cols-4 gap-3">
      <Card>
        <CardTitle>Rating rapid</CardTitle>
        <div className="flex items-baseline gap-2">
          <CardValue>{dash.player.current_rating_rapid ?? "—"}</CardValue>
          {ratingDelta != null && ratingDelta !== 0 && (
            <span className={cn("text-xs tabular-nums flex items-center gap-0.5",
              ratingDelta > 0 ? "text-[var(--accent)]" : "text-[var(--danger)]")}>
              {ratingDelta > 0 ? <TrendingUp className="size-3" /> : <TrendingDown className="size-3" />}
              {ratingDelta > 0 ? "+" : ""}{ratingDelta}
            </span>
          )}
        </div>
        {last && (last.rating_blitz || last.rating_bullet) && (
          <div className="text-xs text-[var(--muted)] mt-1 tabular-nums">
            blitz {last.rating_blitz ?? "—"} · bullet {last.rating_bullet ?? "—"}
          </div>
        )}
      </Card>
      <Card>
        <CardTitle>Parties (30j)</CardTitle>
        <CardValue>{dash.player.games_last_30d}</CardValue>
        <div className="text-xs text-[var(--muted)] mt-1">{dash.player.games_total} au total</div>
      </Card>
      <Card>
        <CardTitle>Winrate blancs</CardTitle>
        <CardValue>{fmtPct(dash.player.winrate_white)}</CardValue>
      </Card>
      <Card>
        <CardTitle>Winrate noirs</CardTitle>
        <CardValue>{fmtPct(dash.player.winrate_black)}</CardValue>
      </Card>
    </section>
  );
}

function ActivityStrip({ series }: { series: ProgressResp["series"] }) {
  const last = series[series.length - 1];
  if (!last) return null;
  return (
    <section className="grid grid-cols-2 md:grid-cols-4 gap-3">
      <MiniStat label="Parties (7j)" value={last.games_7d} />
      <MiniStat label="Puzzles (7j)" value={last.exercises_solved_7d} />
      <MiniStat label="Cartes rép. (7j)" value={last.rep_cards_reviewed_7d} />
      <MiniStat label="Plans complétés (7j)" value={last.plans_completed_7d} />
    </section>
  );
}

function MiniStat({ label, value }: { label: string; value: number | null | undefined }) {
  return (
    <Card>
      <div className="text-[10px] uppercase tracking-wider text-[var(--muted)]">{label}</div>
      <div className="text-2xl font-semibold tabular-nums mt-1">{value ?? 0}</div>
    </Card>
  );
}

function RecommendedEloMini({ data }: { data: RecommendedElo }) {
  const delta = data.last_elo != null ? data.next_elo - data.last_elo : 0;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Prochaine partie SF</CardTitle>
        <Link href="/play" className="text-xs text-[var(--info)] hover:underline flex items-center gap-1">
          <Swords className="size-3" /> Jouer
        </Link>
      </CardHeader>
      <div className="flex items-baseline gap-2">
        <div className="text-3xl font-bold tabular-nums">{data.next_elo}</div>
        {delta !== 0 && (
          <span className={cn("text-xs tabular-nums", delta > 0 ? "text-[var(--accent)]" : "text-[var(--danger)]")}>
            {delta > 0 ? "+" : ""}{delta}
          </span>
        )}
      </div>
      <div className="text-xs text-[var(--muted)] mt-2 line-clamp-2">{data.reason}</div>
    </Card>
  );
}

function PersonalityMini({ data }: { data: Personality }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Style</CardTitle>
        <Link href="/progress" className="text-xs text-[var(--info)] hover:underline">Voir →</Link>
      </CardHeader>
      <div className="text-xs text-[var(--muted)]">Plus proche de</div>
      <div className="text-2xl font-semibold text-[var(--accent)]">{data.closest_gm}</div>
      <div className="text-xs text-[var(--muted)] tabular-nums mt-0.5">
        {Math.round(data.closest_gm_similarity * 100)}% · dominant <span className="text-[var(--foreground)] capitalize">{data.dominant_trait.replace(/_/g, " ")}</span>
      </div>
    </Card>
  );
}

function ContextInsight({ data }: { data: ContextualPatterns }) {
  // Take the most actionable insight: highest relative_to_baseline above baseline
  const worst = [...data.insights]
    .filter((i) => i.relative_to_baseline > 1.15 && i.sample_moves >= 30)
    .sort((a, b) => b.relative_to_baseline - a.relative_to_baseline)[0];
  if (!worst) return null;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Pattern à corriger</CardTitle>
        <Link href="/progress" className="text-xs text-[var(--info)] hover:underline">Voir →</Link>
      </CardHeader>
      <div className="text-xs text-[var(--muted)] uppercase tracking-wider">{worst.metric.replace(/_/g, " ")}</div>
      <div className="text-lg font-medium capitalize mt-1">{worst.bucket}</div>
      <div className="text-sm mt-1">
        <span className="text-[var(--danger)] tabular-nums font-mono">×{worst.relative_to_baseline.toFixed(2)}</span>{" "}
        <span className="text-[var(--muted)]">de blunders vs baseline</span>
      </div>
      {worst.comment && (
        <div className="text-xs text-[var(--muted)] mt-2 italic">{worst.comment}</div>
      )}
    </Card>
  );
}

function TrainingTile({ label, value, extra, href }: { label: string; value: number; extra?: string; href: string }) {
  return (
    <Link
      href={href}
      className="block rounded-lg border bg-[var(--surface-2)] p-4 hover:border-[var(--accent)]/60 transition-colors"
    >
      <div className="text-xs text-[var(--muted)] uppercase tracking-wider">{label}</div>
      <div className="text-3xl font-semibold mt-2 tabular-nums">{value}</div>
      {extra && <div className="text-xs text-[var(--muted)] mt-1">{extra}</div>}
    </Link>
  );
}

function SeverityBar({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const tone = pct >= 70 ? "bg-[var(--danger)]" : pct >= 40 ? "bg-[var(--warning)]" : "bg-[var(--muted)]";
  const text = pct >= 70 ? "text-[var(--danger)]" : pct >= 40 ? "text-[var(--warning)]" : "text-[var(--muted)]";
  return (
    <div className="flex items-center gap-2">
      <div className="w-16 h-1.5 bg-[var(--surface-2)] rounded overflow-hidden">
        <div className={cn("h-full", tone)} style={{ width: `${pct}%` }} />
      </div>
      <span className={cn("font-mono text-xs tabular-nums w-7 text-right", text)}>{pct}</span>
    </div>
  );
}

function ResultDot({ result }: { result: "win" | "loss" | "draw" | "unknown" }) {
  const color = result === "win" ? "bg-[var(--accent)]" : result === "loss" ? "bg-[var(--danger)]" : "bg-[var(--muted)]";
  return <span className={cn("inline-block size-2 rounded-full", color)} />;
}

function fmtPct(v: number | null) {
  if (v == null) return "—";
  return `${Math.round(v * 100)}%`;
}

function SkeletonGrid() {
  return (
    <div className="space-y-6">
      <Card className="animate-pulse">
        <div className="h-3 w-24 bg-[var(--surface-2)] rounded mb-2" />
        <div className="h-4 w-full bg-[var(--surface-2)] rounded" />
      </Card>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {Array.from({ length: 4 }).map((_, i) => (
          <Card key={i} className="animate-pulse">
            <div className="h-3 w-24 bg-[var(--surface-2)] rounded mb-3" />
            <div className="h-8 w-16 bg-[var(--surface-2)] rounded" />
          </Card>
        ))}
      </div>
    </div>
  );
}
