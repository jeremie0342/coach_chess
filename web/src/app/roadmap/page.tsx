"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Target, TrendingUp, Lock, CheckCircle2, Flag } from "lucide-react";
import { api } from "@/lib/api";
import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import { cn } from "@/lib/utils";
import { kindLabel } from "@/lib/plan-items";
import type { Roadmap, RoadmapPhase } from "@/types/roadmap";

export default function RoadmapPage() {
  const q = useQuery<Roadmap>({
    queryKey: ["roadmap"],
    queryFn: () => api<Roadmap>("/coach/me/roadmap"),
  });

  return (
    <div className="px-4 py-6 md:px-8 md:py-8 max-w-6xl">
      <header className="mb-6">
        <div className="text-xs uppercase tracking-widest text-[var(--muted)]">Coach</div>
        <h1 className="text-3xl font-semibold mt-1">Roadmap</h1>
        <p className="text-sm text-[var(--muted)] mt-2">
          Le voyage 450 → 2000 ELO, en 5 phases. Le plan du jour découle automatiquement de ta phase courante.
        </p>
      </header>

      {q.isLoading && <Card className="animate-pulse h-32" />}
      {q.data && <RoadmapContent data={q.data} />}
    </div>
  );
}

function RoadmapContent({ data }: { data: Roadmap }) {
  const span = data.goal_rating - 400; // visualize from 400 to 2000
  const xFor = (r: number) => Math.max(0, Math.min(1, (r - 400) / span)) * 100;
  const currentPct = data.current_rating != null ? xFor(data.current_rating) : 0;

  return (
    <div className="space-y-6">
      {/* Hero: global path */}
      <Card>
        <CardHeader>
          <div>
            <CardTitle>Objectif global</CardTitle>
            <div className="text-sm text-[var(--muted)] mt-1">450 → 2000 ELO Rapid</div>
          </div>
          <Flag className="size-5 text-[var(--accent)]" />
        </CardHeader>

        {/* Track */}
        <div className="relative mt-4 mb-10">
          <div className="h-2 bg-[var(--surface-2)] rounded-full">
            <div
              className="h-full bg-[var(--accent)] rounded-full transition-all"
              style={{ width: `${currentPct}%` }}
            />
          </div>

          {/* Phase markers */}
          {[0, 900, 1300, 1700, 2100].map((r, i) => {
            const reached = data.current_rating != null && data.current_rating >= r;
            return (
              <div key={r} className="absolute top-1 -translate-x-1/2" style={{ left: `${xFor(r)}%` }}>
                <div className={cn(
                  "size-2.5 rounded-full -mt-1.5 border-2 border-[var(--background)]",
                  reached ? "bg-[var(--accent)]" : "bg-[var(--muted)]/40",
                )} />
                <div className="absolute top-3 left-1/2 -translate-x-1/2 text-[10px] text-[var(--muted)] font-mono tabular-nums whitespace-nowrap">
                  {r === 0 ? "" : r}
                </div>
                <div className="absolute top-7 left-1/2 -translate-x-1/2 text-[10px] uppercase tracking-wider text-[var(--muted)] whitespace-nowrap">
                  {["A", "B", "C", "D", "E"][i]}
                </div>
              </div>
            );
          })}

          {/* Goal marker */}
          <div className="absolute top-1 -translate-x-1/2" style={{ left: `100%` }}>
            <div className="size-3 rounded-full -mt-1.5 bg-[var(--accent)] border-2 border-[var(--background)]" />
            <Target className="absolute -top-1 left-1/2 -translate-x-1/2 size-3 text-[var(--accent)]" style={{ marginTop: -16 }} />
          </div>

          {/* Current rating marker */}
          {data.current_rating != null && (
            <div className="absolute -top-2 -translate-x-1/2 z-10" style={{ left: `${currentPct}%` }}>
              <div className="bg-[var(--surface)] border border-[var(--accent)] rounded px-2 py-0.5 text-xs font-mono tabular-nums text-[var(--accent)] shadow whitespace-nowrap">
                {data.current_rating}
              </div>
            </div>
          )}
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm mt-12">
          <Stat label="Rating actuel" value={data.current_rating ?? "—"} mono />
          <Stat
            label="Delta 30j"
            value={
              data.rating_delta_30d != null
                ? `${data.rating_delta_30d > 0 ? "+" : ""}${data.rating_delta_30d}`
                : "—"
            }
            tone={
              data.rating_delta_30d == null
                ? undefined
                : data.rating_delta_30d > 0
                ? "text-[var(--accent)]"
                : data.rating_delta_30d < 0
                ? "text-[var(--danger)]"
                : undefined
            }
            mono
          />
          <Stat label="Prochain palier" value={data.next_milestone} mono />
          <Stat
            label="ETA"
            value={
              data.eta_days_to_next_milestone != null
                ? formatEta(data.eta_days_to_next_milestone)
                : "—"
            }
          />
        </div>
      </Card>

      {/* Current phase highlight */}
      {(() => {
        const current = data.phases.find((p) => p.state === "current");
        if (!current) return null;
        const progressPct = data.progress_in_phase != null ? Math.round(data.progress_in_phase * 100) : 0;
        return (
          <Card className="border-l-4 border-l-[var(--accent)]">
            <CardHeader>
              <div>
                <div className="text-xs uppercase tracking-widest text-[var(--muted)]">Phase courante</div>
                <CardTitle>{current.label}</CardTitle>
              </div>
              <Link href="/today" className="text-xs px-3 py-1.5 rounded bg-[var(--accent)] text-black font-medium">
                Plan du jour →
              </Link>
            </CardHeader>

            <div className="mb-4">
              <div className="flex items-baseline justify-between mb-1">
                <span className="text-xs text-[var(--muted)] tabular-nums">
                  {current.floor === 0 ? "0" : current.floor} → {current.ceiling}
                </span>
                <span className="text-xs tabular-nums">{progressPct}%</span>
              </div>
              <div className="h-1.5 bg-[var(--surface-2)] rounded-full">
                <div
                  className="h-full bg-[var(--accent)] rounded-full transition-all"
                  style={{ width: `${progressPct}%` }}
                />
              </div>
            </div>

            <div className="text-xs text-[var(--muted)] mb-3">
              Programme quotidien (généré chaque jour selon tes faiblesses) :
            </div>
            <ul className="space-y-2">
              {current.items.map((it, i) => (
                <li key={i} className="flex items-start gap-3 text-sm">
                  <span className="text-[10px] uppercase px-1.5 py-0.5 rounded bg-[var(--surface-2)] text-[var(--muted)] shrink-0 mt-0.5">
                    {kindLabel(it.kind)}
                  </span>
                  <div className="flex-1 min-w-0">
                    <div>{it.title}</div>
                    <div className="text-xs text-[var(--muted)] mt-0.5">{it.rationale}</div>
                  </div>
                  <div className="text-xs text-[var(--muted)] tabular-nums shrink-0">≈ {it.minutes} min</div>
                </li>
              ))}
            </ul>
          </Card>
        );
      })()}

      {/* All phases */}
      <div>
        <div className="text-xs uppercase tracking-widest text-[var(--muted)] mb-3">Les 5 phases</div>
        <div className="space-y-3">
          {data.phases.map((p) => (
            <PhaseCard key={p.letter} phase={p} />
          ))}
        </div>
      </div>

      <div className="text-xs text-[var(--muted)] italic">
        <TrendingUp className="size-3 inline mr-1" />
        Tu changes automatiquement de phase dès que ton rating Rapid franchit le seuil correspondant.
        Le plan du jour s'adapte aussi à tes faiblesses détectées chaque nuit.
      </div>
    </div>
  );
}

