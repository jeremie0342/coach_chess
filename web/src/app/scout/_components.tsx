"use client";

import Link from "next/link";
import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import { cn } from "@/lib/utils";

export type MoveStat = { uci?: string; san?: string; games?: number; n?: number; winrate: number; [k: string]: unknown };
export type TimeClassStats = { time_class: string; games: number; winrate: number; wins: number; losses: number; draws: number };
export type ColorStats = { color: string; games: number; winrate: number; wins: number; losses: number; draws: number };
export type PhaseQuality = { phase: string; moves: number; blunders: number; mistakes: number; inaccuracies: number; blunder_rate: number };
export type RepertoireBranch = {
  my_color: string;
  line_san: string[];
  last_ply: number;
  opponent_responses: { uci: string; san: string; games: number; winrate: number }[];
};
export type LearningProbeStep = {
  ply: number;
  expected_san: string;
  expected_uci: string;
  actual_responses: { uci: string; san: string; games: number; winrate: number; is_theory: boolean }[];
  games_reaching: number;
};
export type LearningOpeningProbe = {
  opening_key: string;
  name: string;
  base_name: string;
  branch_label: string;
  user_color: string;
  eco: string;
  summary: string;
  full_line_san: string[];
  games_in_opening: number;
  steps: LearningProbeStep[];
};
export type Weakness = {
  category: string;
  phase: string | null;
  severity: number;
  occurrences: number;
  details: Record<string, unknown> | null;
  sample_game_ids: number[];
};

export type ScoutPayload = {
  opponent: string;
  games_imported: number;
  games_skipped_existing: number;
  elapsed_s: number;
  opening_profile: {
    games_seen: number;
    avg_out_of_book_ply: number | null;
    first_move_as_white: MoveStat[];
    response_to_e4: MoveStat[];
    response_to_d4: MoveStat[];
    response_to_nf3: MoveStat[];
    top_openings_white: Record<string, unknown>[];
    top_openings_black: Record<string, unknown>[];
  };
  profile: {
    games_total: number;
    wins: number;
    losses: number;
    draws: number;
    last_10: string[];
    current_rating: number | null;
    peak_rating: number | null;
    by_time_class: TimeClassStats[];
    by_color: ColorStats[];
  } | null;
  phase_quality: PhaseQuality[];
  vs_my_repertoire: RepertoireBranch[];
  vs_learning_openings?: LearningOpeningProbe[];
  structured_plan: string | null;
  weaknesses: Weakness[];
  battle_plan: string | null;
  snapshot_id?: number;
  scouted_at?: string;
};

