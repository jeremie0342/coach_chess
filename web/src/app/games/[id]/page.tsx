"use client";

import { use, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useQuery, useMutation } from "@tanstack/react-query";
import { Chess } from "chess.js";
import { Play, Pause, Square, SkipBack, Swords } from "lucide-react";
import { DownloadButton } from "@/components/ui/DownloadButton";
import { api } from "@/lib/api";
import { Board } from "@/components/chess/Board";
import { EvalBar } from "@/components/chess/EvalBar";
import { EvalGraph } from "@/components/chess/EvalGraph";
import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import { cn } from "@/lib/utils";
import { useStreamingExplain } from "@/hooks/useStreamingExplain";
import { useKeyNav } from "@/hooks/useKeyNav";
import { useActivePlanItem } from "@/hooks/useActivePlanItem";
import { ActivePlanBanner } from "@/components/plan/ActivePlanBanner";
import { motion, AnimatePresence } from "framer-motion";
import type { GameDetail, MoveRow } from "@/types/games";

type ReviewItem = {
  ply: number;
  side_to_move: string;
  played: string;
  best: string;
  quality: string;
  cp_loss: number;
  explanation: string | null;
  pv: string[] | null;
};
type ReviewResp = { game_id: number; items: ReviewItem[] };

type TacticalMotif = {
  kind: string;
  attacker?: string;
  targets?: string[];
  pinned?: string;
  behind?: string;
};
type TacticalMotifsResp = { ply: number; motifs: TacticalMotif[] };

const STARTPOS = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";

