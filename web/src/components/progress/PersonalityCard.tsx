"use client";

import { Radar, RadarChart, PolarGrid, PolarAngleAxis, ResponsiveContainer } from "recharts";
import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import type { Personality } from "@/types/coach";

const TRAIT_LABELS: Record<string, string> = {
  aggression: "Agressivité",
  tactical_eye: "Œil tactique",
  positional: "Positionnel",
  endgame_skill: "Finales",
  time_management: "Gestion du temps",
};

export function PersonalityCard({ data }: { data: Personality }) {
  const radarData = Object.entries(data.style).map(([k, v]) => ({
    trait: TRAIT_LABELS[k] ?? k,
    value: Math.round(v * 100),
  }));

  return (
    <Card>
      <CardHeader>
        <CardTitle>Style de jeu</CardTitle>
        <span className="text-xs text-[var(--muted)] tabular-nums">{data.moves_used} coups analysés</span>
      </CardHeader>

      <div className="grid grid-cols-[1fr_auto] gap-4 items-center">
        <div className="h-56">
          <ResponsiveContainer>
            <RadarChart data={radarData} outerRadius="75%">
              <PolarGrid stroke="var(--border)" />
              <PolarAngleAxis dataKey="trait" tick={{ fontSize: 10, fill: "var(--muted)" }} />
              <Radar dataKey="value" stroke="var(--accent)" fill="var(--accent)" fillOpacity={0.25} />
            </RadarChart>
          </ResponsiveContainer>
        </div>

        <div className="space-y-3 pr-4">
          <div>
            <div className="text-[10px] uppercase tracking-wider text-[var(--muted)]">Trait dominant</div>
            <div className="text-base font-medium capitalize">
              {TRAIT_LABELS[data.dominant_trait] ?? data.dominant_trait}
            </div>
          </div>
          <div>
            <div className="text-[10px] uppercase tracking-wider text-[var(--muted)]">Plus proche de</div>
            <div className="text-2xl font-semibold text-[var(--accent)]">{data.closest_gm}</div>
            <div className="text-xs text-[var(--muted)] tabular-nums">
              {Math.round(data.closest_gm_similarity * 100)}% de similarité
            </div>
          </div>
          <div className="space-y-1 text-xs">
            {data.all_gm_matches.slice(1, 5).map((m) => (
              <div key={m.gm} className="flex justify-between gap-3">
                <span className="text-[var(--muted)]">{m.gm}</span>
                <span className="font-mono tabular-nums">{Math.round(m.similarity * 100)}%</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {data.notes && (
        <div className="mt-3 text-xs text-[var(--muted)] italic">{data.notes}</div>
      )}
    </Card>
  );
}
