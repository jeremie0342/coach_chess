"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Chess } from "chess.js";
import { Crown, Flame, CheckCircle2 } from "lucide-react";
import { api } from "@/lib/api";
import { Board } from "@/components/chess/Board";
import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import { cn } from "@/lib/utils";
import { useActivePlanItem } from "@/hooks/useActivePlanItem";
import { ActivePlanBanner } from "@/components/plan/ActivePlanBanner";
import type {
  OpeningStart,
  OpeningMoveResp,
  OpeningGroupsResponse,
} from "@/types/opening-trainer";

type MasteryItem = {
  opening_key: string;
  base_name: string;
  user_color: "white" | "black";
  status: string;
  streak_days: number;
  best_streak: number;
  attempts: number;
  perfect_runs: number;
  last_perfect_date: string | null;
  perfect_today: boolean;
  mastered_at: string | null;
};
type MasteryResp = { mastery_streak: number; items: MasteryItem[] };

type MoveResponseWithMastery = OpeningMoveResp & {
  mastery?: {
    perfect: boolean;
    wrong_moves: number;
    streak_days: number;
    mastery_target: number;
    status: string;
    newly_mastered: boolean;
    best_streak: number;
  } | null;
};

type Session = OpeningStart & {
  history: { san: string; correct: boolean; expectedSan?: string | null }[];
  showHint: boolean;
};

