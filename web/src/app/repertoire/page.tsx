"use client";

import { useEffect, useMemo, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Chess } from "chess.js";
import { Flag, Lightbulb, Sparkles, Crown, BookOpen } from "lucide-react";
import { api } from "@/lib/api";
import { Board } from "@/components/chess/Board";
import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import { cn } from "@/lib/utils";
import { useActivePlanItem } from "@/hooks/useActivePlanItem";
import { ActivePlanBanner } from "@/components/plan/ActivePlanBanner";
import { streamPost } from "@/lib/stream";
import type { NextCardResponse, TrainerAnswer, TrainerStats } from "@/types/trainer";

type Color = "white" | "black" | undefined;

export default function RepertoirePage() {
  const qc = useQueryClient();
  const plan = useActivePlanItem();
  const [color, setColor] = useState<Color>(undefined);
  const [feedback, setFeedback] = useState<TrainerAnswer | null>(null);
  const [lastAttempt, setLastAttempt] = useState<TrainerAnswer | null>(null);
  const [triesOnNode, setTriesOnNode] = useState(0);
  const [abandoned, setAbandoned] = useState(false);
  const [coachText, setCoachText] = useState("");
  const [coachStreaming, setCoachStreaming] = useState(false);

  const stats = useQuery<TrainerStats>({
    queryKey: ["trainer-stats", color],
    queryFn: () => api<TrainerStats>("/trainer/stats", { query: { color } }),
  });

  const next = useQuery<NextCardResponse>({
    queryKey: ["trainer-next", color],
    queryFn: () => api<NextCardResponse>("/trainer/next", { query: { color } }),
  });

  const node = next.data && next.data.has_card ? next.data.node : null;
  const [fen, setFen] = useState<string>(node?.fen ?? "");
  const [boardEpoch, setBoardEpoch] = useState(0);
  useEffect(() => {
    setFen(node?.fen ?? "");
    setFeedback(null);
    setLastAttempt(null);
    setTriesOnNode(0);
    setAbandoned(false);
    setCoachText("");
    setCoachStreaming(false);
    setBoardEpoch((e) => e + 1);
  }, [node?.id]);

  const playerColor: "white" | "black" = useMemo(() => {
    if (!node) return "white";
    if (node.color === "RepertoireColor.WHITE" || node.color === "white") return "white";
    return "black";
  }, [node?.color]);

  const answer = useMutation({
    mutationFn: (uci: string) =>
      api<TrainerAnswer>("/trainer/answer", { json: { node_id: node!.id, move: uci } }),
    onSuccess: (r) => {
      setLastAttempt(r);
      qc.invalidateQueries({ queryKey: ["trainer-stats"] });
      if (r.correct) {
        setFeedback(r);
        if (triesOnNode === 0) plan.increment();
      } else {
        // Wrong: bump tries, reset board to node start, force board remount so
        // react-chessboard discards its internal animation/position state.
        setTriesOnNode((t) => t + 1);
        if (node) setFen(node.fen);
        setBoardEpoch((e) => e + 1);
      }
    },
  });

  const handleMove = ({ from, to, promotion }: { from: string; to: string; promotion?: string }) => {
    if (!node || feedback || answer.isPending || abandoned) return false;
    try {
      const c = new Chess(fen);
      const mv = c.move({ from, to, promotion: promotion ?? "q" });
      if (!mv) return false;
      setFen(c.fen());
      answer.mutate(`${from}${to}${mv.promotion ?? ""}`);
      return true;
    } catch { return false; }
  };

  const goNext = () => { next.refetch(); };

  const replay = () => {
    if (!node) return;
    setFen(node.fen);
    setFeedback(null);
    setLastAttempt(null);
    setTriesOnNode(0);
    setAbandoned(false);
    setCoachText("");
    setCoachStreaming(false);
    setBoardEpoch((e) => e + 1);
  };

  const abandon = async () => {
    if (!node) return;
    setAbandoned(true);
    setFen(node.fen);
    setCoachStreaming(true);
    setCoachText("");
    await streamPost(`/trainer/${node.id}/explain/stream`, undefined, {
      onChunk: (c) => setCoachText((prev) => prev + c),
      onDone: () => setCoachStreaming(false),
      onError: () => setCoachStreaming(false),
    });
  };

  const askCoach = async () => {
    if (!node || coachStreaming) return;
    setCoachStreaming(true);
    setCoachText("");
    await streamPost(`/trainer/${node.id}/explain/stream`, undefined, {
      onChunk: (c) => setCoachText((prev) => prev + c),
      onDone: () => setCoachStreaming(false),
      onError: () => setCoachStreaming(false),
    });
  };

  return (
    <div className="px-4 py-6 md:px-8 md:py-8 max-w-7xl">
      <header className="mb-6 flex items-end justify-between">
        <div>
          <div className="text-xs uppercase tracking-widest text-[var(--muted)]">Entraînement</div>
          <h1 className="text-3xl font-semibold mt-1">Répertoire SR</h1>
          <p className="text-xs text-[var(--muted)] mt-1 max-w-md">
            Drill SM-2 sur les positions issues de tes propres parties. Joue le coup que tu joues habituellement.
          </p>
        </div>
        {stats.data && (
          <div className="text-xs text-[var(--muted)] flex gap-6 tabular-nums">
            <span><b className="text-[var(--foreground)]">{stats.data.due_today}</b> dus</span>
            <span><b className="text-[var(--foreground)]">{stats.data.new_nodes}</b> nouveaux</span>
            <span><b className="text-[var(--foreground)]">{stats.data.total_nodes}</b> total</span>
          </div>
        )}
      </header>

      <ActivePlanBanner item={plan.item} onClear={plan.clear} />

      <div className="mb-4 flex gap-1.5">
        {[
          { label: "Toutes couleurs", v: undefined },
          { label: "Blancs", v: "white" as const },
          { label: "Noirs", v: "black" as const },
        ].map((c) => (
          <button
            key={c.label}
            onClick={() => setColor(c.v)}
            className={cn(
              "text-xs px-3 py-1.5 rounded border",
              color === c.v ? "bg-[var(--accent)] text-black border-[var(--accent)]" : "bg-[var(--surface-2)] text-[var(--muted)] hover:text-[var(--foreground)]",
            )}
          >
            {c.label}
          </button>
        ))}
      </div>

      <div className="grid lg:grid-cols-[auto_1fr] gap-6 lg:gap-8">
        <div className="w-full max-w-[520px] mx-auto lg:mx-0">
          {!node && next.isLoading && <div className="aspect-square rounded-lg bg-[var(--surface)] animate-pulse" />}
          {!node && !next.isLoading && (
            <Card>
              <div className="text-sm">Pas de carte due pour le moment.</div>
            </Card>
          )}
          {node && (
            <Board
              key={`${node.id}-${boardEpoch}`}
              fen={fen}
              orientation={playerColor}
              draggableColor={playerColor}
              onMove={handleMove}
              size={520}
            />
          )}
        </div>

        <div className="space-y-4 min-w-0">
          {node && (
            <>
              <Card>
                <CardHeader>
                  <div>
                    <CardTitle>Contexte</CardTitle>
                    {node.opening_name && (
                      <div className="text-base font-medium mt-1 flex items-center gap-2">
                        <BookOpen className="size-4 text-[var(--accent)]" />
                        {node.opening_name}
                        {node.eco && <span className="text-xs text-[var(--muted)] font-mono">{node.eco}</span>}
                      </div>
                    )}
                  </div>
                  <span className="text-xs text-[var(--muted)] font-mono">#{node.id}</span>
                </CardHeader>

                <div className="text-xs text-[var(--muted)] mb-3">
                  Joue le coup pour <b className="text-[var(--foreground)]">{playerColor === "white" ? "les blancs" : "les noirs"}</b>.
                  Tries de réjouer le coup que tu joues habituellement dans cette position.
                </div>

                <div className="flex flex-wrap gap-4 text-xs tabular-nums text-[var(--muted)]">
                  <span>Essais : <b className="text-[var(--foreground)]">{triesOnNode}</b></span>
                  <span>Répétitions SR : <b className="text-[var(--foreground)]">{node.sr_repetitions}</b></span>
                  {node.sr_interval_days > 0 && <span>Intervalle : <b className="text-[var(--foreground)]">{node.sr_interval_days}j</b></span>}
                  <span>Ease : <b className="text-[var(--foreground)]">{node.sr_ease}</b></span>
                </div>
              </Card>

              {/* My personal stats (notes from build_repertoire) */}
              {(node.label || node.notes) && (
                <Card>
                  <CardHeader><CardTitle>Ce que tu joues d'habitude</CardTitle></CardHeader>
                  {node.label && <div className="text-sm">{node.label}</div>}
                  {node.notes && (
                    <pre className="text-xs text-[var(--muted)] mt-2 whitespace-pre-wrap font-mono leading-relaxed">
                      {node.notes}
                    </pre>
                  )}
                </Card>
              )}

              {/* GM annotation if available */}
              {node.gm_total_games && node.gm_moves && node.gm_moves.length > 0 && (
                <Card>
                  <CardHeader>
                    <div className="flex items-center gap-2">
                      <Crown className="size-4 text-[var(--warning)]" />
                      <CardTitle>Que jouent les GMs</CardTitle>
                    </div>
                    <span className="text-xs text-[var(--muted)] tabular-nums">
                      {node.gm_total_games.toLocaleString("fr-FR")} parties
                    </span>
                  </CardHeader>

                  <table className="w-full text-sm">
                    <tbody>
                      {node.gm_moves.slice(0, 5).map((m, i) => {
                        const isMine = m.san && false; // we don't get our SAN here unless via label
                        const sw = typeof m.score_white === "number" ? Math.round(m.score_white * 100) : null;
                        return (
                          <tr key={i} className={cn("border-b border-[var(--border)] last:border-0", isMine && "bg-[var(--surface-2)]")}>
                            <td className="py-1.5 font-mono">{m.san ?? m.uci ?? "?"}</td>
                            <td className="py-1.5 text-right tabular-nums text-[var(--muted)] text-xs">
                              {m.games?.toLocaleString("fr-FR") ?? "—"}
                            </td>
                            <td className="py-1.5 text-right text-xs tabular-nums">
                              {sw != null ? <MiniScore w={sw} /> : "—"}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>

                  {typeof node.gm_my_move_share === "number" && (
                    <div className="text-xs text-[var(--muted)] mt-3 pt-3 border-t border-[var(--border)]">
                      Ton coup habituel est joué par <b className="text-[var(--foreground)] tabular-nums">{Math.round(node.gm_my_move_share * 100)}%</b> des GMs
                      {typeof node.gm_my_move_score === "number" && (
                        <> · score blancs <b className="tabular-nums">{Math.round(node.gm_my_move_score * 100)}%</b></>
                      )}
                    </div>
                  )}
                </Card>
              )}

              {/* Strategic plan */}
              {node.plan && (
                <Card>
                  <CardHeader>
                    <div className="flex items-center gap-2">
                      <Lightbulb className="size-4 text-[var(--accent)]" />
                      <CardTitle>Plan</CardTitle>
                    </div>
                  </CardHeader>
                  <div className="text-sm whitespace-pre-wrap leading-relaxed">{node.plan}</div>
                </Card>
              )}

              {/* Traps */}
              {node.traps && node.traps.length > 0 && (
                <Card>
                  <CardHeader><CardTitle>Pièges connus</CardTitle></CardHeader>
                  <ul className="space-y-2 text-sm">
                    {node.traps.map((t, i) => (
                      <li key={i} className="border-l-2 border-[var(--warning)]/50 pl-2">
                        {t.name && <div className="font-medium">{t.name}</div>}
                        {t.line && <div className="font-mono text-xs text-[var(--muted)]">{t.line}</div>}
                        {t.comment && <div className="text-xs text-[var(--muted)] mt-1">{t.comment}</div>}
                      </li>
                    ))}
                  </ul>
                </Card>
              )}

              {/* Wrong attempt: tell the user *why* it's wrong without revealing the best move */}
              {!feedback && !abandoned && triesOnNode > 0 && lastAttempt && !lastAttempt.correct && (
                <Card className="border-[var(--danger)]/60">
                  <div className="text-sm">
                    <span className="text-[var(--danger)] font-medium">Pas le meilleur coup.</span>{" "}
                    {lastAttempt.plays_usual ? (
                      <>C'est ton coup habituel — mais il y a mieux ici. Réessaie en cherchant le coup objectivement le plus fort.</>
                    ) : (
                      <>Réessaie — c'est un drill, l'erreur fait partie de l'apprentissage.</>
                    )}
                  </div>
                  <div className="text-xs text-[var(--muted)] mt-1">Essais : {triesOnNode}</div>
                  <button
                    onClick={abandon}
                    className="mt-3 text-xs px-3 py-1.5 rounded border border-[var(--warning)]/40 text-[var(--warning)] hover:bg-[var(--warning)]/10 inline-flex items-center gap-1.5"
                  >
                    <Flag className="size-3" /> Abandonner & voir la réponse
                  </button>
                </Card>
              )}

              {/* Correct */}
              {feedback?.correct && (
                <Card className="border-[var(--accent)]/60">
                  <div className="text-lg font-medium text-[var(--accent)]">Bien joué</div>
                  <div className="text-xs text-[var(--muted)] mt-1 font-mono">
                    meilleur coup : <span className="text-[var(--foreground)]">{feedback.expected_san}</span>
                    {feedback.expected_source === "gm" && feedback.expected_score != null && (
                      <span className="text-[var(--accent)] ml-2">({Math.round(feedback.expected_score * 100)}% chez les GMs)</span>
                    )}
                  </div>

                  {/* Coaching nuance based on whether it's also the user's habit */}
                  <div className="mt-2 text-sm">
                    {feedback.is_best_your_usual ? (
                      <span className="text-[var(--accent)]">
                        ✓ C'est aussi ton coup habituel. Tu joues juste, garde le cap.
                      </span>
                    ) : feedback.your_usual_san ? (
                      <span className="text-[var(--info)]">
                        🎯 Upgrade : tu joues d'habitude{" "}
                        <span className="font-mono text-[var(--foreground)]">{feedback.your_usual_san}</span>,
                        mais tu viens de jouer le meilleur coup. Garde ce nouveau réflexe.
                      </span>
                    ) : (
                      <span className="text-[var(--muted)]">Tu as trouvé le meilleur coup.</span>
                    )}
                  </div>

                  <div className="text-xs text-[var(--muted)] mt-2 tabular-nums">
                    prochaine révision dans <b className="text-[var(--foreground)]">{feedback.new_interval_days}j</b>
                  </div>
                  <div className="mt-3 flex gap-2 flex-wrap">
                    <button onClick={goNext} className="text-xs px-3 py-1.5 rounded bg-[var(--accent)] text-black font-medium">
                      Suivant →
                    </button>
                    <button onClick={replay} className="text-xs px-3 py-1.5 rounded border bg-[var(--surface-2)] hover:bg-[var(--surface)]">
                      Rejouer
                    </button>
                    <button
                      onClick={askCoach}
                      disabled={coachStreaming}
                      className="text-xs px-3 py-1.5 rounded border bg-[var(--surface-2)] hover:bg-[var(--surface)] disabled:opacity-50 inline-flex items-center gap-1.5"
                    >
                      <Sparkles className="size-3 text-[var(--accent)]" />
                      Demander au coach
                    </button>
                  </div>
                </Card>
              )}

              {/* Abandoned: reveal best move + LLM commentary */}
              {abandoned && (
                <Card className="border-[var(--warning)]/60">
                  <div className="text-lg font-medium text-[var(--warning)]">Réponse révélée</div>
                  {lastAttempt?.expected_san && (
                    <div className="mt-2">
                      <div className="text-xs text-[var(--muted)] uppercase tracking-wider mb-1">Meilleur coup</div>
                      <div className="font-mono text-base text-[var(--accent)]">
                        {lastAttempt.expected_san}
                        {lastAttempt.expected_source === "gm" && lastAttempt.expected_score != null && (
                          <span className="text-xs text-[var(--muted)] ml-2">({Math.round(lastAttempt.expected_score * 100)}% GM)</span>
                        )}
                      </div>
                    </div>
                  )}
                  {lastAttempt?.your_usual_san && lastAttempt.your_usual_san !== lastAttempt.expected_san && (
                    <div className="mt-3">
                      <div className="text-xs text-[var(--muted)] uppercase tracking-wider mb-1">Ton coup habituel (à upgrade)</div>
                      <div className="font-mono text-sm text-[var(--danger)]">{lastAttempt.your_usual_san}</div>
                    </div>
                  )}
                  <div className="text-xs text-[var(--muted)] mt-3">
                    {triesOnNode} {triesOnNode > 1 ? "tentatives" : "tentative"}
                  </div>
                  <div className="mt-3 flex gap-2">
                    <button onClick={goNext} className="text-xs px-3 py-1.5 rounded bg-[var(--accent)] text-black font-medium">
                      Suivant →
                    </button>
                    <button onClick={replay} className="text-xs px-3 py-1.5 rounded border bg-[var(--surface-2)] hover:bg-[var(--surface)]">
                      Rejouer
                    </button>
                  </div>
                </Card>
              )}

              {/* Coach commentary (shown after abandon OR on demand after success) */}
              {(abandoned || coachText || coachStreaming) && (
                <Card>
                  <CardHeader>
                    <div className="flex items-center gap-2">
                      <Sparkles className="size-4 text-[var(--accent)]" />
                      <CardTitle>Commentaire du coach</CardTitle>
                    </div>
                  </CardHeader>
                  {coachStreaming && coachText.length === 0 && (
                    <div className="text-sm text-[var(--muted)] italic">le coach réfléchit…</div>
                  )}
                  {coachText && (
                    <div className="text-sm leading-relaxed whitespace-pre-wrap">
                      {coachText}
                      {coachStreaming && <span className="inline-block w-2 h-4 bg-[var(--accent)] ml-1 animate-pulse align-middle" />}
                    </div>
                  )}
                  {!coachStreaming && !coachText && abandoned && (
                    <div className="text-xs text-[var(--muted)]">Pas de commentaire disponible (Ollama non démarré ?).</div>
                  )}
                </Card>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function MiniScore({ w }: { w: number }) {
  return (
    <div className="inline-flex items-center gap-2">
      <div className="flex h-1.5 rounded overflow-hidden w-12">
        <div style={{ width: `${w}%` }} className="bg-white/80" />
        <div style={{ width: `${100 - w}%` }} className="bg-black/80" />
      </div>
      <span className="font-mono tabular-nums text-[10px] w-6 text-right">{w}</span>
    </div>
  );
}