export default function GameReviewPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const gameId = Number(id);

  const q = useQuery<GameDetail>({
    queryKey: ["game", gameId],
    queryFn: () => api<GameDetail>(`/games/${gameId}`),
  });

  const [ply, setPly] = useState(0);
  const [tab, setTab] = useState<"moves" | "coach" | "review">("moves");
  const explain = useStreamingExplain();
  const plan = useActivePlanItem();
  // Variation player: replays Stockfish's principal variation on the board.
  const [pvIndex, setPvIndex] = useState<number | null>(null); // null = off, 0+ = how many PV moves applied
  const [pvAutoplay, setPvAutoplay] = useState(false);
  const pvTimer = useRef<number | null>(null);

  const review = useMutation({
    mutationFn: () => api<ReviewResp>(`/coach/games/${gameId}/review`, { method: "POST", query: { max_items: 5 } }),
  });

  const analyze = useMutation({
    mutationFn: () => api(`/games/${gameId}/analyze`, { method: "POST" }),
  });

  const oob = useMutation({
    mutationFn: () => api(`/games/${gameId}/out_of_book`, { method: "POST" }),
  });

  const motifs = useQuery<TacticalMotifsResp>({
    queryKey: ["motifs", gameId, ply],
    queryFn: () => api<TacticalMotifsResp>(`/games/${gameId}/tactical_motifs`, { query: { ply } }),
    enabled: ply > 0,
  });

  const game = q.data;
  const moves: MoveRow[] = game?.moves ?? [];
  const orientation = game?.color ?? "white";

  const currentMove = ply > 0 ? moves[ply - 1] : null;

  // When in PV mode, walk the principal variation from the BEFORE-position of
  // the current move (i.e. what should have been played instead).
  const pvActive = pvIndex !== null && currentMove?.pv && currentMove.pv.length > 0;
  const pvComputed = useMemo(() => {
    if (!pvActive || !currentMove?.pv || pvIndex === null) return null;
    try {
      const c = new Chess(currentMove.fen_before);
      const applied: { uci: string; san: string }[] = [];
      for (let i = 0; i < Math.min(pvIndex, currentMove.pv.length); i++) {
        const u = currentMove.pv[i];
        const from = u.slice(0, 2);
        const to = u.slice(2, 4);
        const promo = u.length > 4 ? u[4] : undefined;
        const mv = c.move({ from, to, promotion: promo });
        if (!mv) break;
        applied.push({ uci: u, san: mv.san });
      }
      const lastUci = applied.length > 0 ? applied[applied.length - 1].uci : null;
      return {
        fen: c.fen(),
        applied,
        lastMove: lastUci ? { from: lastUci.slice(0, 2), to: lastUci.slice(2, 4) } : null,
      };
    } catch { return null; }
  }, [pvActive, currentMove?.fen_before, currentMove?.pv, pvIndex]);

  const fen = pvActive && pvComputed ? pvComputed.fen
    : (currentMove ? currentMove.fen_after : game?.initial_fen || STARTPOS);
  const evalCp = currentMove?.eval_cp ?? null;
  const evalMate = currentMove?.eval_mate ?? null;

  const lastMove = pvActive && pvComputed?.lastMove
    ? pvComputed.lastMove
    : (currentMove ? { from: currentMove.uci.slice(0, 2), to: currentMove.uci.slice(2, 4) } : null);
  const badQuality = currentMove?.quality && /blunder|mistake/.test(currentMove.quality);
  const bestMove = !pvActive && badQuality && currentMove?.best_uci
    ? { from: currentMove.best_uci.slice(0, 2), to: currentMove.best_uci.slice(2, 4) }
    : null;

  // Reset PV mode whenever ply changes
  useEffect(() => {
    setPvIndex(null);
    setPvAutoplay(false);
    if (pvTimer.current) { window.clearTimeout(pvTimer.current); pvTimer.current = null; }
  }, [ply]);

  // Autoplay PV: step through the variation every 900ms
  useEffect(() => {
    if (!pvAutoplay || !currentMove?.pv) return;
    const max = Math.min(currentMove.pv.length, 8);
    if (pvIndex === null || pvIndex >= max) {
      setPvAutoplay(false);
      return;
    }
    pvTimer.current = window.setTimeout(() => setPvIndex((i) => (i ?? 0) + 1), 900);
    return () => {
      if (pvTimer.current) { window.clearTimeout(pvTimer.current); pvTimer.current = null; }
    };
  }, [pvAutoplay, pvIndex, currentMove?.pv]);

  const motifSquares = useMemo(() => {
    const set = new Set<string>();
    for (const m of motifs.data?.motifs ?? []) {
      if (m.attacker) set.add(m.attacker);
      if (m.pinned) set.add(m.pinned);
      if (m.behind) set.add(m.behind);
      for (const t of m.targets ?? []) set.add(t);
    }
    return Array.from(set);
  }, [motifs.data?.motifs]);

  useKeyNav({
    onPrev: () => setPly((p) => Math.max(0, p - 1)),
    onNext: () => setPly((p) => Math.min(moves.length, p + 1)),
    onFirst: () => setPly(0),
    onLast: () => setPly(moves.length),
    enabled: moves.length > 0,
  });

  const points = useMemo(
    () => moves.map((m) => ({ ply: m.ply, cp: m.eval_cp, mate: m.eval_mate, quality: m.quality })),
    [moves],
  );


  if (q.isLoading) return <div className="px-4 py-6 md:px-8 md:py-8 text-[var(--muted)]">Chargement…</div>;
  if (!game) return <div className="px-4 py-6 md:px-8 md:py-8 text-[var(--danger)]">Partie introuvable</div>;

  return (
    <div className="px-4 py-6 md:px-8 md:py-8 max-w-[1400px]">
      <header className="mb-6 flex items-end justify-between">
        <div>
          <div className="text-xs uppercase tracking-widest text-[var(--muted)]">
            <Link href="/games" className="hover:text-[var(--foreground)]">Parties</Link> · #{gameId}
          </div>
          <h1 className="text-2xl font-semibold mt-1">
            {game.opening ?? "—"} <span className="text-[var(--muted)] font-mono text-base ml-2">{game.eco}</span>
          </h1>
          <div className="text-sm text-[var(--muted)] mt-1">
            {game.color === "white" ? "Blancs" : "Noirs"} ({game.my_rating ?? "—"}) vs {game.opp_username ?? "—"} ({game.opp_rating ?? "—"}) · <span className={cn(
              game.result === "win" ? "text-[var(--accent)]" : game.result === "loss" ? "text-[var(--danger)]" : ""
            )}>{game.result}</span>
          </div>
        </div>
        <div className="flex gap-2 flex-wrap">
          {game.url && <a href={game.url} target="_blank" className="text-xs px-3 py-1.5 rounded border bg-[var(--surface-2)] hover:bg-[var(--surface)]">chess.com ↗</a>}
          <a href={`/api/proxy/games/${gameId}/annotated.pgn`} className="text-xs px-3 py-1.5 rounded border bg-[var(--surface-2)] hover:bg-[var(--surface)]">PGN annoté</a>
          <DownloadButton
            href={`/api/proxy/cards/position.png?fen=${encodeURIComponent(fen)}&title=${encodeURIComponent(`#${gameId} ply ${ply}`)}&download=1`}
            title="Télécharger la PNG de la position"
            label="PNG"
            className="text-xs px-3 py-1.5 rounded border bg-[var(--surface-2)] hover:bg-[var(--surface)]"
          />
          <DownloadButton
            href={`/api/proxy/cards/game.gif?game_id=${gameId}&download=1`}
            title="Télécharger le GIF de la partie"
            label="GIF"
            className="text-xs px-3 py-1.5 rounded border bg-[var(--surface-2)] hover:bg-[var(--surface)]"
          />
          <DownloadButton
            href={`/api/proxy/cards/game.mp4?game_id=${gameId}&download=1`}
            title="Télécharger la vidéo MP4 (pausable, plus légère)"
            label="MP4"
            className="text-xs px-3 py-1.5 rounded border bg-[var(--surface-2)] hover:bg-[var(--surface)]"
          />
          {game.analysis_status !== "done" && (
            <button
              onClick={() => analyze.mutate()}
              disabled={analyze.isPending}
              className="text-xs px-3 py-1.5 rounded border bg-[var(--surface-2)] hover:bg-[var(--surface)] disabled:opacity-50"
            >
              {analyze.isPending ? "Analyse…" : "Analyser Stockfish"}
            </button>
          )}
          <button
            onClick={() => oob.mutate()}
            disabled={oob.isPending}
            className="text-xs px-3 py-1.5 rounded border bg-[var(--surface-2)] hover:bg-[var(--surface)] disabled:opacity-50"
          >
            {oob.isPending ? "…" : "Recalc OOB"}
          </button>
        </div>
      </header>

      <ActivePlanBanner item={plan.item} onClear={plan.clear} />

      <div className="grid lg:grid-cols-[auto_1fr] gap-6 lg:gap-8">
        <div className="w-full max-w-[520px] mx-auto lg:mx-0">
          <div className="flex gap-3 items-stretch">
            <EvalBar cp={evalCp} mate={evalMate} orientation={orientation} className="self-stretch" />
            <div className="flex-1 min-w-0">
              <Board
                fen={fen}
                orientation={orientation}
                allowDragging={false}
                size={520}
                lastMove={lastMove}
                bestMove={bestMove}
                highlightSquares={motifSquares}
              />
            </div>
          </div>
          <div className="mt-3 flex items-center gap-2 text-xs">
            <button onClick={() => setPly(0)} className="px-2 py-1 rounded bg-[var(--surface-2)]">⏮</button>
            <button onClick={() => setPly((p) => Math.max(0, p - 1))} className="px-2 py-1 rounded bg-[var(--surface-2)]">◀</button>
            <button onClick={() => setPly((p) => Math.min(moves.length, p + 1))} className="px-2 py-1 rounded bg-[var(--surface-2)]">▶</button>
            <button onClick={() => setPly(moves.length)} className="px-2 py-1 rounded bg-[var(--surface-2)]">⏭</button>
            <span className="ml-3 text-[var(--muted)] tabular-nums font-mono">
              ply {ply} / {moves.length}
            </span>
            <AnimatePresence mode="wait">
              {currentMove?.quality && (
                <motion.span
                  key={`${ply}-${currentMove.quality}`}
                  initial={{ opacity: 0, scale: 0.85, y: -2 }}
                  animate={{ opacity: 1, scale: 1, y: 0 }}
                  exit={{ opacity: 0, scale: 0.9 }}
                  transition={{ duration: 0.18 }}
                  className={cn("ml-2 text-[10px] px-1.5 py-0.5 rounded uppercase font-mono", qualityClass(currentMove.quality))}
                >
                  {currentMove.quality}
                </motion.span>
              )}
            </AnimatePresence>
            <span className="ml-auto text-[10px] text-[var(--muted)] font-mono hidden md:inline">
              ← → · Home · End
            </span>
          </div>
          {ply > 0 && currentMove && (
            <div className="mt-3">
              <Link
                href={`/play?fen=${encodeURIComponent(currentMove.fen_before)}&game_id=${gameId}&ply=${ply}&title=${encodeURIComponent(`Game #${gameId} ply ${ply}`)}`}
                className="text-xs px-3 py-1.5 rounded bg-[var(--info)] text-white font-medium inline-flex items-center gap-1.5"
              >
                <Swords className="size-3" /> Affronter Stockfish à partir d'ici
              </Link>
            </div>
          )}
        </div>

        <div className="min-w-0 space-y-4">
          <Card>
            <CardHeader><CardTitle>Courbe d'évaluation</CardTitle></CardHeader>
            <EvalGraph points={points} selectedPly={ply > 0 ? ply : undefined} onSelect={setPly} />
          </Card>

          <Card className="p-0 overflow-hidden">
            <div className="flex border-b border-[var(--border)] text-xs uppercase tracking-wider">
              {(["moves", "coach", "review"] as const).map((t) => (
                <button
                  key={t}
                  onClick={() => setTab(t)}
                  className={cn("px-4 py-3", tab === t ? "text-[var(--foreground)] border-b-2 border-[var(--accent)]" : "text-[var(--muted)]")}
                >
                  {t === "moves" ? "Coups" : t === "coach" ? "Coach" : "Revue"}
                </button>
              ))}
            </div>

            {tab === "moves" && (
              <div className="max-h-[480px] overflow-y-auto">
                <table className="w-full text-sm font-mono">
                  <tbody>
                    {pairMoves(moves).map(([w, b]) => (
                      <tr key={(w?.ply ?? b?.ply)!} className="border-b border-[var(--border)] last:border-0">
                        <td className="px-3 py-1.5 text-[var(--muted)] tabular-nums w-12">{Math.ceil((w?.ply ?? b!.ply) / 2)}.</td>
                        <MoveCell m={w} selected={w?.ply === ply} onClick={() => w && setPly(w.ply)} />
                        <MoveCell m={b} selected={b?.ply === ply} onClick={() => b && setPly(b.ply)} />
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {tab === "coach" && (
              <div className="p-5 space-y-4">
                {currentMove ? (
                  <>
                    {/* Coup joué vs meilleur coup */}
                    <div className="grid grid-cols-2 gap-3">
                      <div className="rounded border border-[var(--danger)]/40 bg-[var(--danger)]/5 p-3">
                        <div className="text-[10px] uppercase tracking-wider text-[var(--muted)] mb-1">Ton coup</div>
                        <div className="font-mono text-base">{currentMove.san}</div>
                        {currentMove.quality && (
                          <div className={cn("text-xs mt-1 uppercase", qualityTextClass(currentMove.quality))}>
                            {currentMove.quality}
                            {currentMove.cp_loss != null && currentMove.cp_loss > 30 && (
                              <span className="text-[var(--muted)] ml-2 font-mono">−{currentMove.cp_loss}cp</span>
                            )}
                          </div>
                        )}
                      </div>
                      <div className="rounded border border-[var(--accent)]/40 bg-[var(--accent)]/5 p-3">
                        <div className="text-[10px] uppercase tracking-wider text-[var(--muted)] mb-1">Meilleur coup</div>
                        <div className="font-mono text-base text-[var(--accent)]">{currentMove.best_san ?? "—"}</div>
                        {currentMove.pv && currentMove.pv.length > 1 && (
                          <div className="text-xs text-[var(--muted)] mt-1">
                            puis : <span className="font-mono">{previewPv(currentMove)}</span>
                          </div>
                        )}
                      </div>
                    </div>

                    {/* Lecteur de variation principale */}
                    {currentMove.pv && currentMove.pv.length > 0 && (
                      <div className="rounded border border-[var(--info)]/40 bg-[var(--info)]/5 p-3">
                        <div className="flex items-center justify-between mb-2">
                          <div className="text-xs uppercase tracking-wider text-[var(--info)]">
                            🎬 Variation que tu aurais dû jouer
                          </div>
                          {pvActive && pvComputed && (
                            <div className="text-xs text-[var(--muted)] tabular-nums">
                              {pvComputed.applied.length} / {Math.min(currentMove.pv.length, 8)}
                            </div>
                          )}
                        </div>
                        <div className="flex flex-wrap gap-1.5 mb-3">
                          {currentMove.pv.slice(0, 8).map((u, i) => {
                            try {
                              const c = new Chess(currentMove.fen_before);
                              for (let j = 0; j <= i; j++) {
                                const uj = currentMove.pv![j];
                                c.move({ from: uj.slice(0, 2), to: uj.slice(2, 4), promotion: uj.length > 4 ? uj[4] : undefined });
                              }
                              const c0 = new Chess(currentMove.fen_before);
                              for (let j = 0; j < i; j++) {
                                const uj = currentMove.pv![j];
                                c0.move({ from: uj.slice(0, 2), to: uj.slice(2, 4), promotion: uj.length > 4 ? uj[4] : undefined });
                              }
                              const mv = c0.move({ from: u.slice(0, 2), to: u.slice(2, 4), promotion: u.length > 4 ? u[4] : undefined });
                              const san = mv?.san ?? u;
                              return (
                                <button
                                  key={i}
                                  onClick={() => { setPvAutoplay(false); setPvIndex(i + 1); }}
                                  className={cn(
                                    "text-xs font-mono px-2 py-1 rounded",
                                    pvIndex != null && pvIndex >= i + 1
                                      ? "bg-[var(--accent)] text-black"
                                      : "bg-[var(--surface-2)] text-[var(--foreground)] hover:bg-[var(--surface)]",
                                  )}
                                >
                                  {Math.floor(i / 2) + Math.ceil((currentMove.ply) / 2)}{i % 2 === 0 ? "." : "..."} {san}
                                </button>
                              );
                            } catch { return null; }
                          })}
                        </div>
                        <div className="flex gap-1.5">
                          <button
                            onClick={() => { setPvIndex(0); setPvAutoplay(false); }}
                            className="text-xs px-2 py-1 rounded border bg-[var(--surface-2)] hover:bg-[var(--surface)] inline-flex items-center gap-1"
                          >
                            <SkipBack className="size-3" /> Début
                          </button>
                          <button
                            onClick={() => {
                              if (pvAutoplay) {
                                setPvAutoplay(false);
                              } else {
                                setPvIndex((pvIndex ?? 0));
                                setPvAutoplay(true);
                              }
                            }}
                            className="text-xs px-3 py-1 rounded bg-[var(--info)] text-white font-medium inline-flex items-center gap-1"
                          >
                            {pvAutoplay ? <><Pause className="size-3" /> Pause</> : <><Play className="size-3" /> Rejouer</>}
                          </button>
                          <button
                            onClick={() => { setPvIndex(null); setPvAutoplay(false); }}
                            className="text-xs px-2 py-1 rounded border bg-[var(--surface-2)] hover:bg-[var(--surface)] inline-flex items-center gap-1"
                          >
                            <Square className="size-3" /> Stop
                          </button>
                        </div>
                        {pvActive && (
                          <div className="text-[10px] text-[var(--muted)] mt-2 italic">
                            L'échiquier ci-contre montre maintenant la position SI tu avais joué cette variation.
                          </div>
                        )}
                      </div>
                    )}

                    {/* Explication LLM */}
                    <div>
                      <div className="flex gap-2">
                        <button
                          onClick={() => explain.start(gameId, ply)}
                          disabled={ply === 0 || explain.isStreaming}
                          className="text-sm px-4 py-2 rounded bg-[var(--accent)] text-black font-medium disabled:opacity-50"
                        >
                          {explain.isStreaming ? "…" : `Demander au coach`}
                        </button>
                        {explain.isStreaming && (
                          <button
                            onClick={explain.stop}
                            className="text-sm px-3 py-2 rounded border border-[var(--danger)]/40 text-[var(--danger)]"
                          >
                            Stop
                          </button>
                        )}
                      </div>
                      {explain.error && (
                        <div className="mt-3 text-sm text-[var(--danger)]">{explain.error}</div>
                      )}
                      {explain.text && (
                        <div className="mt-4 text-sm whitespace-pre-wrap leading-relaxed">
                          {explain.text}
                          {explain.isStreaming && (
                            <span className="inline-block w-2 h-4 bg-[var(--accent)] ml-1 animate-pulse align-middle" />
                          )}
                        </div>
                      )}
                    </div>
                  </>
                ) : (
                  <div className="text-sm text-[var(--muted)]">
                    Sélectionne un coup dans la liste à gauche pour voir l'analyse + la variation Stockfish + l'explication du coach.
                  </div>
                )}
              </div>
            )}

            {tab === "review" && (
              <div className="p-5">
                <div className="flex items-center gap-3 flex-wrap">
                  <button
                    onClick={() => review.mutate()}
                    disabled={review.isPending}
                    className="text-sm px-4 py-2 rounded bg-[var(--accent)] text-black font-medium disabled:opacity-50"
                  >
                    {review.isPending ? "Analyse..." : "Revue rapide (top 5 erreurs)"}
                  </button>
                  <span className="text-xs text-[var(--muted)]">
                    Instantané — clique un ply pour voir la position + la variation Stockfish.
                  </span>
                </div>
                {review.data && review.data.items.length === 0 && (
                  <div className="mt-4 text-sm text-[var(--muted)]">
                    Aucune erreur majeure détectée — partie propre.
                  </div>
                )}
                {review.data && (
                  <ul className="mt-4 space-y-3">
                    {review.data.items.map((it) => (
                      <li key={it.ply} className="border-l-2 border-[var(--danger)]/50 pl-3 py-1">
                        <div className="flex items-baseline gap-2 text-sm flex-wrap">
                          <button onClick={() => { setPly(it.ply); setTab("coach"); }} className="text-[var(--info)] hover:underline tabular-nums font-mono">
                            ply {it.ply}
                          </button>
                          <span className="font-mono">{it.played}</span>
                          <span className="text-[var(--muted)]">→</span>
                          <span className="font-mono text-[var(--accent)]">{it.best}</span>
                          <span className={cn("text-xs uppercase", qualityTextClass(it.quality))}>{it.quality}</span>
                          <span className="text-xs text-[var(--muted)] ml-auto font-mono">−{it.cp_loss}cp</span>
                        </div>
                        {it.pv && it.pv.length > 0 && (
                          <div className="text-xs text-[var(--muted)] mt-1 font-mono">
                            La suite : {previewPvFromUci(it.pv)}
                          </div>
                        )}
                        {it.explanation && (
                          <div className="text-sm mt-1 text-[var(--muted)] italic">{it.explanation}</div>
                        )}
                        <button
                          onClick={() => { setPly(it.ply); setTab("coach"); }}
                          className="mt-2 text-xs text-[var(--info)] hover:underline"
                        >
                          Voir la variation sur l'échiquier →
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}

function MoveCell({ m, selected, onClick }: { m: MoveRow | null | undefined; selected?: boolean; onClick?: () => void }) {
  if (!m) return <td />;
  return (
    <td className={cn("px-3 py-1.5 cursor-pointer", selected ? "bg-[var(--surface-2)]" : "hover:bg-[var(--surface-2)]/50")} onClick={onClick}>
      <span>{m.san}</span>
      {m.quality && (
        <span className={cn("ml-2 text-[10px] uppercase", qualityTextClass(m.quality))}>
          {m.quality}
        </span>
      )}
    </td>
  );
}

function previewPvFromUci(pv: string[]): string {
  // We don't have the FEN here, just compute UCI -> rough notation
  return pv.slice(0, 6).join(" ");
}

function previewPv(m: MoveRow): string {
  if (!m.pv || m.pv.length === 0) return "";
  try {
    const c = new Chess(m.fen_before);
    const sans: string[] = [];
    for (let i = 0; i < Math.min(m.pv.length, 5); i++) {
      const u = m.pv[i];
      const mv = c.move({ from: u.slice(0, 2), to: u.slice(2, 4), promotion: u.length > 4 ? u[4] : undefined });
      if (!mv) break;
      sans.push(mv.san);
    }
    return sans.slice(1).join(" ");  // skip the best_san (already shown) and show the rest
  } catch { return ""; }
}

function pairMoves(moves: MoveRow[]): [MoveRow | null, MoveRow | null][] {
  const rows: [MoveRow | null, MoveRow | null][] = [];
  for (let i = 0; i < moves.length; i += 2) {
    rows.push([moves[i] ?? null, moves[i + 1] ?? null]);
  }
  return rows;
}

function qualityClass(q: string) {
  if (q.includes("blunder")) return "bg-[var(--danger)]/20 text-[var(--danger)]";
  if (q.includes("mistake")) return "bg-[var(--warning)]/20 text-[var(--warning)]";
  if (q.includes("inaccuracy")) return "bg-[var(--info)]/20 text-[var(--info)]";
  if (q.includes("best") || q.includes("excellent")) return "bg-[var(--accent)]/20 text-[var(--accent)]";
  return "bg-[var(--surface-2)] text-[var(--muted)]";
}

function qualityTextClass(q: string) {
  if (q.includes("blunder")) return "text-[var(--danger)]";
  if (q.includes("mistake")) return "text-[var(--warning)]";
  if (q.includes("inaccuracy")) return "text-[var(--info)]";
  if (q.includes("best") || q.includes("excellent")) return "text-[var(--accent)]";
  return "text-[var(--muted)]";
}
