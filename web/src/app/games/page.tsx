"use client";

import { useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import { JobButton } from "@/components/admin/JobButton";
import { cn } from "@/lib/utils";
import type { GamesListResponse } from "@/types/games";

type Filters = {
  color?: "white" | "black";
  result?: "win" | "loss" | "draw";
  time_class?: string;
  scope?: "mine" | "opponents" | "all";
  q?: string;
};

const PAGE = 50;

export default function GamesListPage() {
  const [filters, setFilters] = useState<Filters>({ scope: "mine" });
  const [searchInput, setSearchInput] = useState("");
  const [page, setPage] = useState(0);

  const q = useQuery<GamesListResponse>({
    queryKey: ["games", filters, page],
    queryFn: () =>
      api<GamesListResponse>("/games", {
        query: { ...filters, limit: PAGE, offset: page * PAGE },
      }),
  });

  return (
    <div className="px-4 py-6 md:px-8 md:py-8 max-w-7xl">
      <header className="mb-6 flex items-end justify-between">
        <div>
          <div className="text-xs uppercase tracking-widest text-[var(--muted)]">Analyse</div>
          <h1 className="text-3xl font-semibold mt-1">Mes parties</h1>
        </div>
        {q.data && (
          <div className="text-xs text-[var(--muted)] tabular-nums">
            <b className="text-[var(--foreground)]">{q.data.total}</b> parties
          </div>
        )}
      </header>

      <details className="text-xs mb-4">
        <summary className="text-[var(--muted)] cursor-pointer hover:text-[var(--foreground)]">Actions Stockfish</summary>
        <div className="mt-2 max-w-md">
          <Card>
            <JobButton
              label="Analyser parties en attente"
              description="Lance Stockfish sur les 100 prochaines parties non analysées."
              path="/async/analyze/pending"
              body={{ limit: 100 }}
            />
            <JobButton
              label="Re-analyse profonde des blunders"
              description="Depth 28 sur les positions critiques (limite 50)."
              path="/async/analyze/deep/critical"
              body={{ limit: 50, depth: 28, min_cp_loss: 150 }}
            />
          </Card>
        </div>
      </details>

      {/* Search bar */}
      <Card className="mb-4">
        <div className="flex flex-col md:flex-row gap-3 items-stretch md:items-center">
          <div className="flex-1 flex gap-2">
            <input
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  setFilters((f) => ({ ...f, q: searchInput.trim() || undefined }));
                  setPage(0);
                }
              }}
              placeholder="Rechercher : adversaire, ouverture, ECO ou ID de partie…"
              className="flex-1 bg-[var(--surface-2)] border rounded px-3 py-2 text-sm"
            />
            <button
              onClick={() => { setFilters((f) => ({ ...f, q: searchInput.trim() || undefined })); setPage(0); }}
              className="text-xs px-3 py-2 rounded bg-[var(--accent)] text-black font-medium"
            >
              Rechercher
            </button>
            {filters.q && (
              <button
                onClick={() => { setSearchInput(""); setFilters((f) => ({ ...f, q: undefined })); setPage(0); }}
                className="text-xs px-3 py-2 rounded border bg-[var(--surface-2)] text-[var(--muted)]"
              >
                ×
              </button>
            )}
          </div>
          <FilterGroup label="Périmètre">
            {(["mine", "opponents", "all"] as const).map((s) => (
              <Chip key={s} active={filters.scope === s} onClick={() => { setFilters((f) => ({ ...f, scope: s })); setPage(0); }}>
                {s === "mine" ? "mes parties" : s === "opponents" ? "adversaires" : "toutes"}
              </Chip>
            ))}
          </FilterGroup>
        </div>
      </Card>

      <Card className="mb-4">
        <div className="flex flex-wrap gap-4 text-sm">
          <FilterGroup label="Couleur">
            <Chip active={!filters.color} onClick={() => setFilters((f) => ({ ...f, color: undefined }))}>toutes</Chip>
            <Chip active={filters.color === "white"} onClick={() => setFilters((f) => ({ ...f, color: "white" }))}>blancs</Chip>
            <Chip active={filters.color === "black"} onClick={() => setFilters((f) => ({ ...f, color: "black" }))}>noirs</Chip>
          </FilterGroup>
          <FilterGroup label="Résultat">
            <Chip active={!filters.result} onClick={() => setFilters((f) => ({ ...f, result: undefined }))}>tous</Chip>
            <Chip active={filters.result === "win"} onClick={() => setFilters((f) => ({ ...f, result: "win" }))}>victoires</Chip>
            <Chip active={filters.result === "draw"} onClick={() => setFilters((f) => ({ ...f, result: "draw" }))}>nulles</Chip>
            <Chip active={filters.result === "loss"} onClick={() => setFilters((f) => ({ ...f, result: "loss" }))}>défaites</Chip>
          </FilterGroup>
          <FilterGroup label="Cadence">
            {["rapid", "blitz", "bullet", "daily"].map((tc) => (
              <Chip key={tc} active={filters.time_class === tc} onClick={() => setFilters((f) => ({ ...f, time_class: f.time_class === tc ? undefined : tc }))}>
                {tc}
              </Chip>
            ))}
          </FilterGroup>
        </div>
      </Card>

      <Card className="p-0 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="text-xs text-[var(--muted)] uppercase tracking-wider">
            <tr className="border-b border-[var(--border)]">
              <th className="text-left px-4 py-3 w-8"></th>
              <th className="text-left px-2 py-3">Date</th>
              <th className="text-left px-2 py-3">Couleur</th>
              <th className="text-left px-2 py-3">Adversaire</th>
              <th className="text-left px-2 py-3">Ouverture</th>
              <th className="text-right px-2 py-3">Rating</th>
              <th className="text-right px-2 py-3">Plis</th>
              <th className="text-right px-2 py-3">Analyse</th>
              <th className="text-right px-4 py-3"></th>
            </tr>
          </thead>
          <tbody>
            {q.isLoading && (
              <tr><td colSpan={9} className="text-center py-8 text-[var(--muted)]">Chargement…</td></tr>
            )}
            {q.data?.items.map((g) => (
              <tr key={g.id} className="border-b border-[var(--border)] last:border-0 hover:bg-[var(--surface-2)]/40">
                <td className="px-4 py-2">
                  <span className={cn("inline-block size-2 rounded-full",
                    g.result === "win" ? "bg-[var(--accent)]" : g.result === "loss" ? "bg-[var(--danger)]" : "bg-[var(--muted)]")} />
                </td>
                <td className="px-2 py-2 text-[var(--muted)] tabular-nums font-mono text-xs">
                  {g.played_at ? new Date(g.played_at).toLocaleDateString("fr-FR") : "—"}
                </td>
                <td className="px-2 py-2 text-xs uppercase text-[var(--muted)]">{g.color}</td>
                <td className="px-2 py-2 truncate max-w-[160px]">
                  <div>{g.opp_username ?? "—"}</div>
                  <div className="text-xs text-[var(--muted)] tabular-nums">{g.opp_rating ?? ""}</div>
                </td>
                <td className="px-2 py-2 truncate max-w-[240px]">
                  <div className="truncate">{g.opening ?? "—"}</div>
                  <div className="text-xs text-[var(--muted)] font-mono">{g.eco ?? ""}</div>
                </td>
                <td className="px-2 py-2 text-right tabular-nums">{g.my_rating ?? "—"}</td>
                <td className="px-2 py-2 text-right text-xs text-[var(--muted)] tabular-nums">{g.ply_count}</td>
                <td className="px-2 py-2 text-right">
                  <span className={cn("text-[10px] px-1.5 py-0.5 rounded",
                    g.analysis_status === "done" ? "bg-[var(--accent)]/20 text-[var(--accent)]" : "bg-[var(--surface-2)] text-[var(--muted)]")}>
                    {g.analysis_status}
                  </span>
                </td>
                <td className="px-4 py-2 text-right whitespace-nowrap">
                  <Link href={`/games/${g.id}`} className="text-xs text-[var(--info)] hover:underline mr-3">Review</Link>
                  <Link
                    href={`/play?fen=${encodeURIComponent("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1")}&game_id=${g.id}&ply=0&title=${encodeURIComponent(`Rejouer game #${g.id}`)}`}
                    className="text-xs text-[var(--accent)] hover:underline"
                    title="Lancer une partie contre Stockfish à partir de cette position"
                  >Rejouer</Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      {q.data && q.data.total > PAGE && (
        <div className="mt-4 flex items-center justify-between text-sm">
          <button disabled={page === 0} onClick={() => setPage((p) => Math.max(0, p - 1))}
            className="text-xs px-3 py-1.5 rounded border bg-[var(--surface-2)] disabled:opacity-30">← Préc.</button>
          <span className="text-xs text-[var(--muted)] tabular-nums">
            {page * PAGE + 1}–{Math.min((page + 1) * PAGE, q.data.total)} / {q.data.total}
          </span>
          <button disabled={(page + 1) * PAGE >= q.data.total} onClick={() => setPage((p) => p + 1)}
            className="text-xs px-3 py-1.5 rounded border bg-[var(--surface-2)] disabled:opacity-30">Suiv. →</button>
        </div>
      )}
    </div>
  );
}

function FilterGroup({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-xs text-[var(--muted)] uppercase tracking-wider">{label}</span>
      <div className="flex gap-1">{children}</div>
    </div>
  );
}

function Chip({ children, active, onClick }: { children: React.ReactNode; active?: boolean; onClick?: () => void }) {
  return (
    <button onClick={onClick} className={cn(
      "text-xs px-2 py-1 rounded border",
      active ? "bg-[var(--accent)] text-black border-[var(--accent)]" : "bg-[var(--surface-2)] text-[var(--muted)] hover:text-[var(--foreground)]",
    )}>{children}</button>
  );
}
