"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Lightbulb, Target, AlertCircle } from "lucide-react";
import { api } from "@/lib/api";
import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import { cn } from "@/lib/utils";
import { weaknessMeta, phaseLabelFr } from "@/lib/weakness-meta";

type Weakness = {
  id: number;
  category: string;
  phase: string | null;
  occurrences: number;
  severity: number;
  details: Record<string, any> | null;
  sample_game_ids: number[];
  updated_at: string;
};

type WeaknessList = { player: string; count: number; weaknesses: Weakness[] };

const PHASES = ["opening", "middlegame", "endgame"];

export default function WeaknessesPage() {
  const qc = useQueryClient();
  const [selected, setSelected] = useState<Weakness | null>(null);

  const q = useQuery<WeaknessList>({
    queryKey: ["weaknesses"],
    queryFn: () => api<WeaknessList>("/player/me/weaknesses"),
  });

  const refresh = useMutation({
    mutationFn: () => api("/player/me/weaknesses/refresh", { method: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["weaknesses"] }),
  });

  // Group by category, with per-phase severity (use the 'theme' from details as
  // the real key for tactical_theme rows so 'missed_fork' etc. don't collapse).
  const grid = useMemo(() => {
    const cats = new Map<string, { rep: Weakness; perPhase: Map<string, Weakness>; max: number }>();
    if (!q.data) return [];
    for (const w of q.data.weaknesses) {
      const key = (w.category === "tactical_theme" && (w.details?.theme as string))
        ? (w.details!.theme as string)
        : w.category;
      const phase = w.phase ?? "—";
      const entry = cats.get(key) ?? { rep: w, perPhase: new Map(), max: 0 };
      entry.perPhase.set(phase, w);
      if (w.severity > entry.max) entry.max = w.severity;
      // Prefer the entry with highest severity as the representative
      if (w.severity >= entry.rep.severity) entry.rep = w;
      cats.set(key, entry);
    }
    return Array.from(cats.entries())
      .sort((a, b) => b[1].max - a[1].max)
      .map(([key, v]) => ({ key, ...v }));
  }, [q.data]);

  return (
    <div className="px-4 py-6 md:px-8 md:py-8 max-w-7xl">
      <header className="mb-6 flex items-end justify-between">
        <div>
          <div className="text-xs uppercase tracking-widest text-[var(--muted)]">Coach</div>
          <h1 className="text-3xl font-semibold mt-1">Faiblesses</h1>
          {q.data && (
            <div className="text-sm text-[var(--muted)] mt-1">
              {grid.length} catégories distinctes détectées sur tes parties
            </div>
          )}
        </div>
        <button
          onClick={() => refresh.mutate()}
          disabled={refresh.isPending}
          className="text-xs px-3 py-1.5 rounded border bg-[var(--surface-2)] hover:bg-[var(--surface)] disabled:opacity-50"
        >
          {refresh.isPending ? "Analyse..." : "Recalculer"}
        </button>
      </header>

      <div className="grid lg:grid-cols-[2fr_1fr] gap-6">
        <Card className="p-0 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="text-xs text-[var(--muted)] uppercase tracking-wider">
              <tr className="border-b border-[var(--border)]">
                <th className="text-left px-4 py-3">Faiblesse</th>
                <th className="text-right px-2 py-3">Occ.</th>
                {PHASES.map((p) => <th key={p} className="text-center px-2 py-3 capitalize w-14">{p.slice(0, 3)}</th>)}
                <th className="text-center px-2 py-3 w-14">Tot.</th>
              </tr>
            </thead>
            <tbody>
              {grid.map(({ key, rep, perPhase }) => {
                const meta = weaknessMeta(rep.category, rep.details);
                const isSelected = selected?.id === rep.id;
                return (
                  <tr
                    key={key}
                    onClick={() => setSelected(rep)}
                    className={cn(
                      "border-b border-[var(--border)] last:border-0 cursor-pointer hover:bg-[var(--surface-2)]/40",
                      isSelected && "bg-[var(--surface-2)]",
                    )}
                  >
                    <td className="px-4 py-2.5">
                      <div className="font-medium">{meta.label}</div>
                      <div className="text-[10px] text-[var(--muted)] font-mono">{key}</div>
                    </td>
                    <td className="px-2 py-2.5 text-right tabular-nums text-[var(--muted)]">
                      {Array.from(perPhase.values()).reduce((acc, w) => acc + w.occurrences, 0)}
                    </td>
                    {PHASES.map((p) => <Cell key={p} w={perPhase.get(p)} />)}
                    <Cell w={perPhase.get("—")} />
                  </tr>
                );
              })}
            </tbody>
          </table>
        </Card>

        <Card>
          {!selected && (
            <>
              <CardHeader><CardTitle>Détail</CardTitle></CardHeader>
              <div className="text-sm text-[var(--muted)]">Clique une ligne pour voir l'explication, l'impact et comment t'améliorer.</div>
            </>
          )}
          {selected && <WeaknessDetail w={selected} />}
        </Card>
      </div>
    </div>
  );
}

