"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Board } from "@/components/chess/Board";
import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import { JobButton } from "@/components/admin/JobButton";
import { SyncJobButton } from "@/components/admin/SyncJobButton";
import { cn } from "@/lib/utils";

type Line = {
  id: number;
  fen: string;
  my_move_san: string | null;
  my_move_uci: string | null;
  label: string | null;
  notes: string | null;
};
type TopLinesResp = { player: string; color: string; lines: Line[] };

type GMMove = { uci?: string; san?: string; games?: number; share?: number; score_white?: number };
type GMNode = {
  id: number;
  color: string;
  fen: string;
  my_move: string | null;
  my_move_san?: string | null;
  my_move_share_in_gm: number | null;
  my_move_score_in_gm: number | null;
  gm_total_games: number | null;
  gm_moves: GMMove[];
  notes?: string | null;
};
type WithGMResp = { count: number; nodes: GMNode[] };

export default function RepertoireLinesPage() {
  const [color, setColor] = useState<"white" | "black">("white");
  const [tab, setTab] = useState<"top" | "gm">("top");
  const [selected, setSelected] = useState<Line | GMNode | null>(null);

  const top = useQuery<TopLinesResp>({
    queryKey: ["rep-top", color],
    queryFn: () => api<TopLinesResp>("/repertoire/me/top-lines", { query: { color, limit: 60 } }),
    enabled: tab === "top",
  });

  const gm = useQuery<WithGMResp>({
    queryKey: ["rep-gm"],
    queryFn: () => api<WithGMResp>("/repertoire/me/with_gm", { query: { limit: 60 } }),
    enabled: tab === "gm",
  });

  const sel = selected;

  return (
    <div className="px-4 py-6 md:px-8 md:py-8 max-w-7xl">
      <header className="mb-6 flex items-end justify-between">
        <div>
          <div className="text-xs uppercase tracking-widest text-[var(--muted)]">Outils</div>
          <h1 className="text-3xl font-semibold mt-1">Répertoire — Lignes</h1>
        </div>
        <div className="flex gap-1">
          {(["top", "gm"] as const).map((t) => (
            <button key={t} onClick={() => { setTab(t); setSelected(null); }}
              className={cn("text-xs px-3 py-1.5 rounded border",
                tab === t ? "bg-[var(--accent)] text-black border-[var(--accent)]" : "bg-[var(--surface-2)] text-[var(--muted)]")}>
              {t === "top" ? "Mes top-lines" : "Annoté GM"}
            </button>
          ))}
        </div>
      </header>

      <details className="text-xs mb-4">
        <summary className="text-[var(--muted)] cursor-pointer hover:text-[var(--foreground)]">Actions</summary>
        <div className="mt-2 max-w-md">
          <Card>
            <JobButton
              label="Reconstruire le répertoire (async)"
              description="Repart de toutes mes parties pour rebuilder l'arbre."
              path="/async/repertoire/me/rebuild"
            />
            <SyncJobButton
              label="Annoter avec données GM"
              description="Enrichit chaque ligne avec les stats des parties GM via Lichess explorer. Requiert LICHESS_TOKEN si rate-limit."
              path="/repertoire/me/annotate"
              query={{ limit: 50 }}
            />
            <SyncJobButton
              label="Recalculer out-of-book sur toutes mes parties"
              description="Recompute du ply où je quitte la théorie pour chaque partie."
              path="/repertoire/me/recompute_out_of_book"
            />
          </Card>
        </div>
      </details>

      {tab === "top" && (
        <div className="mb-4 flex gap-1.5">
          {(["white", "black"] as const).map((c) => (
            <button key={c} onClick={() => setColor(c)}
              className={cn("text-xs px-3 py-1.5 rounded border",
                color === c ? "bg-[var(--accent)] text-black border-[var(--accent)]" : "bg-[var(--surface-2)] text-[var(--muted)]")}>
              {c === "white" ? "Blancs" : "Noirs"}
            </button>
          ))}
        </div>
      )}

      <div className="grid lg:grid-cols-[1fr_auto] gap-8">
        <Card className="p-0 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="text-xs text-[var(--muted)] uppercase tracking-wider">
              <tr className="border-b border-[var(--border)]">
                <th className="text-left px-4 py-2">Position</th>
                <th className="text-left px-2 py-2">Mon coup</th>
                {tab === "gm" && <><th className="text-right px-2 py-2">Part GM</th><th className="text-right px-2 py-2">Score GM</th><th className="text-right px-4 py-2">Parties GM</th></>}
              </tr>
            </thead>
            <tbody>
              {tab === "top" && top.data?.lines.map((l) => (
                <tr key={l.id} onClick={() => setSelected(l)}
                  className={cn("border-b border-[var(--border)] last:border-0 cursor-pointer hover:bg-[var(--surface-2)]/40",
                    (sel as Line)?.id === l.id && "bg-[var(--surface-2)]")}>
                  <td className="px-4 py-2 truncate max-w-[420px]">{l.label ?? "—"}</td>
                  <td className="px-2 py-2 font-mono">{l.my_move_san ?? "—"}</td>
                </tr>
              ))}
              {tab === "gm" && gm.data?.nodes.map((n) => (
                <tr key={n.id} onClick={() => setSelected(n)}
                  className={cn("border-b border-[var(--border)] last:border-0 cursor-pointer hover:bg-[var(--surface-2)]/40",
                    (sel as GMNode)?.id === n.id && "bg-[var(--surface-2)]")}>
                  <td className="px-4 py-2 font-mono text-xs truncate max-w-[420px]">{n.fen}</td>
                  <td className="px-2 py-2 font-mono">{n.my_move ?? "—"}</td>
                  <td className="px-2 py-2 text-right tabular-nums text-[var(--muted)]">{n.my_move_share_in_gm != null ? `${Math.round(n.my_move_share_in_gm * 100)}%` : "—"}</td>
                  <td className="px-2 py-2 text-right tabular-nums">{n.my_move_score_in_gm != null ? `${Math.round(n.my_move_score_in_gm * 100)}%` : "—"}</td>
                  <td className="px-4 py-2 text-right tabular-nums text-[var(--muted)]">{n.gm_total_games ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>

        <div>
          {sel ? (
            <DetailPane sel={sel} tab={tab} fallbackColor={color} />
          ) : (
            <div className="w-[360px] h-[360px] rounded border bg-[var(--surface)] flex items-center justify-center text-sm text-[var(--muted)] text-center px-6">
              Clique sur une ligne pour voir la position + ce que tu joues d&apos;habitude vs ce que la théorie GM recommande.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function DetailPane({
  sel,
  tab,
  fallbackColor,
}: {
  sel: Line | GMNode;
  tab: "top" | "gm";
  fallbackColor: "white" | "black";
}) {
  const isGM = "gm_moves" in sel;
  const orientation = tab === "top"
    ? fallbackColor
    : ((sel as GMNode).color?.includes("BLACK") ? "black" : "white");

  // What the user habitually plays in this position
  const myMoveSan = isGM
    ? ((sel as GMNode).my_move_san ?? (sel as GMNode).my_move ?? null)
    : ((sel as Line).my_move_san ?? null);

  return (
    <div className="space-y-3 w-[420px] max-w-full">
      <Board fen={sel.fen} orientation={orientation} allowDragging={false} size={360} />

      {/* Ce que je joue d'habitude */}
      <Card>
        <div className="text-xs uppercase tracking-widest text-[var(--muted)]">Ton habitude dans cette position</div>
        {myMoveSan ? (
          <div className="text-lg font-mono mt-1">{myMoveSan}</div>
        ) : (
          <div className="text-sm text-[var(--muted)] mt-1 italic">Aucun coup enregistré ici.</div>
        )}
        {"label" in sel && sel.label && (
          <div className="text-xs text-[var(--muted)] mt-1">{sel.label}</div>
        )}
      </Card>

      {/* Comparaison avec la théorie GM (uniquement si annoté) */}
      {isGM ? (
        <GMComparisonCard node={sel as GMNode} />
      ) : (
        <Card className="border-[var(--muted)]/30">
          <div className="text-xs text-[var(--muted)]">
            Pas de données GM ici. Bascule sur l&apos;onglet <b>Annoté GM</b> pour voir ce que les maîtres jouent dans tes positions, ou lance « Annoter avec données GM » dans Actions.
          </div>
        </Card>
      )}

      {sel.notes && (
        <Card>
          <div className="text-xs uppercase tracking-widest text-[var(--muted)] mb-1">Notes</div>
          <pre className="text-xs whitespace-pre-wrap font-mono text-[var(--muted)]">{sel.notes}</pre>
        </Card>
      )}
    </div>
  );
}

function GMComparisonCard({ node }: { node: GMNode }) {
  const myShare = node.my_move_share_in_gm;
  const myScore = node.my_move_score_in_gm;
  const totalGames = node.gm_total_games ?? 0;
  const myMove = node.my_move_san ?? node.my_move;
  const topGM = (node.gm_moves || [])[0];
  const otherGMs = (node.gm_moves || []).filter((m) => m.san !== myMove).slice(0, 4);

  // Verdict
  let verdict = "";
  let tone: "good" | "ok" | "bad" | "unknown" = "unknown";
  if (totalGames < 50) {
    verdict = `Position rare chez les GM (${totalGames} parties).`;
    tone = "ok";
  } else if (myShare == null) {
    verdict = "Ton coup n'apparaît pas dans la base GM — tu joues hors-théorie.";
    tone = "bad";
  } else if (myShare >= 0.30) {
    verdict = `Tu joues comme la majorité des GM (${Math.round(myShare * 100)}% de leurs parties).`;
    tone = "good";
  } else if (myShare >= 0.05) {
    verdict = `Coup minoritaire chez les GM (${Math.round(myShare * 100)}%). Acceptable mais pas mainline.`;
    tone = "ok";
  } else {
    verdict = `Coup très rare chez les GM (${Math.round(myShare * 100)}%) — probablement sous-optimal.`;
    tone = "bad";
  }

  return (
    <Card className={cn(
      tone === "good" && "border-l-4 border-l-[var(--accent)]",
      tone === "bad" && "border-l-4 border-l-[var(--danger)]",
      tone === "ok" && "border-l-4 border-l-[var(--warning)]",
    )}>
      <div className="text-xs uppercase tracking-widest text-[var(--muted)]">Verdict vs théorie GM</div>
      <div className={cn(
        "text-sm mt-1 font-medium",
        tone === "good" && "text-[var(--accent)]",
        tone === "bad" && "text-[var(--danger)]",
        tone === "ok" && "text-[var(--warning)]",
      )}>{verdict}</div>

      <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
        <div className="rounded border bg-[var(--surface-2)] p-2">
          <div className="text-[var(--muted)] uppercase tracking-wider">Ton coup</div>
          <div className="font-mono text-sm mt-1">{myMove ?? "—"}</div>
          {myShare != null && (
            <div className="text-[var(--muted)] tabular-nums mt-1">{Math.round(myShare * 100)}% des GM</div>
          )}
          {myScore != null && (
            <div className="text-[var(--muted)] tabular-nums">winrate {Math.round(myScore * 100)}%</div>
          )}
        </div>
        <div className="rounded border bg-[var(--surface-2)] p-2">
          <div className="text-[var(--muted)] uppercase tracking-wider">Top GM</div>
          <div className="font-mono text-sm mt-1">{topGM?.san ?? "—"}</div>
          {topGM?.share != null && (
            <div className="text-[var(--muted)] tabular-nums mt-1">{Math.round(topGM.share * 100)}% des GM</div>
          )}
          {topGM?.score_white != null && (
            <div className="text-[var(--muted)] tabular-nums">score blanc {Math.round(topGM.score_white * 100)}%</div>
          )}
        </div>
      </div>

      {otherGMs.length > 0 && (
        <div className="mt-3">
          <div className="text-xs text-[var(--muted)] uppercase tracking-wider mb-1">Autres coups GM</div>
          <div className="text-xs space-y-0.5">
            {otherGMs.map((m, i) => (
              <div key={i} className="flex justify-between font-mono">
                <span>{m.san}</span>
                <span className="text-[var(--muted)] tabular-nums">
                  {m.share != null ? `${Math.round(m.share * 100)}%` : "—"}
                  {m.games != null && ` · ${m.games}p`}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="mt-3 text-xs text-[var(--muted)] tabular-nums">
        Base : {totalGames} parties GM
      </div>
    </Card>
  );
}
