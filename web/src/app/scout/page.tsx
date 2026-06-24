"use client";

import { useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api";
import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import { cn } from "@/lib/utils";
import type { ScoutPayload } from "./_components";

type ScoutListItem = {
  opponent_username: string;
  last_scouted_at: string;
  snapshot_id: number;
  snapshot_count: number;
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
};

export default function ScoutListPage() {
  const qc = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [username, setUsername] = useState("");
  const [maxMonths, setMaxMonths] = useState(3);
  const [genPlan, setGenPlan] = useState(false);

  const listQ = useQuery<{ items: ScoutListItem[]; total: number }>({
    queryKey: ["scouts"],
    queryFn: () => api<{ items: ScoutListItem[]; total: number }>("/coach/scout"),
  });

  const scout = useMutation({
    mutationFn: () =>
      api<ScoutPayload>("/coach/scout", {
        json: { opponent_username: username.trim(), max_months: maxMonths, max_games: 100, generate_plan: genPlan },
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["scouts"] });
      setShowForm(false);
      setUsername("");
    },
  });

  return (
    <div className="px-4 py-6 md:px-8 md:py-8 max-w-6xl">
      <header className="mb-6 flex items-end justify-between">
        <div>
          <div className="text-xs uppercase tracking-widest text-[var(--muted)]">Analyse</div>
          <h1 className="text-3xl font-semibold mt-1">Scouts adversaires</h1>
          <p className="text-sm text-[var(--muted)] mt-2">Tes rapports persistés. Clique un adversaire pour voir son détail et son évolution.</p>
        </div>
        <button
          onClick={() => setShowForm((v) => !v)}
          className="px-4 py-2 rounded bg-[var(--accent)] text-black font-medium text-sm"
        >
          {showForm ? "× Annuler" : "+ Nouveau scout"}
        </button>
      </header>

      {showForm && (
        <Card className="mb-4">
          <div className="flex gap-3 items-end flex-wrap">
            <div className="flex-1 min-w-[200px]">
              <div className="text-xs text-[var(--muted)] mb-1">Username chess.com</div>
              <input
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="ex: hikaru"
                className="w-full bg-[var(--surface-2)] border rounded px-3 py-2 font-mono text-sm"
                onKeyDown={(e) => { if (e.key === "Enter" && username.trim()) scout.mutate(); }}
              />
            </div>
            <div>
              <div className="text-xs text-[var(--muted)] mb-1">Mois max</div>
              <input
                type="number" min={1} max={24} value={maxMonths}
                onChange={(e) => setMaxMonths(Number(e.target.value))}
                className="w-20 bg-[var(--surface-2)] border rounded px-3 py-2 text-sm tabular-nums"
              />
            </div>
            <label className="flex items-center gap-2 text-sm pb-2">
              <input type="checkbox" checked={genPlan} onChange={(e) => setGenPlan(e.target.checked)} />
              <span>Plan LLM <span className="text-[var(--muted)]">(~2 min)</span></span>
            </label>
            <button
              onClick={() => scout.mutate()}
              disabled={!username.trim() || scout.isPending}
              className="px-4 py-2 rounded bg-[var(--accent)] text-black font-medium text-sm disabled:opacity-50"
            >
              {scout.isPending ? "Scout..." : "Scouter →"}
            </button>
          </div>
          {scout.isPending && (
            <div className="mt-3 text-xs text-[var(--info)]">
              {genPlan ? "Import + analyse + plan LLM. ~1-2 min…" : "Import + analyse rapide. ~5-30s…"}
            </div>
          )}
          {scout.isError && (
            <div className="mt-3 text-xs text-[var(--danger)]">
              {scout.error instanceof ApiError ? JSON.stringify(scout.error.body) : String(scout.error)}
            </div>
          )}
        </Card>
      )}

      {listQ.isLoading && <div className="text-sm text-[var(--muted)]">Chargement…</div>}
      {listQ.data && listQ.data.items.length === 0 && !showForm && (
        <Card className="text-center py-12 text-[var(--muted)]">
          <div className="text-base">Aucun adversaire scouté pour l&apos;instant.</div>
          <button
            onClick={() => setShowForm(true)}
            className="mt-3 text-sm text-[var(--accent)] hover:underline"
          >Lance ton premier scout →</button>
        </Card>
      )}

      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {listQ.data?.items.map((item) => (
          <Link key={item.opponent_username} href={`/scout/${item.opponent_username}`} className="block">
            <Card className="hover:border-[var(--accent)]/50 transition-colors h-full">
              <div className="flex items-center justify-between mb-2">
                <div className="font-mono font-medium truncate">{item.opponent_username}</div>
                <div className="text-xs text-[var(--muted)] tabular-nums shrink-0 ml-2">
                  {item.summary.current_rating ?? "—"}
                </div>
              </div>
              <div className="text-xs text-[var(--muted)] mb-3">
                Scouté {timeAgo(item.last_scouted_at)} · {item.snapshot_count} snapshot{item.snapshot_count > 1 ? "s" : ""}
              </div>
              <div className="flex items-center justify-between text-xs">
                <div>
                  {item.summary.games_total ?? 0} parties · {item.summary.wins ?? 0}W {item.summary.losses ?? 0}L
                </div>
                <div className="flex gap-0.5">
                  {(item.summary.last_10 || []).slice(0, 10).map((r, i) => (
                    <span
                      key={i}
                      className={cn(
                        "size-3 inline-flex items-center justify-center text-[8px] font-bold rounded-sm",
                        r === "W" ? "bg-[var(--accent)]/30 text-[var(--accent)]" :
                        r === "L" ? "bg-[var(--danger)]/30 text-[var(--danger)]" :
                        "bg-[var(--muted)]/30 text-[var(--muted)]",
                      )}
                    >{r}</span>
                  ))}
                </div>
              </div>
              {item.summary.top_weakness && (
                <div className="mt-2 text-xs">
                  <span className="text-[var(--muted)]">Faiblesse n°1 : </span>
                  <span className="font-mono">{item.summary.top_weakness}</span>
                </div>
              )}
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}

function timeAgo(iso: string): string {
  const then = new Date(iso).getTime();
  const diff = Math.max(0, Date.now() - then);
  const min = Math.floor(diff / 60_000);
  if (min < 1) return "à l'instant";
  if (min < 60) return `il y a ${min} min`;
  const h = Math.floor(min / 60);
  if (h < 24) return `il y a ${h}h`;
  const d = Math.floor(h / 24);
  return `il y a ${d}j`;
}
