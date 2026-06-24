"use client";

import { use, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { RotateCw, Swords } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import { cn } from "@/lib/utils";
import { ScoutResult, type ScoutPayload } from "../_components";

type HistorySnapshot = {
  snapshot_id: number;
  scouted_at: string;
  summary: {
    games_total?: number;
    wins?: number;
    losses?: number;
    draws?: number;
    current_rating?: number | null;
    peak_rating?: number | null;
    last_10?: string[];
    top_weakness?: string | null;
  };
  weaknesses: { category: string; phase: string | null; severity: number; occurrences: number }[];
  opening_profile: {
    first_move_as_white: { uci?: string; san?: string; games?: number; winrate?: number }[];
    response_to_e4: { uci?: string; san?: string; games?: number; winrate?: number }[];
    response_to_d4: { uci?: string; san?: string; games?: number; winrate?: number }[];
  };
};

export default function ScoutDetailPage({ params }: { params: Promise<{ username: string }> }) {
  const { username } = use(params);
  const router = useRouter();
  const qc = useQueryClient();

  const latestQ = useQuery<ScoutPayload>({
    queryKey: ["scout", username],
    queryFn: () => api<ScoutPayload>(`/coach/scout/${username}`),
  });

  const historyQ = useQuery<{ opponent_username: string; history: HistorySnapshot[] }>({
    queryKey: ["scout", username, "history"],
    queryFn: () => api(`/coach/scout/${username}/history`),
  });

  const refresh = useMutation({
    mutationFn: () =>
      api<ScoutPayload>("/coach/scout", {
        json: { opponent_username: username, max_months: 3, max_games: 100, generate_plan: false },
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["scout", username] });
      qc.invalidateQueries({ queryKey: ["scout", username, "history"] });
      qc.invalidateQueries({ queryKey: ["scouts"] });
    },
  });

  const del = useMutation({
    mutationFn: () => api<{ deleted: number }>(`/coach/scout/${username}`, { method: "DELETE" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["scouts"] });
      router.push("/scout");
    },
  });

  const [showSim, setShowSim] = useState(false);
  const [simColor, setSimColor] = useState<"white" | "black">("white");
  const [simUndos, setSimUndos] = useState<number>(0);

  const simulate = useMutation({
    mutationFn: () =>
      api<{ session_id: number; sf_elo: number; skill_level: number; opp_rating: number | null; script_plies: number }>(
        `/coach/scout/${username}/simulate`,
        { json: { my_color: simColor, max_undos: simUndos } },
      ),
    onSuccess: (r) => router.push(`/play/${r.session_id}`),
  });

  return (
    <div className="px-4 py-6 md:px-8 md:py-8 max-w-6xl">
      <header className="mb-6 flex items-end justify-between flex-wrap gap-2">
        <div>
          <Link href="/scout" className="text-xs text-[var(--muted)] hover:text-[var(--foreground)]">← Tous les scouts</Link>
          <h1 className="text-3xl font-semibold mt-1 font-mono">{username}</h1>
          {latestQ.data?.scouted_at && (
            <div className="text-xs text-[var(--muted)] mt-1">
              Dernier snapshot : {new Date(latestQ.data.scouted_at).toLocaleString("fr-FR")}
            </div>
          )}
        </div>
        <div className="flex gap-2 flex-wrap">
          <button
            onClick={() => setShowSim((v) => !v)}
            className="px-3 py-2 rounded bg-[var(--accent)] text-black font-medium text-sm inline-flex items-center gap-1.5"
          >
            <Swords className="size-3.5" /> Simuler une partie
          </button>
          <button
            onClick={() => refresh.mutate()}
            disabled={refresh.isPending}
            className="px-3 py-2 rounded border bg-[var(--surface-2)] text-sm disabled:opacity-50 inline-flex items-center gap-1.5"
          >
            <RotateCw className={`size-3.5 ${refresh.isPending ? "animate-spin" : ""}`} />
            {refresh.isPending ? "Refresh…" : "Refresh scout"}
          </button>
          <button
            onClick={() => {
              if (confirm(`Supprimer tous les snapshots de ${username} ?`)) del.mutate();
            }}
            className="px-3 py-2 rounded border border-[var(--danger)]/40 text-[var(--danger)] text-sm hover:bg-[var(--danger)]/10"
          >
            Supprimer
          </button>
        </div>
      </header>

      {showSim && (
        <Card className="mb-4 border-l-4 border-l-[var(--accent)]">
          <div className="text-xs uppercase tracking-widest text-[var(--muted)]">Simuler une partie vs <span className="font-mono">{username}</span></div>
          <div className="text-sm text-[var(--muted)] mt-1 mb-3">
            Stockfish joue à son ELO (ajusté depuis son rating chess.com) ET suit ses ouvertures habituelles déduites de ses parties passées. Hors livre, SF joue normalement.
          </div>
          <div className="flex gap-3 items-end flex-wrap">
            <div>
              <div className="text-xs text-[var(--muted)] mb-1">Ta couleur</div>
              <div className="flex gap-1">
                {(["white", "black"] as const).map((c) => (
                  <button
                    key={c}
                    onClick={() => setSimColor(c)}
                    className={cn(
                      "text-xs px-3 py-2 rounded border",
                      simColor === c
                        ? "bg-[var(--accent)] text-black border-[var(--accent)]"
                        : "bg-[var(--surface-2)] text-[var(--muted)]",
                    )}
                  >
                    {c === "white" ? "Blancs" : "Noirs"}
                  </button>
                ))}
              </div>
            </div>
            <div>
              <div className="text-xs text-[var(--muted)] mb-1">Annulations</div>
              <div className="flex gap-1">
                {[0, 1, 3, 999].map((u) => (
                  <button
                    key={u}
                    onClick={() => setSimUndos(u)}
                    className={cn(
                      "text-xs px-2 py-2 rounded border",
                      simUndos === u
                        ? "bg-[var(--accent)] text-black border-[var(--accent)]"
                        : "bg-[var(--surface-2)] text-[var(--muted)]",
                    )}
                  >
                    {u === 999 ? "Illimité" : u}
                  </button>
                ))}
              </div>
            </div>
            <button
              onClick={() => simulate.mutate()}
              disabled={simulate.isPending}
              className="ml-auto px-4 py-2 rounded bg-[var(--accent)] text-black font-medium text-sm disabled:opacity-50"
            >
              {simulate.isPending ? "Lancement…" : "Lancer la simulation →"}
            </button>
          </div>
          {simulate.isError && (
            <div className="mt-3 text-xs text-[var(--danger)]">
              {simulate.error instanceof ApiError ? JSON.stringify(simulate.error.body) : String(simulate.error)}
            </div>
          )}
        </Card>
      )}

      {refresh.isPending && (
        <Card className="border-[var(--info)]/40 bg-[var(--info)]/10 text-sm mb-4">
          Refresh en cours… Import des dernières parties + ré-analyse. ~5-30s.
        </Card>
      )}
      {refresh.isError && (
        <Card className="border-[var(--danger)]/40 text-sm text-[var(--danger)] mb-4">
          {refresh.error instanceof ApiError ? JSON.stringify(refresh.error.body) : String(refresh.error)}
        </Card>
      )}

      {historyQ.data && historyQ.data.history.length >= 2 && (
        <ProgressionSection history={historyQ.data.history} />
      )}

      {latestQ.isLoading && <div className="text-sm text-[var(--muted)]">Chargement…</div>}
      {latestQ.isError && (
        <Card className="border-[var(--danger)]/40 text-sm text-[var(--danger)]">
          {latestQ.error instanceof ApiError ? JSON.stringify(latestQ.error.body) : String(latestQ.error)}
        </Card>
      )}

      {latestQ.data && <ScoutResult data={latestQ.data} />}
    </div>
  );
}

