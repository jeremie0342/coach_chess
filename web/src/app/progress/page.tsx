"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Camera } from "lucide-react";
import { LineChart, Line, XAxis, YAxis, ResponsiveContainer, Tooltip, CartesianGrid } from "recharts";
import { api } from "@/lib/api";
import { Card, CardHeader, CardTitle, CardValue } from "@/components/ui/Card";
import { RecommendedEloCard } from "@/components/progress/RecommendedElo";
import { PersonalityCard } from "@/components/progress/PersonalityCard";
import { ContextualPatternsCard } from "@/components/progress/ContextualPatterns";
import { EloCalibrationCard } from "@/components/progress/EloCalibration";
import { OpeningRecommendationsCard } from "@/components/progress/OpeningRecommendations";
import type {
  RecommendedElo,
  Personality,
  ContextualPatterns,
  EloCalibration,
  OpeningRecommendations,
} from "@/types/coach";

type Snapshot = {
  taken_at: string;
  rating_rapid: number | null;
  rating_blitz: number | null;
  rating_bullet: number | null;
  winrate_white: number | null;
  winrate_black: number | null;
  games_total: number | null;
  games_7d: number | null;
  games_30d: number | null;
  exercises_solved_total: number | null;
  exercises_solved_7d: number | null;
  rep_cards_reviewed_7d: number | null;
  plans_completed_7d: number | null;
  weakness_severities: Record<string, number> | null;
  repertoire_due: number | null;
  exercises_due: number | null;
};

type ProgressResp = { player: string; days: number; snapshot_count: number; series: Snapshot[] };

const RANGES = [7, 30, 90, 365];

