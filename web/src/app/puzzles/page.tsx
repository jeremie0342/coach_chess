"use client";

import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Chess } from "chess.js";
import { api } from "@/lib/api";
import { Board } from "@/components/chess/Board";
import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import { JobButton } from "@/components/admin/JobButton";
import { useActivePlanItem } from "@/hooks/useActivePlanItem";
import { ActivePlanBanner } from "@/components/plan/ActivePlanBanner";
import { pickPrimaryTheme, themeMeta } from "@/lib/puzzle-themes";
import { streamPost } from "@/lib/stream";
import { Sparkles, Flag, Lightbulb, Loader2 } from "lucide-react";
import { DownloadButton } from "@/components/ui/DownloadButton";
import { motion, AnimatePresence } from "framer-motion";
import { cn } from "@/lib/utils";
import type { NextExerciseResponse, AnswerResponse, ExerciseStats } from "@/types/exercises";

type Filters = {
  theme?: string;
  themes?: string;            // CSV
  exclude_themes?: string;    // CSV
  rating?: number;
  rating_window?: number;
  source_kind?: string;
};

const THEMES = [
  "fork", "pin", "skewer", "discoveredAttack", "doubleCheck",
  "mateIn1", "mateIn2", "mateIn3", "backRankMate",
  "hangingPiece", "trappedPiece", "endgame", "middlegame", "opening",
];

// Lichess outcome tags. When the user picks a motif (fork, pin, ...) we exclude
// these so we don't drown them in mate-in-N puzzles.
const MATE_TAGS = ["mate", "mateIn1", "mateIn2", "mateIn3", "mateIn4", "mateIn5"];

// Themes that ARE about mating: don't exclude mate tags when one of these
// is the user's selection.
const MATE_THEMES = new Set(["mateIn1", "mateIn2", "mateIn3", "backRankMate", "mate"]);

function buildFilters(base: Filters, themeChip: string | undefined): Filters {
  const out = { ...base };
  if (themeChip) {
    out.theme = themeChip;
    if (!MATE_THEMES.has(themeChip)) {
      out.exclude_themes = MATE_TAGS.join(",");
    } else {
      delete out.exclude_themes;
    }
  } else {
    delete out.theme;
    delete out.exclude_themes;
  }
  return out;
}

type RecommendedRating = {
  rating: number;
  base_rating: number;
  adjustment: number;
  success_rate: number | null;
  sample_size: number;
  rating_window: number;
  reason: string;
};

