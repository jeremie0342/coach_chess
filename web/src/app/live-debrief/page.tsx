"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api";
import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import { cn } from "@/lib/utils";
import type { DebriefPayload } from "./_components";

type DebriefListItem = {
  debrief_id: number;
  game_id: number | null;
  created_at: string;
  title: string | null;
  summary: {
    opening?: string | null;
    eco?: string | null;
    my_color?: string | null;
    moves_analyzed?: number;
    blunders?: number;
    mistakes?: number;
    top_cp_loss?: number | null;
    exercises_generated?: number;
  };
};

export default function LiveDebriefListPage() {
  const router = useRouter();
  const qc = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [pgn, setPgn] = useState("");
  const [explainLLM, setExplainLLM] = useState(true);
  const [genPuzzles, setGenPuzzles] = useState(true);

  const listQ = useQuery<{ items: DebriefListItem[]; total: number }>({
    queryKey: ["live-debriefs"],
    queryFn: () => api<{ items: DebriefListItem[]; total: number }>("/coach/live_debrief"),
  });

  const debrief = useMutation({
    mutationFn: () =>
      api<DebriefPayload>("/coach/live_debrief", {
        json: { pgn, generate_puzzles: genPuzzles, explain_with_llm: explainLLM },
      }),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ["live-debriefs"] });
      if (r.debrief_id) router.push(`/live-debrief/${r.debrief_id}`);
    },
  });

  return (
    <div className="px-4 py-6 md:px-8 md:py-8 max-w-6xl">
      <header className="mb-6 flex items-end justify-between flex-wrap gap-2">
        <div>
          <div className="text-xs uppercase tracking-widest text-[var(--muted)]">Analyse</div>
          <h1 className="text-3xl font-semibold mt-1">Live debriefs</h1>
          <p className="text-sm text-[var(--muted)] mt-2">Tes debriefs persistés. Clique pour rouvrir, ou colle un nouveau PGN.</p>
        </div>
        <button
          onClick={() => setShowForm((v) => !v)}
          className="px-4 py-2 rounded bg-[var(--accent)] text-black font-medium text-sm"
        >
          {showForm ? "× Annuler" : "+ Nouveau debrief"}
        </button>
      </header>

      {showForm && (
        <Card className="mb-4">
          <textarea
            value={pgn}
            onChange={(e) => setPgn(e.target.value)}
            placeholder='[Event "..."]&#10;1. e4 e5 2. Nf3 ...'
            className="w-full h-64 bg-[var(--surface-2)] border rounded px-3 py-2 text-xs font-mono resize-y"
          />
          <div className="flex items-center justify-between mt-4 flex-wrap gap-3">
            <div className="flex gap-4 text-sm">
              <label className="flex items-center gap-2">
                <input type="checkbox" checked={explainLLM} onChange={(e) => setExplainLLM(e.target.checked)} />
                <span>Explication LLM</span>
              </label>
              <label className="flex items-center gap-2">
                <input type="checkbox" checked={genPuzzles} onChange={(e) => setGenPuzzles(e.target.checked)} />
                <span>Générer puzzles</span>
              </label>
            </div>
            <button
              onClick={() => debrief.mutate()}
              disabled={!pgn.trim() || debrief.isPending}
              className="px-4 py-2 rounded bg-[var(--accent)] text-black font-medium text-sm disabled:opacity-50"
            >
              {debrief.isPending ? "Analyse..." : "Analyser →"}
            </button>
          </div>
          {debrief.isPending && (
            <div className="mt-3 text-xs text-[var(--info)]">Analyse Stockfish en cours… ~5-30s selon la longueur de la partie.</div>
          )}
          {debrief.isError && (
            <div className="mt-3 text-xs text-[var(--danger)]">
              {debrief.error instanceof ApiError ? JSON.stringify(debrief.error.body) : String(debrief.error)}
            </div>
          )}
        </Card>
      )}

      {listQ.isLoading && <div className="text-sm text-[var(--muted)]">Chargement…</div>}
      {listQ.data && listQ.data.items.length === 0 && !showForm && (
        <Card className="text-center py-12 text-[var(--muted)]">
          <div className="text-base">Aucun debrief encore.</div>
          <button onClick={() => setShowForm(true)} className="mt-3 text-sm text-[var(--accent)] hover:underline">
            Colle un PGN pour lancer ton premier debrief →
          </button>
        </Card>
      )}

      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {listQ.data?.items.map((item) => (
          <Link key={item.debrief_id} href={`/live-debrief/${item.debrief_id}`} className="block">
            <Card className="hover:border-[var(--accent)]/50 transition-colors h-full">
              <div className="flex items-center justify-between mb-1">
                <div className="text-sm font-medium truncate">{item.summary.opening || item.title || "Partie"}</div>
                <div className="text-xs text-[var(--muted)] font-mono shrink-0 ml-2">{item.summary.eco}</div>
              </div>
              <div className="text-xs text-[var(--muted)] mb-3">
                {timeAgo(item.created_at)}{item.summary.my_color === "white" ? " · Blancs" : item.summary.my_color === "black" ? " · Noirs" : ""}
              </div>
              <div className="text-xs space-y-1">
                <div className="flex justify-between">
                  <span className="text-[var(--muted)]">Coups analysés</span>
                  <span className="tabular-nums">{item.summary.moves_analyzed ?? 0}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-[var(--muted)]">Blunders / mistakes</span>
                  <span className="tabular-nums">
                    <span className={cn(item.summary.blunders ? "text-[var(--danger)]" : "")}>{item.summary.blunders ?? 0}</span>
                    {" / "}
                    <span className={cn(item.summary.mistakes ? "text-[var(--warning)]" : "")}>{item.summary.mistakes ?? 0}</span>
                  </span>
                </div>
                {(item.summary.top_cp_loss ?? 0) > 0 && (
                  <div className="flex justify-between">
                    <span className="text-[var(--muted)]">Pire perte</span>
                    <span className="tabular-nums text-[var(--danger)]">−{item.summary.top_cp_loss}cp</span>
                  </div>
                )}
                {(item.summary.exercises_generated ?? 0) > 0 && (
                  <div className="flex justify-between">
                    <span className="text-[var(--muted)]">Puzzles générés</span>
                    <span className="tabular-nums text-[var(--accent)]">{item.summary.exercises_generated}</span>
                  </div>
                )}
              </div>
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