function Cell({ w }: { w?: Weakness }) {
  if (!w) return <td className="text-center px-2 py-2 text-[var(--muted)]">·</td>;
  const pct = Math.round(w.severity * 100);
  return (
    <td className="text-center px-2 py-2">
      <div
        className={cn(
          "h-8 rounded font-mono text-xs tabular-nums flex items-center justify-center pointer-events-none",
          severityBg(w.severity),
        )}
        title={`${w.occurrences} occ.`}
      >
        {pct}
      </div>
    </td>
  );
}

function WeaknessDetail({ w }: { w: Weakness }) {
  const meta = weaknessMeta(w.category, w.details);
  const pct = Math.round(w.severity * 100);

  return (
    <div className="space-y-4">
      <div>
        <div className="text-xs uppercase tracking-widest text-[var(--muted)] flex items-center gap-2">
          <span className="font-mono">{w.category}</span>
          <span>·</span>
          <span>{phaseLabelFr(w.phase)}</span>
        </div>
        <h3 className="text-xl font-semibold mt-1">{meta.label}</h3>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <Stat label="Sévérité" value={`${pct}`} tone={severityTone(w.severity)} suffix="/ 100" />
        <Stat label="Occurrences" value={String(w.occurrences)} />
      </div>

      <div className="space-y-3">
        <Section icon={<AlertCircle className="size-3.5" />} label="C'est quoi">
          {meta.what}
        </Section>
        <Section icon={<Lightbulb className="size-3.5" />} label="Pourquoi ça coûte">
          {meta.why}
        </Section>
        <DetailsBlock details={w.details} />
        <Link
          href={meta.fix.href}
          className="flex items-center justify-center gap-2 w-full py-2.5 rounded bg-[var(--accent)] text-black text-sm font-medium hover:opacity-90"
        >
          <Target className="size-4" />
          {meta.fix.label} →
        </Link>
      </div>

      {w.sample_game_ids.length > 0 && (
        <div>
          <div className="text-xs uppercase tracking-widest text-[var(--muted)] mb-2">
            Parties où cette erreur apparaît
          </div>
          <div className="flex flex-wrap gap-1.5">
            {w.sample_game_ids.slice(0, 8).map((id) => (
              <Link
                key={id}
                href={`/games/${id}`}
                className="text-xs px-2 py-1 rounded bg-[var(--surface-2)] hover:bg-[var(--info)]/20 hover:text-[var(--info)] font-mono"
              >
                #{id}
              </Link>
            ))}
          </div>
        </div>
      )}

      {w.details && (
        <details className="text-xs">
          <summary className="text-[var(--muted)] cursor-pointer hover:text-[var(--foreground)]">Données brutes (debug)</summary>
          <pre className="mt-2 bg-[var(--surface-2)] rounded p-2 overflow-auto max-h-48 font-mono text-[10px]">
            {JSON.stringify(w.details, null, 2)}
          </pre>
        </details>
      )}
    </div>
  );
}