function ProgressionSection({ history }: { history: HistorySnapshot[] }) {
  // Latest snapshot is last in array (sorted asc)
  const latest = history[history.length - 1];
  const previous = history[history.length - 2];

  const ratingTimeline = useMemo(() => {
    return history.map((h) => ({
      date: new Date(h.scouted_at).toLocaleDateString("fr-FR", { day: "2-digit", month: "2-digit" }),
      rating: h.summary.current_rating ?? null,
      games: h.summary.games_total ?? 0,
      wr: ((h.summary.wins ?? 0) + 0.5 * (h.summary.draws ?? 0)) / Math.max(h.summary.games_total ?? 1, 1),
    }));
  }, [history]);

  const weaknessDiff = useMemo(() => {
    if (!previous) return null;
    const prevSet = new Map(previous.weaknesses.map((w) => [w.category + (w.phase ?? ""), w]));
    const currSet = new Map(latest.weaknesses.map((w) => [w.category + (w.phase ?? ""), w]));
    const added: typeof latest.weaknesses = [];
    const removed: typeof latest.weaknesses = [];
    const changed: { category: string; phase: string | null; before: number; after: number }[] = [];
    for (const [k, w] of currSet) {
      if (!prevSet.has(k)) added.push(w);
      else {
        const before = prevSet.get(k)!.severity;
        if (Math.abs(before - w.severity) > 0.02) changed.push({ category: w.category, phase: w.phase, before, after: w.severity });
      }
    }
    for (const [k, w] of prevSet) {
      if (!currSet.has(k)) removed.push(w);
    }
    return { added, removed, changed };
  }, [latest, previous]);

  const openingDiff = useMemo(() => {
    if (!previous) return null;
    const compare = (curr: HistorySnapshot["opening_profile"]["first_move_as_white"], prev: HistorySnapshot["opening_profile"]["first_move_as_white"]) => {
      const map = new Map(prev.map((m) => [m.san ?? m.uci, m]));
      const out: { san: string; before: number; after: number }[] = [];
      for (const m of curr) {
        const key = m.san ?? m.uci ?? "";
        const beforeGames = map.get(key)?.games ?? 0;
        const afterGames = m.games ?? 0;
        if (Math.abs(afterGames - beforeGames) >= 2) {
          out.push({ san: key, before: beforeGames, after: afterGames });
        }
      }
      return out;
    };
    return {
      first_move_white: compare(latest.opening_profile.first_move_as_white, previous.opening_profile.first_move_as_white),
      resp_e4: compare(latest.opening_profile.response_to_e4, previous.opening_profile.response_to_e4),
      resp_d4: compare(latest.opening_profile.response_to_d4, previous.opening_profile.response_to_d4),
    };
  }, [latest, previous]);

  const ratingDelta = (latest.summary.current_rating ?? 0) - (previous?.summary.current_rating ?? 0);

  return (
    <div className="mb-6 space-y-4">
      <Card className="border-l-4 border-l-[var(--info)]">
        <CardHeader>
          <CardTitle>Progression sur {history.length} snapshots</CardTitle>
          <span className="text-xs text-[var(--muted)]">
            Du {new Date(history[0].scouted_at).toLocaleDateString("fr-FR")} à aujourd&apos;hui
          </span>
        </CardHeader>

        <div className="space-y-4">
          <div>
            <div className="text-xs uppercase tracking-widest text-[var(--muted)] mb-2">Timeline rating</div>
            <RatingChart data={ratingTimeline} />
          </div>

          {ratingDelta !== 0 && (
            <div className="text-sm">
              <span className="text-[var(--muted)]">Rating depuis le scout précédent : </span>
              <span className={cn(
                "font-mono font-medium tabular-nums",
                ratingDelta > 0 ? "text-[var(--accent)]" : "text-[var(--danger)]",
              )}>
                {ratingDelta > 0 ? "+" : ""}{ratingDelta}
              </span>
            </div>
          )}

          {weaknessDiff && (weaknessDiff.added.length + weaknessDiff.removed.length + weaknessDiff.changed.length > 0) && (
            <div>
              <div className="text-xs uppercase tracking-widest text-[var(--muted)] mb-2">Diff faiblesses vs scout précédent</div>
              <ul className="text-sm space-y-1">
                {weaknessDiff.added.map((w, i) => (
                  <li key={`a-${i}`} className="text-[var(--danger)]">
                    <b>+ Nouvelle :</b> <span className="font-mono">{w.category}</span> {w.phase ?? ""} (sev {w.severity.toFixed(2)})
                  </li>
                ))}
                {weaknessDiff.removed.map((w, i) => (
                  <li key={`r-${i}`} className="text-[var(--accent)]">
                    <b>− Disparue :</b> <span className="font-mono">{w.category}</span> {w.phase ?? ""}
                  </li>
                ))}
                {weaknessDiff.changed.map((c, i) => (
                  <li key={`c-${i}`} className="text-[var(--muted)]">
                    <span className="font-mono">{c.category}</span> {c.phase ?? ""} :{" "}
                    <span className="tabular-nums">{c.before.toFixed(2)} → {c.after.toFixed(2)}</span>
                    {c.after > c.before
                      ? <span className="text-[var(--danger)]"> (s&apos;aggrave)</span>
                      : <span className="text-[var(--accent)]"> (s&apos;améliore)</span>}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {openingDiff && (openingDiff.first_move_white.length + openingDiff.resp_e4.length + openingDiff.resp_d4.length > 0) && (
            <div>
              <div className="text-xs uppercase tracking-widest text-[var(--muted)] mb-2">Diff ouvertures vs scout précédent</div>
              <div className="text-sm space-y-1">
                {openingDiff.first_move_white.map((d, i) => (
                  <div key={`fw-${i}`}>
                    <span className="text-[var(--muted)]">1.</span>
                    <span className="font-mono">{d.san}</span> joué <span className="tabular-nums">{d.before} → {d.after}</span>
                  </div>
                ))}
                {openingDiff.resp_e4.map((d, i) => (
                  <div key={`e4-${i}`}>
                    <span className="text-[var(--muted)]">1.e4 →</span>
                    <span className="font-mono ml-1">{d.san}</span> joué <span className="tabular-nums">{d.before} → {d.after}</span>
                  </div>
                ))}
                {openingDiff.resp_d4.map((d, i) => (
                  <div key={`d4-${i}`}>
                    <span className="text-[var(--muted)]">1.d4 →</span>
                    <span className="font-mono ml-1">{d.san}</span> joué <span className="tabular-nums">{d.before} → {d.after}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          <details className="text-xs">
            <summary className="text-[var(--muted)] cursor-pointer hover:text-[var(--foreground)]">Tous les snapshots ({history.length})</summary>
            <ul className="mt-2 space-y-1 ml-2">
              {[...history].reverse().map((h) => (
                <li key={h.snapshot_id} className="tabular-nums">
                  {new Date(h.scouted_at).toLocaleString("fr-FR")} — rating {h.summary.current_rating ?? "—"}, {h.summary.games_total ?? 0} parties
                </li>
              ))}
            </ul>
          </details>
        </div>
      </Card>
    </div>
  );
}

function RatingChart({ data }: { data: { date: string; rating: number | null; wr: number }[] }) {
  const ratings = data.map((d) => d.rating).filter((r): r is number => r != null);
  if (ratings.length === 0) {
    return <div className="text-xs text-[var(--muted)]">Pas de rating disponible.</div>;
  }
  const min = Math.min(...ratings);
  const max = Math.max(...ratings);
  const range = Math.max(max - min, 50);
  const W = 800;
  const H = 80;
  const step = data.length > 1 ? W / (data.length - 1) : 0;
  const points = data.map((d, i) => {
    const x = i * step;
    const y = d.rating == null ? H / 2 : H - ((d.rating - min) / range) * (H - 12) - 6;
    return { x, y, d };
  });
  const path = points.map((p, i) => `${i === 0 ? "M" : "L"} ${p.x} ${p.y}`).join(" ");
  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-20" preserveAspectRatio="none">
        <path d={path} stroke="var(--accent)" strokeWidth="2" fill="none" />
        {points.map((p, i) => (
          <circle key={i} cx={p.x} cy={p.y} r="3" fill="var(--accent)">
            <title>{p.d.date} — {p.d.rating ?? "—"} ({Math.round(p.d.wr * 100)}%wr)</title>
          </circle>
        ))}
      </svg>
      <div className="flex justify-between text-xs text-[var(--muted)] tabular-nums mt-1">
        <span>{data[0].date} · {data[0].rating ?? "—"}</span>
        <span>{data[data.length - 1].date} · {data[data.length - 1].rating ?? "—"}</span>
      </div>
    </div>
  );
}