export function ScoutResult({ data }: { data: ScoutPayload }) {
  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>{data.opponent}</CardTitle>
          <span className="text-xs text-[var(--muted)] tabular-nums">
            {data.games_imported} importées · {data.games_skipped_existing} déjà connues · {data.elapsed_s}s
          </span>
        </CardHeader>
        <ProfileBlock data={data} />
      </Card>

      {data.structured_plan && (
        <Card className="border-l-4 border-l-[var(--accent)]">
          <CardHeader><CardTitle>Plan de bataille</CardTitle></CardHeader>
          <div className="text-sm whitespace-pre-wrap leading-relaxed">{data.structured_plan}</div>
        </Card>
      )}

      {data.battle_plan && (
        <Card className="border-l-4 border-l-[var(--info)]">
          <CardHeader><CardTitle>Plan narratif (LLM)</CardTitle></CardHeader>
          <div className="text-sm whitespace-pre-wrap leading-relaxed text-[var(--muted)]">{data.battle_plan}</div>
        </Card>
      )}

      {data.vs_my_repertoire.length > 0 && (
        <Card>
          <CardHeader><CardTitle>Vs ton répertoire</CardTitle></CardHeader>
          <div className="text-xs text-[var(--muted)] mb-3">Pour chaque ouverture que tu joues souvent, voici ce qu&apos;il a tendance à répondre.</div>
          <div className="space-y-3">
            {data.vs_my_repertoire.map((b, i) => (
              <div key={i} className="border-l-2 border-[var(--border)] pl-3">
                <div className="text-xs text-[var(--muted)] uppercase tracking-wider mb-1">
                  Quand tu joues <b className="text-[var(--foreground)]">{b.my_color === "white" ? "BLANCS" : "NOIRS"}</b>
                </div>
                <div className="font-mono text-sm mb-1">
                  {b.line_san.map((s, j) => (
                    <span key={j} className="mr-2">
                      {j % 2 === 0 && <span className="text-[var(--muted)] text-xs">{Math.floor(j / 2) + 1}.</span>}{s}
                    </span>
                  ))}
                </div>
                <div className="text-xs space-y-0.5 ml-2">
                  {b.opponent_responses.map((r, j) => (
                    <div key={j} className="flex gap-3">
                      <span className="font-mono text-[var(--info)]">{r.san}</span>
                      <span className="text-[var(--muted)] tabular-nums">{r.games}×</span>
                      <span className={cn(
                        "tabular-nums",
                        r.winrate >= 0.55 ? "text-[var(--danger)]" :
                        r.winrate <= 0.40 ? "text-[var(--accent)]" :
                        "text-[var(--muted)]",
                      )}>
                        wr {Math.round(r.winrate * 100)}%
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}

      {data.vs_learning_openings && data.vs_learning_openings.length > 0 && (
        <LearningOpeningsSection probes={data.vs_learning_openings} />
      )}

      {data.phase_quality.some((p) => p.moves > 0) && (
        <Card>
          <CardHeader><CardTitle>Force par phase</CardTitle></CardHeader>
          <table className="w-full text-sm">
            <thead className="text-xs text-[var(--muted)] uppercase tracking-wider">
              <tr><th className="text-left py-1">Phase</th><th className="text-right py-1">Coups</th><th className="text-right py-1">Blunders</th><th className="text-right py-1">Mistakes</th><th className="text-right py-1">Inaccs</th><th className="text-right py-1">Taux blunder</th></tr>
            </thead>
            <tbody>
              {data.phase_quality.map((p) => (
                <tr key={p.phase} className="border-t border-[var(--border)]">
                  <td className="py-2 capitalize">{p.phase}</td>
                  <td className="py-2 text-right tabular-nums text-[var(--muted)]">{p.moves}</td>
                  <td className="py-2 text-right text-[var(--danger)] tabular-nums">{p.blunders}</td>
                  <td className="py-2 text-right text-[var(--warning)] tabular-nums">{p.mistakes}</td>
                  <td className="py-2 text-right text-[var(--info)] tabular-nums">{p.inaccuracies}</td>
                  <td className="py-2 text-right tabular-nums font-mono">{(p.blunder_rate * 100).toFixed(1)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}

      {data.phase_quality.length > 0 && data.phase_quality.every((p) => p.moves === 0) && (
        <Card className="border-[var(--muted)]/30">
          <div className="text-xs text-[var(--muted)]">
            Force par phase indisponible — les parties de l&apos;adversaire n&apos;ont pas été analysées par Stockfish.
          </div>
        </Card>
      )}

      <div className="grid md:grid-cols-2 gap-4">
        <MoveTable title="1er coup (blancs)" moves={data.opening_profile.first_move_as_white} />
        <MoveTable title="Réponse à 1.e4" moves={data.opening_profile.response_to_e4} />
        <MoveTable title="Réponse à 1.d4" moves={data.opening_profile.response_to_d4} />
        <MoveTable title="Réponse à 1.Nf3" moves={data.opening_profile.response_to_nf3} />
      </div>

      {data.weaknesses?.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Faiblesses détectées</CardTitle>
            <span className="text-xs text-[var(--muted)]">Clique un game pour voir l&apos;exemple en review.</span>
          </CardHeader>
          <ul className="text-sm space-y-2">
            {data.weaknesses.slice(0, 15).map((w, i) => (
              <li key={i} className="border-b border-[var(--border)] last:border-0 pb-2">
                <div className="flex items-center gap-3 flex-wrap">
                  <span className="text-xs px-1.5 py-0.5 rounded bg-[var(--surface-2)] font-mono">{w.category}</span>
                  {w.phase && (
                    <span className="text-xs text-[var(--muted)] uppercase tracking-wider">{w.phase}</span>
                  )}
                  <span className="text-xs text-[var(--muted)] tabular-nums">
                    {w.occurrences}× · sévérité {w.severity.toFixed(2)}
                  </span>
                  {w.sample_game_ids.length > 0 && (
                    <span className="text-xs ml-auto flex gap-2">
                      <span className="text-[var(--muted)]">exemples :</span>
                      {w.sample_game_ids.slice(0, 3).map((gid) => (
                        <Link key={gid} href={`/games/${gid}`} className="text-[var(--info)] hover:underline font-mono">#{gid}</Link>
                      ))}
                    </span>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}

export function ProfileBlock({ data }: { data: ScoutPayload }) {
  const p = data.profile;
  const o = data.opening_profile;
  if (!p) {
    return (
      <div className="text-sm text-[var(--muted)]">
        {o.games_seen} parties · sort du livre vers le ply {o.avg_out_of_book_ply ?? "—"}
      </div>
    );
  }
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3 text-sm">
        <Stat label="Parties" value={String(p.games_total)} />
        <Stat
          label="Bilan"
          value={`${p.wins}W ${p.losses}L ${p.draws}D`}
          sub={`${Math.round(((p.wins + 0.5 * p.draws) / Math.max(p.games_total, 1)) * 100)}%`}
        />
        <Stat label="Rating" value={p.current_rating?.toString() ?? "—"} sub={p.peak_rating ? `pic ${p.peak_rating}` : ""} />
        <Stat label="Sort du livre" value={o.avg_out_of_book_ply ? `ply ${o.avg_out_of_book_ply}` : "—"} />
        <div>
          <div className="text-xs uppercase tracking-wider text-[var(--muted)]">10 dernières</div>
          <div className="flex gap-0.5 mt-1.5">
            {p.last_10.map((r, i) => (
              <span
                key={i}
                className={cn(
                  "size-4 inline-flex items-center justify-center text-[10px] font-bold rounded-sm",
                  r === "W" ? "bg-[var(--accent)]/30 text-[var(--accent)]" :
                  r === "L" ? "bg-[var(--danger)]/30 text-[var(--danger)]" :
                  "bg-[var(--muted)]/30 text-[var(--muted)]",
                )}
              >{r}</span>
            ))}
          </div>
        </div>
      </div>

      {p.by_color.length > 0 && (
        <div className="flex gap-4 text-xs text-[var(--muted)] flex-wrap">
          {p.by_color.map((c) => (
            <span key={c.color}>
              <span className="uppercase text-[10px] tracking-wider font-mono mr-1">{c.color === "white" ? "Blancs" : "Noirs"}</span> <b className="text-[var(--foreground)]">{Math.round(c.winrate * 100)}%</b> sur {c.games} parties
            </span>
          ))}
          <span className="border-l border-[var(--border)] pl-4">
            Time controls :
            {p.by_time_class.slice(0, 4).map((t) => (
              <span key={t.time_class} className="ml-2">
                <b className="text-[var(--foreground)]">{t.time_class}</b> {t.games}p ({Math.round(t.winrate * 100)}%)
              </span>
            ))}
          </span>
        </div>
      )}
    </div>
  );
}

export function Stat({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div>
      <div className="text-xs uppercase tracking-wider text-[var(--muted)]">{label}</div>
      <div className="text-base mt-1 tabular-nums">{value}</div>
      {sub && <div className="text-xs text-[var(--muted)] font-mono">{sub}</div>}
    </div>
  );
}

function LearningOpeningsSection({ probes }: { probes: LearningOpeningProbe[] }) {
  // Group probes by opening_key so we can show variants together
  const grouped = new Map<string, LearningOpeningProbe[]>();
  for (const p of probes) {
    if (!grouped.has(p.opening_key)) grouped.set(p.opening_key, []);
    grouped.get(p.opening_key)!.push(p);
  }
  return (
    <Card>
      <CardHeader>
        <CardTitle>Vs tes ouvertures en cours</CardTitle>
        <span className="text-xs text-[var(--muted)]">Comment il répond aux lignes que tu drilles.</span>
      </CardHeader>
      <div className="space-y-5">
        {Array.from(grouped.entries()).map(([key, variants]) => {
          const first = variants[0];
          const totalGames = variants.reduce((s, v) => s + v.games_in_opening, 0);
          return (
            <div key={key} className="border-l-2 border-[var(--accent)]/40 pl-3">
              <div className="flex items-baseline justify-between gap-3 flex-wrap">
                <div>
                  <span className="font-medium">{first.name}</span>
                  <span className="text-xs text-[var(--muted)] ml-2 font-mono">{first.eco}</span>
                  <span className="text-xs text-[var(--muted)] ml-2">
                    (tu joues {first.user_color === "white" ? "BLANCS" : "NOIRS"})
                  </span>
                </div>
                <span className="text-xs text-[var(--muted)] tabular-nums">
                  {totalGames} partie{totalGames > 1 ? "s" : ""} de l&apos;adversaire dans cette ouverture
                </span>
              </div>

              {totalGames === 0 && (
                <div className="text-xs text-[var(--muted)] mt-2 italic">
                  L&apos;adversaire n&apos;a jamais joué dans cette ouverture sur ses {variants.length === 1 ? "parties récentes" : "parties récentes"}.
                </div>
              )}

              {variants.map((v, vi) => v.steps.length > 0 && (
                <details key={vi} open={vi === 0} className="mt-3">
                  <summary className="text-xs text-[var(--muted)] cursor-pointer hover:text-[var(--foreground)]">
                    {v.branch_label} — {v.games_in_opening} parties · ligne de {v.full_line_san.length} demi-coups
                  </summary>
                  <ol className="mt-2 space-y-2 text-sm">
                    {v.steps.map((step) => {
                      const theoryResp = step.actual_responses.find((r) => r.is_theory);
                      const nonTheory = step.actual_responses.filter((r) => !r.is_theory);
                      return (
                        <li key={step.ply} className="border-l border-[var(--border)] pl-3">
                          <div className="text-xs text-[var(--muted)]">
                            Au demi-coup {step.ply} — théorie attend{" "}
                            <span className="font-mono text-[var(--foreground)]">{step.expected_san}</span>
                            {" "}({step.games_reaching} partie{step.games_reaching > 1 ? "s" : ""} ont atteint cette position)
                          </div>
                          <div className="mt-1 space-y-0.5 text-xs">
                            {theoryResp && (
                              <div className="flex gap-3">
                                <span className="font-mono text-[var(--accent)]">
                                  [théorie] {theoryResp.san}
                                </span>
                                <span className="text-[var(--muted)] tabular-nums">{theoryResp.games}×</span>
                                <span className={cn(
                                  "tabular-nums",
                                  theoryResp.winrate >= 0.55 ? "text-[var(--danger)]" :
                                  theoryResp.winrate <= 0.40 ? "text-[var(--accent)]" :
                                  "text-[var(--muted)]",
                                )}>wr {Math.round(theoryResp.winrate * 100)}%</span>
                                <span className="text-[var(--muted)]">— il connaît la théorie ici</span>
                              </div>
                            )}
                            {nonTheory.map((r, i) => (
                              <div key={i} className="flex gap-3">
                                <span className="font-mono text-[var(--warning)]">
                                  [écart] {r.san}
                                </span>
                                <span className="text-[var(--muted)] tabular-nums">{r.games}×</span>
                                <span className={cn(
                                  "tabular-nums",
                                  r.winrate >= 0.55 ? "text-[var(--danger)]" :
                                  r.winrate <= 0.40 ? "text-[var(--accent)]" :
                                  "text-[var(--muted)]",
                                )}>wr {Math.round(r.winrate * 100)}%</span>
                                <span className="text-[var(--muted)]">— hors théorie, profite-en</span>
                              </div>
                            ))}
                          </div>
                        </li>
                      );
                    })}
                  </ol>
                </details>
              ))}
            </div>
          );
        })}
      </div>
    </Card>
  );
}

export function MoveTable({ title, moves }: { title: string; moves: MoveStat[] }) {
  if (!moves || moves.length === 0) return null;
  return (
    <Card>
      <CardHeader><CardTitle>{title}</CardTitle></CardHeader>
      <table className="w-full text-sm">
        <tbody>
          {moves.slice(0, 6).map((m, i) => (
            <tr key={i} className="border-b border-[var(--border)] last:border-0">
              <td className="py-1.5 font-mono">{m.san ?? m.uci ?? "?"}</td>
              <td className="py-1.5 text-right tabular-nums text-[var(--muted)] text-xs">{(m.games ?? m.n) ?? "—"} parties</td>
              <td className="py-1.5 text-right tabular-nums">{Math.round((m.winrate ?? 0) * 100)}%</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}
