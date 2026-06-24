"use client";

import { useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Chess } from "chess.js";
import { api } from "@/lib/api";
import { Board } from "@/components/chess/Board";
import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import { FenInput } from "@/components/chess/FenInput";
import { cn } from "@/lib/utils";

type Match = {
  game_id: number;
  ply: number;
  fen: string;
  distance: number;
  quality: string | null;
  cp_loss: number | null;
};

type SimResp = { fen: string; matches: Match[] };

const EXAMPLE = "r1bqkb1r/pppp1ppp/2n2n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4";

export default function SimilarPage() {
  const [fen, setFen] = useState(EXAMPLE);
  const [maxDist, setMaxDist] = useState(4);
  const [allPlayers, setAllPlayers] = useState(false);

  const q = useQuery<SimResp>({
    queryKey: ["similar", fen, maxDist, allPlayers],
    queryFn: () => api<SimResp>("/coach/me/similar_positions", {
      query: { fen, max_distance: maxDist, all_players: allPlayers, limit: 30 },
    }),
    enabled: !!fen,
  });

  const orientation: "white" | "black" = (() => {
    try { return new Chess(fen).turn() === "w" ? "white" : "black"; } catch { return "white"; }
  })();

  return (
    <div className="px-4 py-6 md:px-8 md:py-8 max-w-7xl">
      <header className="mb-6">
        <div className="text-xs uppercase tracking-widest text-[var(--muted)]">Outils</div>
        <h1 className="text-3xl font-semibold mt-1">Positions similaires</h1>
        <p className="text-sm text-[var(--muted)] mt-2">Recherche par distance de Hamming sur le squelette de pièces.</p>
      </header>

      <div className="grid lg:grid-cols-[auto_1fr] gap-8">
        <div>
          <Board fen={fen} orientation={orientation} allowDragging={false} size={420} />
          <div className="mt-3 text-xs text-[var(--muted)] font-mono break-all">{fen}</div>
        </div>

        <div className="space-y-4 min-w-0">
          <Card>
            <FenInput value={fen} onChange={setFen} />
            <div className="mt-4 flex items-center gap-6 text-sm">
              <label className="flex items-center gap-2">
                <span className="text-[var(--muted)]">Distance max</span>
                <input type="range" min={0} max={12} value={maxDist} onChange={(e) => setMaxDist(Number(e.target.value))} />
                <span className="font-mono tabular-nums w-6">{maxDist}</span>
              </label>
              <label className="flex items-center gap-2">
                <input type="checkbox" checked={allPlayers} onChange={(e) => setAllPlayers(e.target.checked)} />
                <span>Toutes parties (pas seulement les miennes)</span>
              </label>
            </div>
          </Card>

          {q.data && (
            <Card className="p-0 overflow-hidden">
              <div className="px-5 py-3 border-b border-[var(--border)] text-sm">
                <b>{q.data.matches.length}</b> positions similaires
              </div>
              <table className="w-full text-sm">
                <thead className="text-xs text-[var(--muted)] uppercase tracking-wider">
                  <tr className="border-b border-[var(--border)]">
                    <th className="text-left px-4 py-2">Partie</th>
                    <th className="text-right px-2 py-2">Ply</th>
                    <th className="text-right px-2 py-2">Dist.</th>
                    <th className="text-left px-2 py-2">Qualité</th>
                    <th className="text-right px-4 py-2">cp loss</th>
                  </tr>
                </thead>
                <tbody>
                  {q.data.matches.map((m, i) => (
                    <tr key={i} className="border-b border-[var(--border)] last:border-0 hover:bg-[var(--surface-2)]/40">
                      <td className="px-4 py-2">
                        <Link href={`/games/${m.game_id}`} className="text-[var(--info)] hover:underline">#{m.game_id}</Link>
                      </td>
                      <td className="px-2 py-2 text-right tabular-nums">{m.ply}</td>
                      <td className="px-2 py-2 text-right font-mono tabular-nums">{m.distance}</td>
                      <td className="px-2 py-2">
                        {m.quality && (
                          <span className={cn("text-[10px] uppercase px-1.5 py-0.5 rounded",
                            m.quality.includes("blunder") ? "bg-[var(--danger)]/20 text-[var(--danger)]" :
                            m.quality.includes("mistake") ? "bg-[var(--warning)]/20 text-[var(--warning)]" :
                            "bg-[var(--surface-2)] text-[var(--muted)]")}>
                            {m.quality}
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-2 text-right tabular-nums text-[var(--muted)]">{m.cp_loss ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