export default function OpeningTrainerPage() {
  const plan = useActivePlanItem();
  const sp = useSearchParams();
  const qc = useQueryClient();
  const deepLinkKey = sp?.get("opening_key");

  const list = useQuery<OpeningGroupsResponse>({
    queryKey: ["opening-trainer-list-grouped"],
    queryFn: () => api<OpeningGroupsResponse>("/trainer/opening/list", { query: { grouped: "true" } }),
  });

  const mastery = useQuery<MasteryResp>({
    queryKey: ["opening-mastery"],
    queryFn: () => api<MasteryResp>("/trainer/opening/mastery"),
  });

  const [session, setSession] = useState<Session | null>(null);
  const [lastFeedback, setLastFeedback] = useState<MoveResponseWithMastery | null>(null);
  const [autoStarted, setAutoStarted] = useState(false);

  const start = useMutation({
    mutationFn: (opening_key: string) =>
      api<OpeningStart>("/trainer/opening/start", { json: { opening_key } }),
    onSuccess: (s) => {
      setSession({ ...s, history: [], showHint: false });
      setLastFeedback(null);
    },
  });

  // Deep-link auto-start: /opening-trainer?opening_key=foo[&plan_item=N]
  useEffect(() => {
    if (deepLinkKey && !autoStarted && !session) {
      setAutoStarted(true);
      start.mutate(deepLinkKey);
    }
  }, [deepLinkKey, autoStarted, session, start]);

  const move = useMutation({
    mutationFn: (uci: string) =>
      api<MoveResponseWithMastery>(`/trainer/opening/${session!.id}/move`, { json: { move: uci } }),
    onSuccess: (r) => {
      setLastFeedback(r);
      if (!session) return;
      if (r.correct) {
        // Increment plan item once when the line is fully completed.
        if (r.status === "completed") {
          plan.increment();
          qc.invalidateQueries({ queryKey: ["opening-mastery"] });
        }
        setSession({
          ...session,
          current_fen: r.current_fen,
          expected_user_uci: r.expected_user_uci ?? null,
          expected_user_san: r.expected_user_san ?? null,
          coach_hint: r.coach_hint ?? null,
          ply: r.ply ?? session.ply,
          total_plies: r.total_plies ?? session.total_plies,
          history: [...session.history, { san: r.your_san ?? "", correct: true }],
          showHint: false,
        });
      } else {
        setSession({
          ...session,
          history: [...session.history, { san: r.your_san ?? "?", correct: false, expectedSan: r.expected_user_san }],
        });
      }
    },
  });

  const close = useMutation({
    mutationFn: () => api(`/trainer/opening/${session!.id}`, { method: "DELETE" }),
    onSuccess: () => { setSession(null); setLastFeedback(null); },
  });

  const handleMove = ({ from, to, promotion }: { from: string; to: string; promotion?: string }) => {
    if (!session || move.isPending) return false;
    try {
      const c = new Chess(session.current_fen);
      const mv = c.move({ from, to, promotion: promotion ?? "q" });
      if (!mv) return false;
      const uci = `${from}${to}${mv.promotion ?? ""}`;
      move.mutate(uci);
      return true;
    } catch {
      return false;
    }
  };

  if (!session) {
    return (
      <div className="px-4 py-6 md:px-8 md:py-8 max-w-5xl">
        <header className="mb-6 flex items-end justify-between gap-3">
          <div>
            <div className="text-xs uppercase tracking-widest text-[var(--muted)]">Entraînement</div>
            <h1 className="text-3xl font-semibold mt-1">Opening trainer</h1>
            <p className="text-sm text-[var(--muted)] mt-2">
              Apprends les lignes principales d&apos;une ouverture coup par coup, avec les explications du coach.
            </p>
          </div>
          <Link
            href="/opening-trainer/repertoire"
            className="text-xs px-3 py-1.5 rounded border bg-[var(--surface-2)] hover:bg-[var(--surface)] hover:border-[var(--accent)]/60 shrink-0"
          >
            Mon répertoire →
          </Link>
        </header>

        <ActivePlanBanner item={plan.item} onClear={plan.clear} />

        {mastery.data && <MasteryPanel data={mastery.data} onStart={(k) => start.mutate(k)} />}

        {list.isLoading && <div className="text-[var(--muted)]">Chargement…</div>}

        {(["white", "black"] as const).map((side) => {
          const groups = (list.data?.groups ?? []).filter((g) => g.user_color === side);
          if (groups.length === 0) return null;
          return (
            <section key={side} className="mb-6">
              <div className="text-xs uppercase tracking-widest text-[var(--muted)] mb-3">
                {side === "white" ? "Ouvertures Blancs" : "Défenses Noirs"}
              </div>
              <div className="grid md:grid-cols-2 gap-4">
                {groups.map((g) => (
                  <Card key={g.base_name}>
                    <CardHeader>
                      <div>
                        <CardTitle>{g.base_name}</CardTitle>
                        <div className="text-xs text-[var(--muted)] mt-1">
                          <span className="font-mono">{g.eco ?? "—"}</span> ·{" "}
                          {g.user_color === "white" ? "Blancs" : "Noirs"} ·{" "}
                          {g.variants.length} variante{g.variants.length > 1 ? "s" : ""}
                        </div>
                      </div>
                    </CardHeader>
                    <p className="text-sm text-[var(--foreground)]/80 leading-relaxed mb-4">{g.summary}</p>
                    <div className="space-y-1.5">
                      {g.variants.map((v) => (
                        <button
                          key={v.key}
                          onClick={() => start.mutate(v.key)}
                          className="w-full text-left px-3 py-2 rounded border bg-[var(--surface-2)] hover:bg-[var(--surface)] hover:border-[var(--accent)]/60 transition-colors flex items-center justify-between gap-3"
                        >
                          <div className="min-w-0">
                            <div className="text-sm truncate">
                              {/* Strip the base prefix from the variant name */}
                              {v.name.startsWith(g.base_name + " - ")
                                ? v.name.slice(g.base_name.length + 3)
                                : v.name}
                            </div>
                            <div className="text-xs text-[var(--muted)] font-mono">
                              {v.eco ?? ""} · {v.plies} plis
                            </div>
                          </div>
                          <span className="text-[var(--muted)] text-xs">→</span>
                        </button>
                      ))}
                    </div>
                  </Card>
                ))}
              </div>
            </section>
          );
        })}
      </div>
    );
  }

  const wrongBook = lastFeedback?.status === "wrong_book";
  const completed = lastFeedback?.status === "completed" || session.ply >= session.total_plies;

  return (
    <div className="px-4 py-6 md:px-8 md:py-8 max-w-7xl">
      <header className="mb-6 flex items-end justify-between gap-3">
        <div>
          <div className="text-xs uppercase tracking-widest text-[var(--muted)]">
            Opening trainer · <button onClick={() => close.mutate()} className="hover:text-[var(--foreground)]">← retour</button>
          </div>
          <h1 className="text-2xl font-semibold mt-1">{session.opening.name}</h1>
          {session.opening.variant_label && session.opening.variant_label !== "Ligne principale" && (
            <div className="mt-1 inline-flex items-center gap-1.5 text-xs px-2 py-0.5 rounded bg-[var(--warning)]/15 text-[var(--warning)]">
              Variante tirée : <b>{session.opening.variant_label}</b>
            </div>
          )}
          <div className="text-sm text-[var(--muted)] mt-1">
            <span className="font-mono">{session.opening.eco}</span> · {session.opening.user_color === "white" ? "Blancs" : "Noirs"} · ply {session.ply}/{session.total_plies}
          </div>
        </div>
        <button
          onClick={() => start.mutate(session.opening.key)}
          className="text-xs px-3 py-1.5 rounded border bg-[var(--surface-2)] hover:bg-[var(--surface)]"
        >
          Recommencer
        </button>
      </header>

      <ActivePlanBanner item={plan.item} onClear={plan.clear} />

      <div className="grid lg:grid-cols-[auto_1fr] gap-6 lg:gap-8">
        <div className="w-full max-w-[520px] mx-auto lg:mx-0">
          <Board
            fen={session.current_fen}
            orientation={session.opening.user_color}
            draggableColor={session.opening.user_color}
            onMove={handleMove}
            size={520}
          />
          <div className="mt-3 h-2 bg-[var(--surface-2)] rounded overflow-hidden">
            <div
              className="h-full bg-[var(--accent)] transition-all"
              style={{ width: `${(session.ply / Math.max(session.total_plies, 1)) * 100}%` }}
            />
          </div>
        </div>

        <div className="space-y-4 min-w-0">
          {completed ? (
            <Card className={cn(
              "border-l-4",
              lastFeedback?.mastery?.newly_mastered ? "border-l-[var(--warning)]" :
              lastFeedback?.mastery?.perfect ? "border-l-[var(--accent)]" :
              "border-l-[var(--muted)]",
            )}>
              {lastFeedback?.mastery?.newly_mastered ? (
                <>
                  <div className="flex items-center gap-2">
                    <Crown className="size-5 text-[var(--warning)]" />
                    <CardTitle>Maîtrisée 🎉</CardTitle>
                  </div>
                  <div className="text-sm mt-2">
                    7 jours parfaits d'affilée — <b>{session.opening.base_name ?? session.opening.name}</b>{" "}
                    est désormais maîtrisée. Le coach va te proposer une nouvelle variante demain.
                  </div>
                </>
              ) : lastFeedback?.mastery?.perfect ? (
                <>
                  <div className="flex items-center gap-2">
                    <Flame className="size-5 text-[var(--accent)]" />
                    <CardTitle>Sans-faute du jour</CardTitle>
                  </div>
                  <div className="text-sm mt-2">
                    Tu as enchaîné la ligne complète sans erreur.
                  </div>
                  {lastFeedback.mastery && (
                    <StreakBar
                      current={lastFeedback.mastery.streak_days}
                      target={lastFeedback.mastery.mastery_target}
                    />
                  )}
                </>
              ) : (
                <>
                  <CardTitle>Ligne terminée</CardTitle>
                  <div className="text-sm mt-2">
                    Tu as fini la ligne, mais avec {lastFeedback?.mastery?.wrong_moves ?? "?"} erreur(s).
                    Le streak repart à zéro — refais-la sans erreur pour la valider aujourd'hui.
                  </div>
                  {lastFeedback?.mastery && (
                    <StreakBar
                      current={0}
                      target={lastFeedback.mastery.mastery_target}
                      reset
                    />
                  )}
                </>
              )}
              <button
                onClick={() => start.mutate(session.opening.key)}
                className="mt-3 text-xs px-3 py-1.5 rounded bg-[var(--accent)] text-black font-medium"
              >
                Refaire →
              </button>
            </Card>
          ) : (
            <Card>
              <CardHeader>
                <CardTitle>Joue le bon coup</CardTitle>
                {!session.showHint && session.expected_user_san && (
                  <button
                    onClick={() => setSession({ ...session, showHint: true })}
                    className="text-xs text-[var(--info)] hover:underline"
                  >
                    Indice ?
                  </button>
                )}
              </CardHeader>
              {session.showHint && session.expected_user_san && (
                <div className="space-y-2 text-sm">
                  <div className="font-mono text-base text-[var(--accent)]">{session.expected_user_san}</div>
                  {session.coach_hint && (
                    <div className="text-[var(--muted)] leading-relaxed">{session.coach_hint}</div>
                  )}
                </div>
              )}
              {!session.showHint && (
                <div className="text-sm text-[var(--muted)]">
                  À toi de jouer pour {session.opening.user_color === "white" ? "les blancs" : "les noirs"}.
                </div>
              )}
            </Card>
          )}

          {wrongBook && lastFeedback && (
            <Card className="border-[var(--warning)]/60">
              <div className="text-sm">
                <div className="text-[var(--warning)] font-medium">Pas le coup théorique</div>
                <div className="mt-2">
                  Tu as joué <span className="font-mono">{lastFeedback.your_san}</span>, ici la théorie joue{" "}
                  <span className="font-mono text-[var(--accent)]">{lastFeedback.expected_user_san}</span>.
                </div>
                {lastFeedback.coach_hint && (
                  <div className="text-[var(--muted)] text-xs mt-2 leading-relaxed">{lastFeedback.coach_hint}</div>
                )}
              </div>
            </Card>
          )}

          <Card>
            <CardHeader><CardTitle>Plan</CardTitle></CardHeader>
            <ul className="text-sm leading-relaxed space-y-1.5 list-disc pl-5 marker:text-[var(--muted)]">
              {session.opening.plan.map((p, i) => <li key={i}>{p}</li>)}
            </ul>
          </Card>

          {session.history.length > 0 && (
            <Card>
              <CardHeader><CardTitle>Historique</CardTitle></CardHeader>
              <ol className="text-sm font-mono space-y-1">
                {session.history.map((h, i) => (
                  <li key={i} className={cn("flex justify-between", h.correct ? "text-[var(--foreground)]" : "text-[var(--danger)]")}>
                    <span>{i + 1}. {h.san}</span>
                    {!h.correct && h.expectedSan && <span className="text-[var(--accent)]">{h.expectedSan}</span>}
                  </li>
                ))}
              </ol>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}

function MasteryPanel({ data, onStart }: { data: MasteryResp; onStart: (key: string) => void }) {
  const active = data.items.filter((i) => i.status === "active");
  const mastered = data.items.filter((i) => i.status === "mastered");
  if (active.length === 0 && mastered.length === 0) return null;
  return (
    <Card className="mb-6">
      <CardHeader>
        <CardTitle>Ton répertoire en construction</CardTitle>
        <div className="text-xs text-[var(--muted)]">
          {data.mastery_streak} jours parfaits d'affilée = maîtrisée
        </div>
      </CardHeader>
      {active.length > 0 && (
        <div className="grid md:grid-cols-2 gap-3 mb-3">
          {active.map((it) => (
            <button
              key={it.opening_key}
              onClick={() => onStart(it.opening_key)}
              className="text-left rounded-lg border bg-[var(--surface-2)] hover:bg-[var(--surface)] hover:border-[var(--accent)]/60 p-3 transition-colors"
            >
              <div className="flex items-center gap-2 mb-2">
                <span className={cn(
                  "text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded",
                  it.user_color === "white" ? "bg-white/10 text-white" : "bg-black/40 text-white",
                )}>{it.user_color === "white" ? "Blancs" : "Noirs"}</span>
                <div className="font-medium text-sm">{it.base_name}</div>
                {it.perfect_today && (
                  <span className="ml-auto text-[10px] text-[var(--accent)] flex items-center gap-1">
                    <CheckCircle2 className="size-3" /> fait aujourd'hui
                  </span>
                )}
              </div>
              <StreakBar current={it.streak_days} target={data.mastery_streak} />
              <div className="text-xs text-[var(--muted)] mt-2 flex gap-3 tabular-nums">
                <span>Best : {it.best_streak}j</span>
                <span>{it.perfect_runs} runs parfaits / {it.attempts} essais</span>
              </div>
            </button>
          ))}
        </div>
      )}
      {mastered.length > 0 && (
        <div className="border-t border-[var(--border)] pt-3">
          <div className="text-xs uppercase tracking-wider text-[var(--muted)] mb-2">
            Maîtrisées
          </div>
          <div className="flex flex-wrap gap-2">
            {mastered.map((it) => (
              <span key={it.opening_key} className="text-xs px-2 py-1 rounded bg-[var(--accent)]/15 text-[var(--accent)] flex items-center gap-1">
                <Crown className="size-3" />
                {it.base_name} <span className="text-[var(--muted)]">· {it.user_color}</span>
              </span>
            ))}
          </div>
        </div>
      )}
    </Card>
  );
}

function StreakBar({ current, target, reset }: { current: number; target: number; reset?: boolean }) {
  const pct = Math.min(100, (current / Math.max(target, 1)) * 100);
  return (
    <div>
      <div className="flex items-center justify-between text-xs text-[var(--muted)] tabular-nums mb-1">
        <span className="flex items-center gap-1">
          <Flame className={cn("size-3", current > 0 ? "text-[var(--accent)]" : "text-[var(--muted)]")} />
          {current} / {target} jours
        </span>
        {reset && <span className="text-[var(--danger)] text-[10px] uppercase">reset</span>}
      </div>
      <div className="h-1.5 bg-[var(--surface-2)] rounded overflow-hidden">
        <div
          className={cn("h-full transition-all", current > 0 ? "bg-[var(--accent)]" : "bg-[var(--muted)]/40")}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}
