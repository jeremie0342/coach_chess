"use client";

import { LineChart, Line, ResponsiveContainer, XAxis, YAxis, ReferenceLine, Tooltip } from "recharts";

export type EvalPoint = { ply: number; cp: number | null; mate: number | null; quality?: string | null };

function clamp(v: number) {
  return Math.max(-800, Math.min(800, v));
}

export function EvalGraph({
  points,
  selectedPly,
  onSelect,
}: {
  points: EvalPoint[];
  selectedPly?: number;
  onSelect?: (ply: number) => void;
}) {
  const data = points.map((p) => ({
    ply: p.ply,
    eval: p.mate != null ? (p.mate > 0 ? 800 : -800) : p.cp != null ? clamp(p.cp) : 0,
    quality: p.quality,
  }));

  return (
    <div className="h-32 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart
          data={data}
          margin={{ top: 5, right: 8, left: 0, bottom: 0 }}
          onClick={(e) => {
            if (e && e.activeLabel != null && onSelect) onSelect(Number(e.activeLabel));
          }}
        >
          <XAxis dataKey="ply" hide />
          <YAxis domain={[-800, 800]} hide />
          <ReferenceLine y={0} stroke="var(--border)" strokeDasharray="2 2" />
          {selectedPly != null && <ReferenceLine x={selectedPly} stroke="var(--info)" />}
          <Tooltip
            contentStyle={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 6, fontSize: 11 }}
            labelStyle={{ color: "var(--muted)" }}
            formatter={(v) => {
              const n = Number(v) || 0;
              return `${n >= 0 ? "+" : ""}${(n / 100).toFixed(2)}`;
            }}
          />
          <Line type="monotone" dataKey="eval" stroke="var(--accent)" strokeWidth={1.5} dot={false} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
