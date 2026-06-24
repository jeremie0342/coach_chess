"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useQuery, useMutation } from "@tanstack/react-query";
import { Chess } from "chess.js";
import { FlaskConical, AlertCircle } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import { Board } from "@/components/chess/Board";
import { cn } from "@/lib/utils";
import type { PlaySession, StartPlayIn } from "@/types/play";

type CriticalPosition = {
  move_id: number;
  game_id: number;
  ply: number;
  played_san: string;
  played_uci: string;
  fen_before: string;
  fen_after: string;
  best_san: string | null;
  best_uci: string | null;
  cp_loss: number;
  quality: string | null;
  pv: string[] | null;
  played_at: string | null;
  opening: string | null;
  eco: string | null;
};
type CriticalResp = { player: string; count: number; items: CriticalPosition[] };

type UndoMode = "0" | "1" | "3" | "999";

const UNDO_LABEL: Record<UndoMode, string> = {
  "0": "Strict (aucune)",
  "1": "1 annulation",
  "3": "3 annulations",
  "999": "Illimité",
};

export default function LabPositionsPage() {
  const router = useRouter();
  const [selected, setSelected] = useState<CriticalPosition | null>(null);
  const [skill, setSkill] = useState<number>(5);
  const [elo, setElo] = useState<number>(1320);
  const [undoMode, setUndoMode] = useState<UndoMode>("3");

  const q = useQuery<CriticalResp>({
    queryKey: ["critical-positions"],
    queryFn: () => api<CriticalResp>("/games/me/critical_positions", { query: { limit: 12 } }),
  });

  const start = useMutation({
    mutationFn: (pos: CriticalPosition) => {
      // Determine whose turn it is from the FEN.
      let user_color: "white" | "black" = "white";
      try { user_color = new Chess(pos.fen_before).turn() === "w" ? "white" : "black"; } catch {}
      const body: StartPlayIn & { max_undos?: number; source?: string; source_ref?: Record<string, unknown> } = {
        fen: pos.fen_before,
        user_color,
        skill_level: skill,
        sf_elo: elo,
        depth: 12,
        title: `Rejouer game #${pos.game_id} ply ${pos.ply}`,
        source: "critical_position",
        source_ref: { game_id: pos.game_id, ply: pos.ply, original_blunder: pos.played_san },
        max_undos: Number(undoMode),
      };
      return api<PlaySession>("/train/play/start", { json: body });
    },
    onSuccess: (s) => router.push(`/play/${s.id}`),
  });

  return (
    <div className="px-4 py-6 md:px-8 md:py-8 max-w-7xl">
      <header className="mb-6 flex items-center gap-3">
        <FlaskConical className="size-5 text-[var(--accent)]" />
        <div>
          <div className="text-xs uppercase tracking-widest text-[var(--muted)]">Entraînement</div>
          <h1 className="text-3xl font-semibold mt-1">Rejouer mes blunders</h1>
          <p className="text-sm text-[var(--muted)] mt-1 max-w-2xl">
            Choisis un moment-clé d'une partie perdue et affronte Stockfish à partir de cette position.
            Cette fois, tu peux choisir le meilleur coup — ou apprendre ce qui ne marche pas.
          </p>
        </div>
      </header>

      {q.isLoading && <Card className="animate-pulse h-32" />}

      {q.data && q.data.count === 0 && (
        <Card>
          <div className="text-sm">
            Aucune position critique détectée. Lance d'abord l'analyse Stockfish sur tes parties
            (page <Link href="/games" className="text-[var(--info)] hover:underline">Mes parties</Link>).
          </div>
        </Card>
      )}

      {q.data && q.data.count > 0 && (
        <div className="grid lg:grid-cols-[1fr_400px] gap-6">
          {/* List of critical positions */}
          <div className="grid sm:grid-cols-2 gap-3">
            {q.data.items.map((it) => (
              <button
                key={it.move_id}
                onClick={() => setSelected(it)}
                className={cn(
                  "text-left rounded-lg border bg-[var(--surface)] p-3 hover:border-[var(--accent)]/60 transition-colors",
                  selected?.move_id === it.move_id && "border-[var(--accent)]",
                )}
              >
                <div className="flex items-baseline justify-between mb-2">
                  <span className="text-xs text-[var(--muted)] font-mono">
                    #{it.game_id} · ply {it.ply}
                  </span>
                  <span className={cn(
                    "text-[10px] uppercase font-mono px-1.5 py-0.5 rounded",
                    it.quality?.toLowerCase().includes("blunder")
                      ? "bg-[var(--danger)]/20 text-[var(--danger)]"
                      : "bg-[var(--warning)]/20 text-[var(--warning)]",
                  )}>{(it.quality || "").split(".").pop()}</span>
                </div>
                <div className="text-sm">
                  <span className="font-mono text-[var(--danger)]">{it.played_san}</span>
                  <span className="text-[var(--muted)] mx-1">→</span>
                  <span className="font-mono text-[var(--accent)]">{it.best_san}</span>
                </div>
                <div className="text-xs text-[var(--muted)] mt-1 tabular-nums">
                  −{it.cp_loss}cp
                  {it.opening && <span className="ml-2 truncate inline-block max-w-[150px] align-bottom">· {it.opening}</span>}
                </div>
              </button>
            ))}
          </div>

          {/* Selected position + setup */}
          <div className="space-y-4">
            {selected ? (
              <>
                <Card>
                  <CardHeader>
                    <div>
                      <CardTitle>Position #{selected.game_id} · ply {selected.ply}</CardTitle>
                      {selected.opening && (
                        <div className="text-xs text-[var(--muted)] mt-0.5">
                          {selected.opening} {selected.eco && <span className="font-mono">({selected.eco})</span>}
                        </div>
                      )}
                    </div>
                  </CardHeader>
                  <Board
                    fen={selected.fen_before}
                    allowDragging={false}
                    size={360}
                    bestMove={selected.best_uci ? {
                      from: selected.best_uci.slice(0, 2),
                      to: selected.best_uci.slice(2, 4),
                    } : null}
                    hideFlipButton
                  />
                  <div className="mt-3 text-sm">
                    <div className="flex items-center gap-2">
                      <AlertCircle className="size-3.5 text-[var(--danger)]" />
                      Ton coup raté : <span className="font-mono text-[var(--danger)]">{selected.played_san}</span>
                      <span className="text-xs text-[var(--muted)]">(−{selected.cp_loss}cp)</span>
                    </div>
                    <div className="text-xs text-[var(--muted)] mt-1">
                      Stockfish suggérait : <span className="font-mono text-[var(--accent)]">{selected.best_san}</span>
                    </div>
                  </div>
                </Card>

                <Card>
                  <CardHeader><CardTitle>Configuration</CardTitle></CardHeader>
                  <div className="space-y-4">
                    <div>
                      <div className="text-xs text-[var(--muted)] mb-2">Annulations autorisées</div>
                      <div className="grid grid-cols-2 gap-1.5">
                        {(["0", "1", "3", "999"] as UndoMode[]).map((m) => (
                          <button
                            key={m}
                            onClick={() => setUndoMode(m)}
                            className={cn(
                              "text-xs px-2 py-1.5 rounded border",
                              undoMode === m
                                ? "bg-[var(--accent)] text-black border-[var(--accent)]"
                                : "bg-[var(--surface-2)] text-[var(--muted)] hover:text-[var(--foreground)]",
                            )}
                          >
                            {UNDO_LABEL[m]}
                          </button>
                        ))}
                      </div>
                      <div className="text-xs text-[var(--muted)] mt-2">
                        {undoMode === "0" && "Mode partie réelle — pas de marche arrière, tu vis avec tes choix."}
                        {undoMode === "1" && "1 seul take-back pour ta plus grosse erreur."}
                        {undoMode === "3" && "3 take-backs — challenge équilibré."}
                        {undoMode === "999" && "Mode laboratoire — annule autant que tu veux pour explorer."}
                      </div>
                    </div>

                    <div>
                      <div className="text-xs text-[var(--muted)] mb-2">Skill Stockfish (0 faible — 20 max)</div>
                      <input type="range" min={0} max={20} value={skill}
                        onChange={(e) => setSkill(Number(e.target.value))}
                        className="w-full" />
                      <div className="text-sm tabular-nums">{skill}</div>
                    </div>

                    <div>
                      <div className="text-xs text-[var(--muted)] mb-2">ELO Stockfish</div>
                      <input type="range" min={1320} max={2400} step={20} value={elo}
                        onChange={(e) => setElo(Number(e.target.value))}
                        className="w-full" />
                      <div className="text-sm tabular-nums">{elo}</div>
                    </div>

                    <button
                      onClick={() => start.mutate(selected)}
                      disabled={start.isPending}
                      className="w-full py-2.5 rounded bg-[var(--accent)] text-black font-medium text-sm disabled:opacity-50"
                    >
                      {start.isPending ? "Démarrage..." : "Affronter Stockfish à partir d'ici →"}
                    </button>
                    {start.isError && (
                      <div className="text-xs text-[var(--danger)]">
                        {start.error instanceof ApiError ? JSON.stringify(start.error.body) : String(start.error)}
                      </div>
                    )}
                  </div>
                </Card>
              </>
            ) : (
              <Card>
                <div className="text-sm text-[var(--muted)]">
                  Sélectionne une position à gauche pour voir le détail et lancer la session.
                </div>
              </Card>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