function DetailsBlock({ details }: { details: Record<string, any> | null }) {
  if (!details) return null;
  const items: { label: string; value: string }[] = [];

  if (typeof details.rate_per_game === "number") {
    items.push({ label: "Fréquence", value: `${(details.rate_per_game).toFixed(2)} / partie` });
  }
  if (typeof details.games_affected === "number") {
    items.push({ label: "Parties touchées", value: String(details.games_affected) });
  }
  if (typeof details.total_material_dropped === "number") {
    items.push({ label: "Matériel perdu (total)", value: `${details.total_material_dropped} pts` });
  }
  if (typeof details.avg_piece_value_dropped === "number") {
    items.push({ label: "Pièce moyenne perdue", value: `${details.avg_piece_value_dropped.toFixed(1)} pts` });
  }
  if (typeof details.blunders === "number") {
    items.push({ label: "Blunders dans la phase", value: String(details.blunders) });
  }
  if (typeof details.mistakes === "number") {
    items.push({ label: "Mistakes dans la phase", value: String(details.mistakes) });
  }
  if (typeof details.bad_share === "number") {
    items.push({ label: "Part des coups < idéal", value: `${Math.round(details.bad_share * 100)}%` });
  }
  if (typeof details.total_lost_games_in_time_trouble === "number") {
    items.push({ label: "Parties perdues en zeitnot", value: String(details.total_lost_games_in_time_trouble) });
  }
  if (typeof details.clock_threshold_seconds === "number") {
    items.push({ label: "Seuil temps critique", value: `< ${details.clock_threshold_seconds}s` });
  }
  if (typeof details.early_loss_share_of_all_losses === "number") {
    items.push({ label: "Part des défaites précoces", value: `${Math.round(details.early_loss_share_of_all_losses * 100)}%` });
  }
  if (typeof details.early_plies_threshold === "number") {
    items.push({ label: "Seuil 'précoce'", value: `< ${details.early_plies_threshold} plis` });
  }
  if (typeof details.wins === "number" && typeof details.losses === "number") {
    const total = (details.wins ?? 0) + (details.draws ?? 0) + (details.losses ?? 0);
    if (total > 0) {
      const wr = ((details.wins ?? 0) + 0.5 * (details.draws ?? 0)) / total;
      items.push({ label: "W/D/L", value: `${details.wins}/${details.draws ?? 0}/${details.losses}` });
      items.push({ label: "Winrate", value: `${Math.round(wr * 100)}%` });
    }
  }
  if (Array.isArray(details.openings) && details.openings.length > 0) {
    const top = details.openings.slice(0, 3).map((o: any) => o.name ?? o.eco ?? "?").join(", ");
    items.push({ label: "Ouvertures concernées", value: top });
  }

  if (items.length === 0) return null;

  return (
    <div className="rounded border bg-[var(--surface-2)]/50 p-3 space-y-1.5">
      <div className="text-[10px] uppercase tracking-widest text-[var(--muted)] mb-1">Indicateurs</div>
      {items.map((it, i) => (
        <div key={i} className="flex justify-between gap-3 text-xs">
          <span className="text-[var(--muted)]">{it.label}</span>
          <span className="font-mono tabular-nums">{it.value}</span>
        </div>
      ))}
    </div>
  );
}

function Section({ icon, label, children }: { icon: React.ReactNode; label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-widest text-[var(--muted)] mb-1 flex items-center gap-1.5">
        {icon}
        {label}
      </div>
      <div className="text-sm leading-relaxed">{children}</div>
    </div>
  );
}

function Stat({ label, value, tone, suffix }: { label: string; value: string; tone?: string; suffix?: string }) {
  return (
    <div>
      <div className="text-xs uppercase tracking-wider text-[var(--muted)]">{label}</div>
      <div className="flex items-baseline gap-1 mt-1">
        <span className={cn("text-2xl font-semibold tabular-nums", tone)}>{value}</span>
        {suffix && <span className="text-xs text-[var(--muted)]">{suffix}</span>}
      </div>
    </div>
  );
}

function severityTone(s: number) {
  if (s >= 0.7) return "text-[var(--danger)]";
  if (s >= 0.4) return "text-[var(--warning)]";
  return "text-[var(--muted)]";
}

function severityBg(s: number) {
  if (s >= 0.7) return "bg-[var(--danger)]/20 text-[var(--danger)]";
  if (s >= 0.4) return "bg-[var(--warning)]/15 text-[var(--warning)]";
  if (s > 0) return "bg-[var(--info)]/10 text-[var(--info)]";
  return "bg-[var(--surface-2)] text-[var(--muted)]";
}
