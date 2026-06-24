"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Chess } from "chess.js";
import { Undo2 } from "lucide-react";
import { api } from "@/lib/api";
import { Board } from "@/components/chess/Board";
import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import { FenInput } from "@/components/chess/FenInput";
import { cn } from "@/lib/utils";

const START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";

type ExplorerMove = {
  uci: string;
  san: string;
  games: number;
  share: number;
  score_white: number;
  avg_rating: number | null;
};
type ExplorerResp = {
  db: string;
  fen_epd: string;
  total_games: number;
  white: number;
  draws: number;
  black: number;
  moves: ExplorerMove[];
};

export default function ExplorerPage() {
  const [fen, setFen] = useState(START);
  const [db, setDb] = useState<"masters" | "lichess">("masters");

  const q = useQuery<ExplorerResp>({
    queryKey: ["explorer", fen, db],
    queryFn: () => api<ExplorerResp>("/openings/explorer", { query: { fen, db } }),
    enabled: !!fen,
  });

  const match = useQuery<{ matched: boolean; name?: string; eco?: string; moves_san?: string }>({
    queryKey: ["opening-match", fen],
    queryFn: () => api("/openings/match", { query: { fen } }),
    enabled: !!fen,
  });

  const sideToMove: "white" | "black" = (() => {
    try { return new Chess(fen).turn() === "w" ? "white" : "black"; } catch { return "white"; }
  })();

  const applyMove = (uci: string) => {
    try {
      const c = new Chess(fen);
      const from = uci.slice(0, 2);
      const to = uci.slice(2, 4);
      const promo = uci.length > 4 ? uci[4] : undefined;
      c.move({ from, to, promotion: promo });
      setFen(c.fen());
    } catch {}
  };

  // Board click/drag handler — apply legal move and advance the explorer.
  const handleBoardMove = ({ from, to, promotion }: { from: string; to: string; promotion?: string }): boolean => {
    try {
      const c = new Chess(fen);
      const mv = c.move({ from, to, promotion: promotion ?? "q" });
      if (!mv) return false;
      setFen(c.fen());
      return true;
    } catch {
      return false;
    }
  };

  const undoLastPly = () => {
    try {
      const c = new Chess(fen);
      const hist = c.history();
      if (hist.length === 0) return;
      c.undo();
      setFen(c.fen());
    } catch {}
  };

  return (
    <div className="px-4 py-6 md:px-8 md:py-8 max-w-7xl">
      <header className="mb-6">
        <div className="text-xs uppercase tracking-widest text-[var(--muted)]">Outils</div>
        <h1 className="text-3xl font-semibold mt-1">Opening explorer</h1>
        <p className="text-sm text-[var(--muted)] mt-2">Lichess masters (2000+) ou online players. Source : Lichess API.</p>
      </header>

      <div className="grid lg:grid-cols-[auto_1fr] gap-8">
        <div>
          <Board
            fen={fen}
            orientation={sideToMove}
            draggableColor={sideToMove}
            onMove={handleBoardMove}
            size={420}
          />
          <div className="mt-3 flex items-center justify-between gap-3">
            <div className="text-xs text-[var(--muted)] font-mono">
              {sideToMove === "white" ? "Trait aux blancs" : "Trait aux noirs"}
            </div>
            <div className="flex gap-2">
              <button onClick={undoLastPly} className="text-xs px-2 py-1 rounded border bg-[var(--surface-2)] hover:bg-[var(--surface)] inline-flex items-center gap-1">
                <Undo2 className="size-3" /> Annuler
              </button>
              <button onClick={() => setFen(START)} className="text-xs px-2 py-1 rounded border bg-[var(--surface-2)] hover:bg-[var(--surface)]">
                Reset
              </button>
            </div>
          </div>
          {match.data?.matched && (
            <div className="mt-3 text-sm">
              <span className="text-[var(--accent)] font-medium">{match.data.name}</span>{" "}
              <span className="text-xs text-[var(--muted)] font-mono">{match.data.eco}</span>
              {match.data.moves_san && (
                <div className="text-xs text-[var(--muted)] font-mono mt-1">
                  {match.data.moves_san}
                </div>
              )}
            </div>
          )}
        </div>

        <div className="space-y-4 min-w-0">
          <Card>
            <FenInput value={fen} onChange={setFen} />
            <div className="mt-3 flex gap-1.5">
              {(["masters", "lichess"] as const).map((d) => (
                <button
                  key={d}
                  onClick={() => setDb(d)}
                  className={cn("text-xs px-3 py-1.5 rounded border",
                    db === d ? "bg-[var(--accent)] text-black border-[var(--accent)]" : "bg-[var(--surface-2)] text-[var(--muted)]")}
                >
                  {d}
                </button>
              ))}
            </div>
          </Card>

          {q.isError && (
            <Card className="border-[var(--danger)]/40 text-sm text-[var(--danger)]">
              {String(q.error)}
            </Card>
          )}

          {q.data && (
            <Card className="p-0 overflow-hidden">
              <div className="px-5 py-3 border-b border-[var(--border)] flex items-baseline justify-between">
                <div className="text-sm">
                  <b className="tabular-nums">{q.data.total_games.toLocaleString("fr-FR")}</b> parties
                </div>
                <ScoreBar w={q.data.white} d={q.data.draws} b={q.data.black} />
              </div>
              <table className="w-full text-sm">
                <thead className="text-xs text-[var(--muted)] uppercase tracking-wider">
                  <tr className="border-b border-[var(--border)]">
                    <th className="text-left px-4 py-2">Coup</th>
                    <th className="text-right px-2 py-2">Parties</th>
                    <th className="text-right px-2 py-2">Part</th>
                    <th className="px-2 py-2">Score (W/D/B)</th>
                    <th className="text-right px-4 py-2">Avg rating</th>
                  </tr>
                </thead>
                <tbody>
                  {q.data.moves.slice(0, 30).map((m) => {
                    const w = Math.round(m.score_white * 100);
                    return (
                      <tr key={m.uci} className="border-b border-[var(--border)] last:border-0 hover:bg-[var(--surface-2)]/40">
                        <td className="px-4 py-2 font-mono">
                          <button onClick={() => applyMove(m.uci)} className="hover:text-[var(--accent)]">{m.san}</button>
                        </td>
                        <td className="px-2 py-2 text-right tabular-nums">{m.games.toLocaleString("fr-FR")}</td>
                        <td className="px-2 py-2 text-right tabular-nums text-[var(--muted)]">{Math.round(m.share * 100)}%</td>
                        <td className="px-2 py-2 w-48">
                          <MiniBar w={w} />
                        </td>
                        <td className="px-4 py-2 text-right tabular-nums text-[var(--muted)]">{m.avg_rating ?? "—"}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}

function ScoreBar({ w, d, b }: { w: number; d: number; b: number }) {
  const total = w + d + b || 1;
  return (
    <div className="flex items-center gap-2 text-xs">
      <div className="flex w-40 h-2 rounded overflow-hidden">
        <div style={{ width: `${(w / total) * 100}%` }} className="bg-white/80" />
        <div style={{ width: `${(d / total) * 100}%` }} className="bg-[var(--muted)]" />
        <div style={{ width: `${(b / total) * 100}%` }} className="bg-black/80" />
      </div>
    </div>
  );
}

function MiniBar({ w }: { w: number }) {
  return (
    <div className="flex h-3 rounded overflow-hidden w-full">
      <div style={{ width: `${w}%` }} className="bg-white/80" />
      <div style={{ width: `${100 - w}%` }} className="bg-black/80" />
    </div>
  );
}
