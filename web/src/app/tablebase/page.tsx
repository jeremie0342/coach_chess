"use client";

import { useState } from "react";
import Link from "next/link";
import { Swords } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { Chess } from "chess.js";
import { api } from "@/lib/api";
import { Board } from "@/components/chess/Board";
import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import { FenInput } from "@/components/chess/FenInput";
import { cn } from "@/lib/utils";

type ProbeResp = {
  fen: string;
  pieces: number;
  wdl: number | null;
  dtz: number | null;
  verdict: string | null;
  source: string | null;
  has_local_tables: boolean;
};

const EXAMPLE = "4k3/8/8/8/8/8/4K3/4R3 w - - 0 1";

export default function TablebasePage() {
  const [fen, setFen] = useState(EXAMPLE);

  const q = useQuery<ProbeResp>({
    queryKey: ["tb", fen],
    queryFn: () => api<ProbeResp>("/tablebase/probe", { query: { fen } }),
    enabled: !!fen,
    retry: false,
  });

  const status = useQuery<{ has_local_tables: boolean }>({
    queryKey: ["tb-status"],
    queryFn: () => api("/tablebase/status"),
  });

  const sideToMove: "white" | "black" = (() => {
    try { return new Chess(fen).turn() === "w" ? "white" : "black"; } catch { return "white"; }
  })();

  return (
    <div className="px-4 py-6 md:px-8 md:py-8 max-w-5xl">
      <header className="mb-6">
        <div className="text-xs uppercase tracking-widest text-[var(--muted)]">Outils</div>
        <h1 className="text-3xl font-semibold mt-1">Tablebase</h1>
        <p className="text-sm text-[var(--muted)] mt-2">Sonde de finale (≤ 7 pièces) via Lichess.</p>
        <div className="text-xs text-[var(--muted)] mt-1">
          Tables locales : <span className={status.data?.has_local_tables ? "text-[var(--accent)]" : "text-[var(--warning)]"}>
            {status.data?.has_local_tables ? "disponibles" : "non installées (fallback API Lichess)"}
          </span>
        </div>
      </header>

      <div className="grid lg:grid-cols-[auto_1fr] gap-8">
        <Board fen={fen} orientation={sideToMove} allowDragging={false} size={420} />

        <div className="space-y-4 min-w-0">
          <Card>
            <FenInput value={fen} onChange={setFen} />
          </Card>

          {q.isError && (
            <Card className="border-[var(--danger)]/40 text-sm text-[var(--danger)]">{String(q.error)}</Card>
          )}

          {q.data && (
            <Card>
              <CardHeader>
                <CardTitle>Résultat</CardTitle>
                <span className="text-xs text-[var(--muted)] font-mono">{q.data.pieces} pièces</span>
              </CardHeader>
              {q.data.wdl == null ? (
                <div className="text-sm text-[var(--muted)]">Position non couverte par les tablebases (plus de 7 pièces ?).</div>
              ) : (
                <div className="space-y-4">
                  <div className="flex items-baseline gap-3">
                    <div className={cn("text-4xl font-bold tabular-nums", wdlColor(q.data.wdl))}>
                      {wdlLabel(q.data.wdl)}
                    </div>
                    <div className="text-sm text-[var(--muted)]">{q.data.verdict ?? ""}</div>
                  </div>
                  <div className="grid grid-cols-3 gap-3 text-sm">
                    <Stat label="WDL" value={String(q.data.wdl)} />
                    <Stat label="DTZ" value={q.data.dtz?.toString() ?? "—"} />
                    <Stat label="Source" value={q.data.source ?? "—"} />
                  </div>
                  <div className="text-xs text-[var(--muted)]">
                    Tables locales : {q.data.has_local_tables ? "oui" : "non"}
                  </div>
                </div>
              )}
            </Card>
          )}

          {q.data && q.data.wdl != null && (
            <Card className="border-l-4 border-l-[var(--accent)]">
              <div className="text-xs uppercase tracking-widest text-[var(--muted)]">Drill cette finale</div>
              <div className="text-sm mt-1 mb-3">
                La tablebase te donne juste le verdict mathématique. Pour la jouer réellement, lance une partie contre Stockfish à partir de cette position — utile pour t&apos;entraîner aux finales théoriques élémentaires (KRK, KQK, KPvK…).
              </div>
              <div className="flex gap-2 flex-wrap">
                <Link
                  href={`/play?fen=${encodeURIComponent(fen)}&title=${encodeURIComponent("Drill finale " + (q.data.verdict ?? ""))}`}
                  className="px-3 py-2 rounded bg-[var(--accent)] text-black font-medium text-sm inline-flex items-center gap-1.5"
                >
                  <Swords className="size-3.5" /> Jouer cette position vs Stockfish
                </Link>
              </div>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded border bg-[var(--surface-2)] p-3">
      <div className="text-[10px] uppercase tracking-wider text-[var(--muted)]">{label}</div>
      <div className="text-lg font-mono tabular-nums mt-1">{value}</div>
    </div>
  );
}

function wdlLabel(wdl: number) {
  if (wdl >= 2) return "Gagne";
  if (wdl === 1) return "Cursed win";
  if (wdl === 0) return "Nulle";
  if (wdl === -1) return "Blessed loss";
  return "Perd";
}

function wdlColor(wdl: number) {
  if (wdl >= 2) return "text-[var(--accent)]";
  if (wdl <= -2) return "text-[var(--danger)]";
  if (wdl === 0) return "text-[var(--muted)]";
  return "text-[var(--warning)]";
}