export default function PuzzlesPage() {
  const qc = useQueryClient();
  const sp = useSearchParams();
  const plan = useActivePlanItem();

  // Adaptive recommended rating fetched from the backend. Used to seed the
  // rating filter on first load (unless URL has explicit ?rating=).
  const recommended = useQuery<RecommendedRating>({
    queryKey: ["recommended-puzzle-rating"],
    queryFn: () => api<RecommendedRating>("/exercises/recommended_rating"),
    staleTime: 5 * 60_000,
  });

  // Initial filters seeded from URL query, or from adaptive recommendation,
  // or sane defaults.
  const urlRating = sp?.get("rating");
  const urlTheme = sp?.get("theme") ?? undefined;
  const urlThemesCsv = sp?.get("themes") ?? undefined; // from /today plan (multi-theme)
  const [filters, setFilters] = useState<Filters>(() => {
    const f: Filters = {
      rating: urlRating ? Number(urlRating) : undefined,
      rating_window: sp?.get("rating_window") ? Number(sp.get("rating_window")) : 200,
      theme: urlTheme,
      themes: urlThemesCsv,
      source_kind: sp?.get("source_kind") ?? undefined,
    };
    // When the user lands with a tactical motif but no explicit exclude, auto-ban
    // mate tags so the picker doesn't fall back to mate-in-N puzzles.
    const sole = urlTheme;
    if (sole && !MATE_THEMES.has(sole)) {
      f.exclude_themes = MATE_TAGS.join(",");
    } else if (urlThemesCsv) {
      const list = urlThemesCsv.split(",");
      const onlyMate = list.every((t) => MATE_THEMES.has(t));
      if (!onlyMate) f.exclude_themes = MATE_TAGS.join(",");
    }
    return f;
  });

  // Once the recommended rating arrives, seed the filter (only if not set
  // already by URL or by the user manually).
  useEffect(() => {
    if (recommended.data && filters.rating == null && !urlRating) {
      setFilters((f) => ({
        ...f,
        rating: recommended.data!.rating,
        rating_window: recommended.data!.rating_window,
      }));
    }
  }, [recommended.data, urlRating]);  // eslint-disable-line react-hooks/exhaustive-deps
  const [feedback, setFeedback] = useState<AnswerResponse | null>(null);
  const [tries, setTries] = useState(0);

  const stats = useQuery<ExerciseStats>({
    queryKey: ["exercise-stats"],
    queryFn: () => api<ExerciseStats>("/exercises/stats"),
  });

  const next = useQuery<NextExerciseResponse>({
    queryKey: ["exercise-next", filters],
    queryFn: () => api<NextExerciseResponse>("/exercises/next", { query: filters }),
  });

  const ex = next.data && next.data.has_exercise ? next.data.exercise : null;

  // The board state evolves as the user plays through the puzzle. `fen` is the
  // CURRENT position the user is facing; `step` is the index of the user move
  // expected next (0-indexed). On retry, we reset both to the puzzle's start.
  const [fen, setFen] = useState<string>(ex?.fen ?? "");
  const [step, setStep] = useState(0);
  const [lastFeedback, setLastFeedback] = useState<AnswerResponse | null>(null);
  const [abandoned, setAbandoned] = useState(false);
  const [coachText, setCoachText] = useState("");
  const [coachStreaming, setCoachStreaming] = useState(false);
  const [boardEpoch, setBoardEpoch] = useState(0);
  const [isTransitioning, setIsTransitioning] = useState(false);
  useEffect(() => {
    setFen(ex?.fen ?? "");
    setStep(0);
    setFeedback(null);
    setLastFeedback(null);
    setTries(0);
    setAbandoned(false);
    setCoachText("");
    setCoachStreaming(false);
    setBoardEpoch((e) => e + 1);
  }, [ex?.id]);

  const answer = useMutation({
    mutationFn: (uci: string) =>
      api<AnswerResponse>("/exercises/answer", {
        json: { exercise_id: ex!.id, move: uci, step },
      }),
    onSuccess: (r) => {
      setLastFeedback(r);
      if (!r.correct) {
        setTries((t) => t + 1);
        if (ex) {
          setFen(ex.fen);
          setStep(0);
          setBoardEpoch((e) => e + 1);
        }
        qc.invalidateQueries({ queryKey: ["exercise-stats"] });
        return;
      }
      if (r.complete) {
        // Final user move: puzzle solved. Always credit the daily plan
        // (regardless of tries) — the user worked through the puzzle.
        setFeedback(r);
        qc.invalidateQueries({ queryKey: ["exercise-stats"] });
        plan.increment();
        return;
      }
      // Intermediate correct move: animate opp reply and continue.
      if (r.fen_after_opponent) {
        // Brief delay so the user move animation is visible before opp's reply.
        setTimeout(() => {
          setFen(r.fen_after_opponent!);
          setStep((s) => s + 1);
        }, 250);
      } else {
        setStep((s) => s + 1);
      }
    },
  });

  const handleMove = ({ from, to, promotion }: { from: string; to: string; promotion?: string }) => {
    // Block while waiting OR while terminal feedback (success/fail) is shown OR if abandoned.
    if (!ex || feedback || answer.isPending || abandoned) return false;
    try {
      const c = new Chess(fen);
      const mv = c.move({ from, to, promotion: promotion ?? "q" });
      if (!mv) return false;
      // Optimistically reflect user's move on the board.
      setFen(c.fen());
      const uci = `${from}${to}${mv.promotion ?? ""}`;
      answer.mutate(uci);
      return true;
    } catch {
      return false;
    }
  };

  const goNext = async () => {
    setIsTransitioning(true);
    // Clear the visible feedback immediately so the previous result doesn't
    // linger while we wait for the next puzzle.
    setFeedback(null);
    setLastFeedback(null);
    qc.invalidateQueries({ queryKey: ["exercise-next"] });
    try {
      await next.refetch();
    } finally {
      // Small minimum so the transition animation feels intentional even
      // when the backend is fast.
      window.setTimeout(() => setIsTransitioning(false), 220);
    }
  };

  const retry = () => {
    if (!ex) return;
    setFen(ex.fen);
    setStep(0);
    setFeedback(null);
    setBoardEpoch((e) => e + 1);
  };

  const replay = () => {
    if (!ex) return;
    setFen(ex.fen);
    setStep(0);
    setFeedback(null);
    setLastFeedback(null);
    setTries(0);
    setAbandoned(false);
    setCoachText("");
    setCoachStreaming(false);
    setBoardEpoch((e) => e + 1);
  };

  const abandon = async () => {
    if (!ex) return;
    setAbandoned(true);
    setFen(ex.fen);
    setStep(0);
    // Try fetching LLM commentary in the background — fine if Ollama is off.
    setCoachText("");
    setCoachStreaming(true);
    await streamPost(`/exercises/${ex.id}/explain/stream`, undefined, {
      onChunk: (c) => setCoachText((prev) => prev + c),
      onDone: () => setCoachStreaming(false),
      onError: () => setCoachStreaming(false),
    });
  };

  const playerColor: "white" | "black" = ex?.user_color ?? (ex?.side_to_move === "b" ? "black" : "white");

  return (
    <div className="px-4 py-6 md:px-8 md:py-8 max-w-7xl">
      <header className="mb-6 flex items-end justify-between">
        <div>
          <div className="text-xs uppercase tracking-widest text-[var(--muted)]">Entraînement</div>
          <h1 className="text-3xl font-semibold mt-1">Puzzles</h1>
        </div>
        {stats.data && (
          <div className="text-xs text-[var(--muted)] flex gap-6 tabular-nums">
            <span><b className="text-[var(--foreground)]">{stats.data.due_today}</b> dus</span>
            <span><b className="text-[var(--foreground)]">{stats.data.new}</b> nouveaux</span>
            <span><b className="text-[var(--foreground)]">{stats.data.total}</b> total</span>
          </div>
        )}
      </header>

      <ActivePlanBanner item={plan.item} onClear={plan.clear} />

      {recommended.data && (
        <Card className="mb-4 border-l-4 border-l-[var(--info)]">
          <div className="flex items-center gap-3">
            <div className="text-xs uppercase tracking-widest text-[var(--muted)] shrink-0">
              Difficulté adaptative
            </div>
            <div className="text-sm flex-1">
              <span className="font-mono text-[var(--foreground)]">{recommended.data.rating}</span>
              <span className="text-[var(--muted)]"> ±{recommended.data.rating_window}</span>
              {recommended.data.adjustment !== 0 && (
                <span className={cn("ml-2 font-mono text-xs",
                  recommended.data.adjustment > 0 ? "text-[var(--accent)]" : "text-[var(--warning)]")}>
                  {recommended.data.adjustment > 0 ? "+" : ""}{recommended.data.adjustment} vs base {recommended.data.base_rating}
                </span>
              )}
              <span className="text-[var(--muted)] ml-2 text-xs">{recommended.data.reason}</span>
            </div>
            <button
              onClick={() => {
                qc.invalidateQueries({ queryKey: ["recommended-puzzle-rating"] });
                if (recommended.data) {
                  setFilters((f) => ({
                    ...f,
                    rating: recommended.data!.rating,
                    rating_window: recommended.data!.rating_window,
                  }));
                }
              }}
              className="text-xs px-2 py-1 rounded border bg-[var(--surface-2)] hover:bg-[var(--surface)]"
            >
              Recalculer
            </button>
          </div>
        </Card>
      )}

      <div className="mb-4">
        <details className="text-xs">
          <summary className="text-[var(--muted)] cursor-pointer hover:text-[var(--foreground)]">Actions</summary>
          <div className="mt-2 max-w-md">
            <Card>
              <JobButton
                label="Générer puzzles depuis mes blunders"
                description="Min 120 cp loss. Tourne en arrière-plan."
                path="/async/exercises/generate"
                body={{ min_cp_loss: 120 }}
              />
            </Card>
          </div>
        </details>
      </div>

      <div className="grid lg:grid-cols-[auto_1fr] gap-8">
        {/* Board */}
        <div>
          {!ex && next.isLoading && <div className="w-[480px] h-[480px] rounded-lg bg-[var(--surface)] animate-pulse" />}
          {!ex && !next.isLoading && (
            <Card className="w-[480px]">
              <div className="text-sm">Aucun puzzle pour ces filtres.</div>
              <button onClick={() => setFilters({})} className="mt-3 text-xs text-[var(--info)] hover:underline">
                Réinitialiser les filtres
              </button>
            </Card>
          )}
          {ex && (
            <div className="relative">
              <AnimatePresence mode="wait">
                <motion.div
                  key={`${ex.id}-${boardEpoch}`}
                  initial={{ opacity: 0, scale: 0.97 }}
                  animate={{ opacity: isTransitioning ? 0.35 : 1, scale: 1 }}
                  exit={{ opacity: 0, scale: 0.97 }}
                  transition={{ duration: 0.18, ease: [0.22, 1, 0.36, 1] }}
                >
                  <Board
                    key={`${ex.id}-${boardEpoch}`}
                    fen={fen}
                    orientation={playerColor}
                    draggableColor={playerColor}
                    onMove={handleMove}
                    size={520}
                  />
                </motion.div>
              </AnimatePresence>

              {/* Loading overlay during refetch */}
              <AnimatePresence>
                {isTransitioning && (
                  <motion.div
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    transition={{ duration: 0.15 }}
                    className="absolute inset-0 flex items-center justify-center pointer-events-none rounded-lg bg-[var(--background)]/30 backdrop-blur-sm"
                  >
                    <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-[var(--surface)] border border-[var(--border)] shadow text-xs">
                      <Loader2 className="size-3.5 animate-spin text-[var(--accent)]" />
                      <span>Puzzle suivant…</span>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          )}
          {ex && (
            <div className="mt-3 flex items-center justify-between gap-3 text-xs">
              <div className="text-[var(--muted)] font-mono break-all">
                {ex.side_to_move === "w" ? "Trait aux blancs" : "Trait aux noirs"} · #{ex.id}
              </div>
              <DownloadButton
                href={`/api/proxy/cards/exercise.gif?exercise_id=${ex.id}&download=1`}
                title="Télécharger le GIF animé de la solution"
                label="GIF"
                className="px-2 py-1 rounded border bg-[var(--surface-2)] hover:bg-[var(--surface)] text-[var(--muted)] hover:text-[var(--foreground)]"
              />
              <DownloadButton
                href={`/api/proxy/cards/exercise.mp4?exercise_id=${ex.id}&download=1`}
                title="Télécharger la vidéo MP4"
                label="MP4"
                className="px-2 py-1 rounded border bg-[var(--surface-2)] hover:bg-[var(--surface)] text-[var(--muted)] hover:text-[var(--foreground)]"
              />
            </div>
          )}
        </div>

        {/* Side */}
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Filtres</CardTitle>
            </CardHeader>
            <div className="space-y-3 text-sm">
              <label className="flex items-center gap-3">
                <span className="w-24 text-[var(--muted)]">Rating</span>
                <input
                  type="number"
                  value={filters.rating ?? ""}
                  onChange={(e) => setFilters((f) => ({ ...f, rating: Number(e.target.value) || undefined }))}
                  className="bg-[var(--surface-2)] border rounded px-2 py-1 w-24 tabular-nums"
                />
                <span className="text-[var(--muted)]">±</span>
                <input
                  type="number"
                  value={filters.rating_window ?? 200}
                  onChange={(e) => setFilters((f) => ({ ...f, rating_window: Number(e.target.value) || undefined }))}
                  className="bg-[var(--surface-2)] border rounded px-2 py-1 w-20 tabular-nums"
                />
              </label>
              <div>
                <div className="text-[var(--muted)] mb-2">Thème</div>
                <div className="flex flex-wrap gap-1.5">
                  <Chip active={!filters.theme && !filters.themes} onClick={() => setFilters((f) => buildFilters({ ...f, themes: undefined }, undefined))}>tous</Chip>
                  {THEMES.map((t) => (
                    <Chip key={t} active={filters.theme === t} onClick={() => setFilters((f) => buildFilters({ ...f, themes: undefined }, t))}>
                      {themeMeta(t).label}
                    </Chip>
                  ))}
                </div>
              </div>
              <div>
                <div className="text-[var(--muted)] mb-2">Source</div>
                <div className="flex gap-1.5">
                  {[
                    { label: "Toutes", v: undefined },
                    { label: "Lichess", v: "lichess" },
                    { label: "Mes blunders", v: "my_blunder" },
                  ].map((s) => (
                    <Chip key={s.label} active={filters.source_kind === s.v} onClick={() => setFilters((f) => ({ ...f, source_kind: s.v }))}>
                      {s.label}
                    </Chip>
                  ))}
                </div>
              </div>
            </div>
          </Card>

          {ex && (() => {
            const primary = pickPrimaryTheme(ex.themes);
            return (
              <Card>
                <CardHeader>
                  <div>
                    <CardTitle>Puzzle</CardTitle>
                    <div className="text-base font-medium text-[var(--foreground)] mt-1">{primary.label}</div>
                  </div>
                  {ex.difficulty != null && <span className="text-xs text-[var(--muted)] font-mono">{ex.difficulty}</span>}
                </CardHeader>
                <div className="flex items-start gap-2 text-sm leading-relaxed">
                  <Lightbulb className="size-4 text-[var(--accent)] mt-0.5 shrink-0" />
                  <span>{primary.hint}</span>
                </div>
                {ex.themes && ex.themes.length > 0 && (
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {ex.themes.slice(0, 6).map((t) => (
                      <span key={t} className="text-[10px] px-2 py-0.5 rounded bg-[var(--surface-2)] text-[var(--muted)]">
                        {themeMeta(t).label}
                      </span>
                    ))}
                  </div>
                )}
                <div className="mt-3 text-xs text-[var(--muted)] flex gap-4 tabular-nums">
                  <span>Tu joues les <b className="text-[var(--foreground)]">{ex.user_color === "white" ? "blancs" : "noirs"}</b></span>
                  <span>Essais : {tries}</span>
                  <span>Étape : <b className="text-[var(--foreground)]">{step + 1}</b> / {ex.total_user_steps}</span>
                </div>
              </Card>
            );
          })()}

          {/* Wrong attempt: don't reveal the answer, just nudge to retry. */}
          {!feedback && !abandoned && tries > 0 && lastFeedback && !lastFeedback.correct && (
            <Card className="border-[var(--danger)]/60">
              <div className="text-sm">
                <span className="text-[var(--danger)] font-medium">Pas le bon coup.</span>{" "}
                Réessaie — tu peux tenter autant de fois que tu veux.
              </div>
              <div className="text-xs text-[var(--muted)] mt-1">Essais : {tries}</div>
              <button
                onClick={abandon}
                className="mt-3 text-xs px-3 py-1.5 rounded border border-[var(--warning)]/40 text-[var(--warning)] hover:bg-[var(--warning)]/10 inline-flex items-center gap-1.5"
              >
                <Flag className="size-3" /> Abandonner & voir la solution
              </button>
            </Card>
          )}

          {/* In-progress multi-move puzzle: positive nudge */}
          {!feedback && !abandoned && ex && ex.total_user_steps > 1 && lastFeedback?.correct && !lastFeedback.complete && (
            <Card className="border-[var(--info)]/40">
              <div className="text-sm">
                <span className="text-[var(--info)] font-medium">Bonne idée !</span> Continue, il reste{" "}
                <b>{ex.total_user_steps - step}</b> {ex.total_user_steps - step > 1 ? "coups" : "coup"}.
              </div>
              {lastFeedback.opponent_san && (
                <div className="text-xs text-[var(--muted)] mt-1 font-mono">
                  Réponse adverse : {lastFeedback.opponent_san}
                </div>
              )}
            </Card>
          )}

          {/* Solved (feedback.correct && complete) */}
          {feedback?.correct && feedback.complete && (
            <Card className="border-[var(--accent)]/60">
              <div className="text-lg font-medium text-[var(--accent)]">Puzzle résolu</div>
              <div className="text-xs text-[var(--muted)] mt-1 font-mono">
                ton coup : <span className="text-[var(--foreground)]">{feedback.expected_san}</span> ({feedback.expected_uci})
              </div>
              <div className="text-xs text-[var(--muted)] mt-1">Essais : {tries === 0 ? "1 (premier coup)" : tries + 1}</div>
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

          {/* Abandoned: reveal solution + optional LLM commentary */}
          {abandoned && ex && (
            <Card className="border-[var(--warning)]/60">
              <div className="text-lg font-medium text-[var(--warning)]">Solution révélée</div>
              <div className="text-xs text-[var(--muted)] mt-1">
                Tu as fait {tries} {tries > 1 ? "tentatives" : "tentative"}. Voici la séquence gagnante :
              </div>
              {lastFeedback?.expected_san && (
                <div className="mt-2 font-mono text-base text-[var(--accent)]">
                  {lastFeedback.expected_san} <span className="text-[var(--muted)] text-xs">({lastFeedback.expected_uci})</span>
                </div>
              )}

              <div className="mt-4 border-t border-[var(--border)] pt-3">
                <div className="flex items-center gap-2 text-xs uppercase tracking-widest text-[var(--muted)] mb-2">
                  <Sparkles className="size-3.5 text-[var(--accent)]" />
                  Commentaire du coach
                </div>
                {coachStreaming && coachText.length === 0 && (
                  <div className="text-sm text-[var(--muted)] italic">le coach réfléchit…</div>
                )}
                {coachText && (
                  <div className="text-sm leading-relaxed whitespace-pre-wrap">
                    {coachText}
                    {coachStreaming && <span className="inline-block w-2 h-4 bg-[var(--accent)] ml-1 animate-pulse align-middle" />}
                  </div>
                )}
                {!coachStreaming && !coachText && (
                  <div className="text-xs text-[var(--muted)]">
                    Pas de commentaire (le service LLM n'est probablement pas démarré).
                  </div>
                )}
              </div>

              <div className="mt-4 flex gap-2">
                <button onClick={goNext} className="text-xs px-3 py-1.5 rounded bg-[var(--accent)] text-black font-medium">
                  Suivant →
                </button>
                <button onClick={replay} className="text-xs px-3 py-1.5 rounded border bg-[var(--surface-2)] hover:bg-[var(--surface)]">
                  Rejouer
                </button>
              </div>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}

function Chip({ children, active, onClick }: { children: React.ReactNode; active?: boolean; onClick?: () => void }) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "text-xs px-2 py-1 rounded border",
        active ? "bg-[var(--accent)] text-black border-[var(--accent)]" : "bg-[var(--surface-2)] text-[var(--muted)] hover:text-[var(--foreground)]",
      )}
    >
      {children}
    </button>
  );
}
