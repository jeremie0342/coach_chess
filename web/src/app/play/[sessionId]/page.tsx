"use client";

import { use, useEffect, useMemo, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Chess } from "chess.js";
import { api } from "@/lib/api";
import { Board } from "@/components/chess/Board";
import { EvalBar } from "@/components/chess/EvalBar";
import { AlertTriangle, Undo2 } from "lucide-react";
import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import { cn } from "@/lib/utils";
import type { PlaySession, MoveResponse } from "@/types/play";

export default function PlaySessionPage({ params }: { params: Promise<{ sessionId: string }> }) {
  const { sessionId } = use(params);
  const id = Number(sessionId);
  const qc = useQueryClient();

  const q = useQuery<PlaySession>({
    queryKey: ["play-session", id],
    queryFn: () => api<PlaySession>(`/train/play/${id}`),
  });

  const sess = q.data;
  const orientation = sess?.user_color ?? "white";

  const [optimisticFen, setOptimisticFen] = useState<string | null>(null);
  const fen = optimisticFen ?? sess?.current_fen ?? "";
  useEffect(() => { setOptimisticFen(null); }, [sess?.current_fen]);

  const [lastEval, setLastEval] = useState<{ cp: number | null; mate: number | null }>({ cp: null, mate: null });
  const [lastQuality, setLastQuality] = useState<string | null>(null);

  const move = useMutation({
    mutationFn: (uci: string) => api<MoveResponse>(`/train/play/${id}/move`, { json: { move: uci } }),
    onSuccess: (r) => {
      // Backend may return accepted=false (illegal move) — surface that.
      if (!r.accepted) {
        // Roll back the optimistic update so the board snaps back.
        setOptimisticFen(null);
      }
      setLastEval({ cp: r.eval_cp, mate: r.eval_mate });
      setLastQuality(r.user_quality);
      qc.invalidateQueries({ queryKey: ["play-session", id] });
    },
    onError: () => {
      // Network error or backend exception — undo the optimistic move so the
      // user can try again or see clearly that the position hasn't advanced.
      setOptimisticFen(null);
    },
  });

  const abandon = useMutation({
    mutationFn: () => api(`/train/play/${id}/abandon`, { method: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["play-session", id] }),
  });

  const undo = useMutation({
    mutationFn: () => api<{ accepted: boolean; error: string | null; current_fen: string; undos_remaining: number }>(
      `/train/play/${id}/undo`, { method: "POST" },
    ),
    onSuccess: (r) => {
      if (r.accepted) {
        setOptimisticFen(null);
        setLastQuality(null);
        setLastEval({ cp: null, mate: null });
      }
      qc.invalidateQueries({ queryKey: ["play-session", id] });
    },
  });

  const sideToMove: "white" | "black" = useMemo(() => {
    if (!fen) return "white";
    try { return new Chess(fen).turn() === "w" ? "white" : "black"; } catch { return "white"; }
  }, [fen]);

  const isOver = !!sess && sess.status.toLowerCase() !== "active";

  const handleMove = ({ from, to, promotion }: { from: string; to: string; promotion?: string }) => {
    if (!sess || isOver) return false;
    if (sideToMove !== orientation) return false;
    try {
      const c = new Chess(fen);
      const mv = c.move({ from, to, promotion: promotion ?? "q" });
      if (!mv) return false;
      setOptimisticFen(c.fen());
      move.mutate(`${from}${to}${mv.promotion ?? ""}`);
      return true;
    } catch { return false; }
  };

  return (
    <div className="px-4 py-6 md:px-8 md:py-8 max-w-7xl">
      <header className="mb-6 flex items-end justify-between">
        <div>
          <div className="text-xs uppercase tracking-widest text-[var(--muted)]">Partie #{id}</div>
          <h1 className="text-2xl font-semibold mt-1">vs Stockfish {sess?.sf_elo ?? ""}</h1>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          {sess && sess.max_undos > 0 && (
            <button
              onClick={() => undo.mutate()}
              disabled={(sess.undos_remaining ?? 0) <= 0 || undo.isPending}
              className="text-xs px-3 py-1.5 rounded border bg-[var(--surface-2)] hover:bg-[var(--surface)] disabled:opacity-40"
              title={sess.undos_remaining > 0 ? "Reprendre ton dernier coup" : "Plus d'annulations"}
            >
              <Undo2 className="size-3 inline mr-1" /> Annuler ({sess.undos_remaining}/{sess.max_undos})
            </button>
          )}
          <button
            onClick={() => abandon.mutate()}
            className="text-xs px-3 py-1.5 rounded border border-[var(--danger)]/40 text-[var(--danger)] hover:bg-[var(--danger)]/10"
          >
            Abandonner
          </button>
        </div>
      </header>

      {isOver && sess && (
        <div className={cn(
          "mb-4 rounded border p-4 text-sm",
          sess.status === "user_won" ? "border-[var(--accent)]/60 bg-[var(--accent)]/15 text-[var(--accent)]" :
          sess.status === "user_lost" ? "border-[var(--danger)]/60 bg-[var(--danger)]/15 text-[var(--danger)]" :
          sess.status === "draw" ? "border-[var(--info)]/60 bg-[var(--info)]/15" :
          "border-[var(--muted)]/60 bg-[var(--surface-2)]",
        )}>
          <div className="text-xs uppercase tracking-widest opacity-70">Partie terminée</div>
          <div className="text-lg font-semibold mt-1">
            {sess.status === "user_won" && "Victoire"}
            {sess.status === "user_lost" && "Défaite"}
            {sess.status === "draw" && "Nulle"}
            {sess.status === "abandoned" && "Abandonnée"}
          </div>
          {sess.result_reason && (
            <div className="text-xs mt-1 opacity-80">
              Raison : {sess.result_reason === "opening_deviation"
                ? "déviation théorique sans annulation restante"
                : sess.result_reason}
            </div>
          )}
          <a href="/play" className="mt-3 inline-block text-xs px-3 py-1.5 rounded border bg-[var(--surface)] hover:bg-[var(--surface-2)]">
            Nouvelle partie →
          </a>
        </div>
      )}

      {sess?.source === "scout_simulation" && (
        <div className="mb-4 rounded border border-[var(--accent)]/40 bg-[var(--accent)]/10 p-3 text-sm">
          <div className="text-xs uppercase tracking-widest text-[var(--muted)]">Simulation vs adversaire</div>
          <div className="font-medium mt-1">
            Stockfish joue à ELO {sess.sf_elo} et suit les ouvertures de{" "}
            <span className="font-mono">{(sess.source_ref as { opponent_username?: string } | null)?.opponent_username}</span>
            {(sess.source_ref as { opp_rating?: number } | null)?.opp_rating && (
              <span className="text-xs text-[var(--muted)]"> (rating {(sess.source_ref as { opp_rating?: number } | null)?.opp_rating})</span>
            )}
          </div>
        </div>
      )}

      {sess?.opening_key && (
        <div className={cn(
          "mb-4 rounded border p-3 text-sm",
          sess.opening_status === "in_book"
            ? "border-[var(--info)]/40 bg-[var(--info)]/10"
            : sess.result_reason === "opening_deviation"
              ? "border-[var(--danger)]/40 bg-[var(--danger)]/10"
              : "border-[var(--accent)]/40 bg-[var(--accent)]/10",
        )}>
          <div className="flex items-center justify-between flex-wrap gap-2">
            <div>
              <div className="text-xs uppercase tracking-widest text-[var(--muted)]">
                {sess.opening_status === "in_book" ? "Phase d'ouverture" : "Ouverture"}
              </div>
              <div className="font-medium">
                {sess.opening_key}
                {sess.opening_branch_label ? ` — ${sess.opening_branch_label}` : " — Mainline"}
              </div>
            </div>
            <div className="text-xs tabular-nums">
              {sess.opening_ply_index ?? 0} / {sess.opening_total_plies ?? 0} demi-coups
              {sess.opening_status === "completed" && (
                <span className="ml-2 text-[var(--accent)]">Ligne complétée — jeu libre</span>
              )}
              {sess.result_reason === "opening_deviation" && (
                <span className="ml-2 text-[var(--danger)] inline-flex items-center gap-1"><AlertTriangle className="size-3" /> Défaite : déviation théorique</span>
              )}
            </div>
          </div>
          {sess.opening_status === "in_book" && sideToMove === orientation && (sess.undos_remaining ?? 0) === 0 && (
            <div className="mt-2 text-xs text-[var(--danger)]">
              <AlertTriangle className="size-3 inline mr-1" /> Plus d&apos;annulation — la moindre déviation = défaite.
            </div>
          )}
        </div>
      )}

      <div className="flex flex-col lg:flex-row gap-6">
        <div className="w-full max-w-[520px] mx-auto lg:mx-0 flex gap-3 items-stretch">
          <EvalBar cp={lastEval.cp} mate={lastEval.mate} orientation={orientation} className="self-stretch" />
          <div className="flex-1 min-w-0">
            <Board fen={fen} orientation={orientation} draggableColor={isOver ? undefined : orientation} onMove={handleMove} size={520} />
          </div>
        </div>
        <div className="flex-1 space-y-4 min-w-0">
          <Card>
            <CardHeader><CardTitle>État</CardTitle></CardHeader>
            <div className="text-sm">
              <Row label="Statut" value={sess?.status ?? "—"} />
              <Row
                label="Trait"
                value={
                  move.isPending
                    ? "Stockfish réfléchit…"
                    : sideToMove === orientation ? "à toi" : "Stockfish à jouer"
                }
                tone={move.isPending ? "text-[var(--info)]" : undefined}
              />
              <Row label="Coups joués" value={String(sess?.moves.length ?? 0)} />
              {lastQuality && <Row label="Dernier coup" value={lastQuality} tone={qualityTone(lastQuality)} />}
            </div>
            {move.isError && (
              <div className="mt-3 rounded border border-[var(--danger)]/40 bg-[var(--danger)]/10 p-2 text-xs text-[var(--danger)]">
                <div className="font-medium">Le coup n'a pas été enregistré</div>
                <div className="mt-1">
                  {move.error instanceof Error ? move.error.message : String(move.error)}
                </div>
                <button
                  onClick={() => move.reset()}
                  className="mt-2 text-xs px-2 py-1 rounded border bg-[var(--surface-2)] hover:bg-[var(--surface)]"
                >
                  OK, je rejoue
                </button>
              </div>
            )}
            {move.data && !move.data.accepted && move.data.error && (
              <div className="mt-3 rounded border border-[var(--warning)]/40 bg-[var(--warning)]/10 p-2 text-xs text-[var(--warning)]">
                <div className="font-medium">Coup refusé : {move.data.error}</div>
              </div>
            )}
          </Card>

          <Card>
            <CardHeader><CardTitle>Coups</CardTitle></CardHeader>
            <ol className="text-sm font-mono space-y-0.5 max-h-[300px] overflow-y-auto">
              {sess?.moves.map((m) => (
                <li key={m.ply} className={cn(m.is_user ? "text-[var(--foreground)]" : "text-[var(--muted)]")}>
                  <span className="text-[var(--muted)] mr-2 tabular-nums">{m.ply}.</span>
                  {m.san}
                </li>
              ))}
            </ol>
          </Card>
        </div>
      </div>
    </div>
  );
}

function Row({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="flex justify-between py-1.5 border-b border-[var(--border)] last:border-0">
      <span className="text-[var(--muted)]">{label}</span>
      <span className={tone ?? ""}>{value}</span>
    </div>
  );
}

function qualityTone(q: string) {
  switch (q) {
    case "blunder": return "text-[var(--danger)]";
    case "mistake": return "text-[var(--warning)]";
    case "inaccuracy": return "text-[var(--info)]";
    case "best": case "excellent": return "text-[var(--accent)]";
    default: return "text-[var(--muted)]";
  }
}