function PhaseCard({ phase }: { phase: RoadmapPhase }) {
  const Icon = phase.state === "done" ? CheckCircle2 : phase.state === "current" ? TrendingUp : Lock;
  return (
    <Card className={cn(
      phase.state === "current" && "border-l-4 border-l-[var(--accent)]",
      phase.state === "done" && "opacity-60",
    )}>
      <details>
        <summary className="cursor-pointer flex items-center gap-3 list-none">
          <Icon className={cn(
            "size-4 shrink-0",
            phase.state === "done" && "text-[var(--accent)]",
            phase.state === "current" && "text-[var(--accent)]",
            phase.state === "upcoming" && "text-[var(--muted)]",
          )} />
          <div className="flex-1 min-w-0">
            <div className="text-sm font-medium">{phase.label}</div>
            <div className="text-xs text-[var(--muted)] tabular-nums font-mono">
              {phase.floor === 0 ? "<" : `${phase.floor} →`} {phase.ceiling >= 3000 ? "∞" : phase.ceiling} ELO
            </div>
          </div>
          <span className={cn(
            "text-[10px] uppercase tracking-wider px-2 py-1 rounded shrink-0",
            phase.state === "done" && "bg-[var(--accent)]/20 text-[var(--accent)]",
            phase.state === "current" && "bg-[var(--accent)] text-black",
            phase.state === "upcoming" && "bg-[var(--surface-2)] text-[var(--muted)]",
          )}>
            {phase.state === "done" ? "Validée" : phase.state === "current" ? "En cours" : "À venir"}
          </span>
        </summary>

        <ul className="mt-4 space-y-2 pl-7">
          {phase.items.map((it, i) => (
            <li key={i} className="flex items-start gap-3 text-sm">
              <span className="text-[10px] uppercase px-1.5 py-0.5 rounded bg-[var(--surface-2)] text-[var(--muted)] shrink-0 mt-0.5">
                {kindLabel(it.kind)}
              </span>
              <div className="flex-1 min-w-0">
                <div>{it.title}</div>
                <div className="text-xs text-[var(--muted)] mt-0.5">{it.rationale}</div>
              </div>
              <div className="text-xs text-[var(--muted)] tabular-nums shrink-0">≈ {it.minutes} min</div>
            </li>
          ))}
        </ul>
      </details>
    </Card>
  );
}

function Stat({ label, value, tone, mono }: { label: string; value: string | number; tone?: string; mono?: boolean }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wider text-[var(--muted)]">{label}</div>
      <div className={cn("text-2xl font-semibold mt-1", mono && "tabular-nums font-mono", tone)}>
        {value}
      </div>
    </div>
  );
}

function formatEta(days: number): string {
  if (days < 60) return `${days} j`;
  const months = Math.round(days / 30);
  if (months < 18) return `≈ ${months} mois`;
  const years = (days / 365).toFixed(1);
  return `≈ ${years} an${parseFloat(years) > 1 ? "s" : ""}`;
}