export default function ProgressPage() {
  const qc = useQueryClient();
  const [days, setDays] = useState(30);

  const q = useQuery<ProgressResp>({
    queryKey: ["progress", days],
    queryFn: () => api<ProgressResp>("/coach/me/progress", { query: { days } }),
  });
  const recElo = useQuery<RecommendedElo>({
    queryKey: ["recommended_elo"],
    queryFn: () => api<RecommendedElo>("/coach/me/recommended_elo"),
  });
  const personality = useQuery<Personality>({
    queryKey: ["personality"],
    queryFn: () => api<Personality>("/coach/me/personality"),
  });
  const ctx = useQuery<ContextualPatterns>({
    queryKey: ["contextual"],
    queryFn: () => api<ContextualPatterns>("/coach/me/contextual_patterns"),
  });
  const calib = useQuery<EloCalibration>({
    queryKey: ["calibration"],
    queryFn: () => api<EloCalibration>("/coach/me/elo_calibration"),
  });
  const openings = useQuery<OpeningRecommendations>({
    queryKey: ["opening_recs"],
    queryFn: () => api<OpeningRecommendations>("/coach/me/opening_recommendations"),
  });

  const snap = useMutation({
    mutationFn: () => api("/coach/me/progress/snapshot", { method: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["progress"] }),
  });

  const series = q.data?.series ?? [];
  const data = series.map((s) => ({
    t: new Date(s.taken_at).toLocaleDateString("fr-FR", { day: "2-digit", month: "short" }),
    rapid: s.rating_rapid,
    blitz: s.rating_blitz,
    bullet: s.rating_bullet,
    wr_w: s.winrate_white != null ? Math.round(s.winrate_white * 100) : null,
    wr_b: s.winrate_black != null ? Math.round(s.winrate_black * 100) : null,
    ex_7d: s.exercises_solved_7d,
    games_7d: s.games_7d,
  }));

  const last = series[series.length - 1];
  const first = series[0];
  const dateRange = first && last
    ? `du ${new Date(first.taken_at).toLocaleDateString("fr-FR")} au ${new Date(last.taken_at).toLocaleDateString("fr-FR")}`
    : null;
  const sparseData = series.length < 3;

  return (
    <div className="px-4 py-6 md:px-8 md:py-8 max-w-7xl">
      <header className="mb-6 flex items-end justify-between">
        <div>
          <div className="text-xs uppercase tracking-widest text-[var(--muted)]">Coach</div>
          <h1 className="text-3xl font-semibold mt-1">Progression</h1>
          {q.data && (
            <div className="text-sm text-[var(--muted)] mt-1">
              {q.data.snapshot_count} snapshot{q.data.snapshot_count > 1 ? "s" : ""} sur les {days} derniers jours
              {dateRange && ` · ${dateRange}`}
            </div>
          )}
        </div>
        <div className="flex gap-2 items-center">
          <div className="flex gap-1">
            {RANGES.map((d) => (
              <button
                key={d}
                onClick={() => setDays(d)}
                className={`text-xs px-3 py-1.5 rounded border ${days === d ? "bg-[var(--accent)] text-black border-[var(--accent)]" : "bg-[var(--surface-2)] text-[var(--muted)]"}`}
              >
                {d}j
              </button>
            ))}
          </div>
          <button
            onClick={() => snap.mutate()}
            disabled={snap.isPending}
            className="text-xs px-3 py-1.5 rounded border bg-[var(--surface-2)] hover:bg-[var(--surface)] disabled:opacity-50 inline-flex items-center gap-1.5"
          >
            <Camera className="size-3" />
            {snap.isPending ? "..." : "Snapshot maintenant"}
          </button>
        </div>
      </header>

      {sparseData && q.data && (
        <Card className="mb-4 border-l-4 border-l-[var(--warning)]">
          <div className="flex items-start gap-3">
            <AlertTriangle className="size-5 text-[var(--warning)] shrink-0 mt-0.5" />
            <div className="text-sm">
              <div className="font-medium text-[var(--warning)]">
                Seulement {q.data.snapshot_count} snapshot{q.data.snapshot_count > 1 ? "s" : ""} en base — les courbes 7j / 30j / 365j affichent les mêmes points
              </div>
              <div className="text-xs text-[var(--muted)] mt-1">
                Chaque snapshot capture ton rating + tes stats à un instant T. Pour une vraie courbe d&apos;évolution il faut <b>au moins 5-7 snapshots</b>.
                Deux moyens :
              </div>
              <ul className="text-xs text-[var(--muted)] list-disc ml-5 mt-2 space-y-1">
                <li>
                  Clique <b>Snapshot maintenant</b> chaque jour (manuel).
                </li>
                <li>
                  Lance le <b>worker arq</b> en parallèle du backend pour avoir un snapshot automatique chaque soir à 23h UTC : <code className="font-mono text-[10px]">uv run arq app.worker.settings.WorkerSettings</code>
                </li>
              </ul>
            </div>
          </div>
        </Card>
      )}

      {recElo.data && (
        <section className="mb-6">
          <RecommendedEloCard data={recElo.data} />
        </section>
      )}

      {last && (
        <>
          <div className="text-xs text-[var(--muted)] mb-2 mt-2">
            Stats du dernier snapshot ({new Date(last.taken_at).toLocaleDateString("fr-FR")})
          </div>
          <section className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
            <Card>
              <CardTitle>Rating rapid</CardTitle>
              <CardValue>{last.rating_rapid ?? "—"}</CardValue>
              {first && first !== last && first.rating_rapid != null && last.rating_rapid != null && (
                <div className={`text-xs mt-1 tabular-nums ${last.rating_rapid - first.rating_rapid > 0 ? "text-[var(--accent)]" : last.rating_rapid - first.rating_rapid < 0 ? "text-[var(--danger)]" : "text-[var(--muted)]"}`}>
                  {last.rating_rapid - first.rating_rapid > 0 ? "+" : ""}{last.rating_rapid - first.rating_rapid} sur la période
                </div>
              )}
            </Card>
            <Card>
              <CardTitle>Parties (7 derniers jours)</CardTitle>
              <CardValue>{last.games_7d ?? 0}</CardValue>
              <div className="text-[10px] text-[var(--muted)] mt-1">fenêtre roulante, indépendante du filtre</div>
            </Card>
            <Card>
              <CardTitle>Puzzles résolus (7j)</CardTitle>
              <CardValue>{last.exercises_solved_7d ?? 0}</CardValue>
              <div className="text-[10px] text-[var(--muted)] mt-1">fenêtre roulante 7 jours</div>
            </Card>
            <Card>
              <CardTitle>Cartes répertoire (7j)</CardTitle>
              <CardValue>{last.rep_cards_reviewed_7d ?? 0}</CardValue>
              <div className="text-[10px] text-[var(--muted)] mt-1">fenêtre roulante 7 jours</div>
            </Card>
          </section>
        </>
      )}

      <div className="grid md:grid-cols-2 gap-4">
        <Card>
          <CardHeader><CardTitle>Rating</CardTitle></CardHeader>
          <div className="h-56">
            <ResponsiveContainer>
              <LineChart data={data}>
                <CartesianGrid stroke="var(--border)" strokeDasharray="2 2" />
                <XAxis dataKey="t" stroke="var(--muted)" fontSize={10} />
                <YAxis stroke="var(--muted)" fontSize={10} />
                <Tooltip contentStyle={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 6, fontSize: 11 }} />
                <Line type="monotone" dataKey="rapid" stroke="var(--accent)" strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="blitz" stroke="var(--info)" strokeWidth={1.5} dot={false} />
                <Line type="monotone" dataKey="bullet" stroke="var(--warning)" strokeWidth={1.5} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <Card>
          <CardHeader><CardTitle>Winrate (%)</CardTitle></CardHeader>
          <div className="h-56">
            <ResponsiveContainer>
              <LineChart data={data}>
                <CartesianGrid stroke="var(--border)" strokeDasharray="2 2" />
                <XAxis dataKey="t" stroke="var(--muted)" fontSize={10} />
                <YAxis stroke="var(--muted)" fontSize={10} domain={[0, 100]} />
                <Tooltip contentStyle={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 6, fontSize: 11 }} />
                <Line type="monotone" dataKey="wr_w" name="blancs" stroke="#f0d9b5" strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="wr_b" name="noirs" stroke="#b58863" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <Card>
          <CardHeader><CardTitle>Activité (7j roulant)</CardTitle></CardHeader>
          <div className="h-56">
            <ResponsiveContainer>
              <LineChart data={data}>
                <CartesianGrid stroke="var(--border)" strokeDasharray="2 2" />
                <XAxis dataKey="t" stroke="var(--muted)" fontSize={10} />
                <YAxis stroke="var(--muted)" fontSize={10} />
                <Tooltip contentStyle={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 6, fontSize: 11 }} />
                <Line type="monotone" dataKey="games_7d" name="parties" stroke="var(--accent)" strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="ex_7d" name="puzzles" stroke="var(--info)" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <Card>
          <CardHeader><CardTitle>Sévérités</CardTitle></CardHeader>
          {last?.weakness_severities ? (
            <ul className="space-y-1.5 text-sm">
              {Object.entries(last.weakness_severities)
                .sort(([, a], [, b]) => (b as number) - (a as number))
                .slice(0, 10)
                .map(([k, v]) => (
                  <li key={k} className="flex items-center gap-3">
                    <span className="w-32 truncate text-[var(--muted)]">{k}</span>
                    <div className="flex-1 h-2 bg-[var(--surface-2)] rounded overflow-hidden">
                      <div className="h-full bg-[var(--danger)]" style={{ width: `${Math.round((v as number) * 100)}%` }} />
                    </div>
                    <span className="font-mono tabular-nums text-xs text-[var(--muted)] w-8 text-right">{Math.round((v as number) * 100)}</span>
                  </li>
                ))}
            </ul>
          ) : (
            <div className="text-sm text-[var(--muted)]">Pas encore de snapshot.</div>
          )}
        </Card>
      </div>

      <div className="grid md:grid-cols-2 gap-4 mt-4">
        {personality.data && <PersonalityCard data={personality.data} />}
        {ctx.data && <ContextualPatternsCard data={ctx.data} />}
        {calib.data && <EloCalibrationCard data={calib.data} />}
        {openings.data && <OpeningRecommendationsCard data={openings.data} />}
      </div>
    </div>
  );
}
