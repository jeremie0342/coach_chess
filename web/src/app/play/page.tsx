"use client";

import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Chess } from "chess.js";
import { api, ApiError } from "@/lib/api";
import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import { Board } from "@/components/chess/Board";
import { PositionEditor } from "@/components/chess/PositionEditor";
import { AlertTriangle } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ConstrainedOpening, PlaySession, StartPlayIn } from "@/types/play";

const START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";

type UndoMode = "0" | "1" | "3" | "999";
const UNDO_LABELS: Record<UndoMode, string> = {
  "0": "Strict (0)",
  "1": "1 annulation",
  "3": "3 annulations",
  "999": "Illimité",
};

export default function PlaySetupPage() {
  const router = useRouter();
  const sp = useSearchParams();
  const urlFen = sp?.get("fen");
  const urlGameId = sp?.get("game_id");
  const urlPly = sp?.get("ply");
  const urlTitle = sp?.get("title");

  const [color, setColor] = useState<"white" | "black">("white");
  const [elo, setElo] = useState<number>(1320);
  const [skill, setSkill] = useState<number>(5);
  const [fen, setFen] = useState<string>(START_FEN);
  const [customPos, setCustomPos] = useState(false);
  const [undoMode, setUndoMode] = useState<UndoMode>("3");
  const [openingKey, setOpeningKey] = useState<string | null>(null);

  const openingsQ = useQuery<{ openings: ConstrainedOpening[] }>({
    queryKey: ["play", "openings"],
    queryFn: () => api<{ openings: ConstrainedOpening[] }>("/train/play/openings"),
    staleTime: 60_000,
  });
  const selectedOpening = openingKey
    ? openingsQ.data?.openings.find((o) => o.key === openingKey)
    : undefined;

  // Selecting an opening overrides the color + position settings (the
  // backend enforces this anyway, but we mirror it in the UI to be honest).
  useEffect(() => {
    if (!selectedOpening) return;
    setColor(selectedOpening.user_color);
    setCustomPos(false);
    setFen(START_FEN);
  }, [selectedOpening]);

  // If the page was opened with ?fen=... (e.g. from Game Review's
  // "Rejouer depuis ici"), pre-fill the form and auto-detect color.
  useEffect(() => {
    if (!urlFen) return;
    setFen(urlFen);
    setCustomPos(true);
    try {
      const c = new Chess(urlFen);
      setColor(c.turn() === "w" ? "white" : "black");
    } catch { /* ignore invalid fen */ }
  }, [urlFen]);

  const start = useMutation({
    mutationFn: (body: StartPlayIn) => api<PlaySession>("/train/play/start", { json: body }),
    onSuccess: (s) => router.push(`/play/${s.id}`),
  });

  return (
    <div className="px-4 py-6 md:px-8 md:py-8 max-w-4xl">
      <header className="mb-6">
        <div className="text-xs uppercase tracking-widest text-[var(--muted)]">Entraînement</div>
        <h1 className="text-3xl font-semibold mt-1">Jouer vs Stockfish</h1>
      </header>

      {urlGameId && (
        <Card className="mb-4 border-l-4 border-l-[var(--info)]">
          <div className="text-xs uppercase tracking-widest text-[var(--info)]">Rejouer une position</div>
          <div className="text-sm mt-1">
            Tu repars de la position <b>ply {urlPly ?? "?"} de la partie #{urlGameId}</b>{urlTitle ? ` — ${urlTitle}` : ""}.
            Configure les paramètres ci-dessous puis affronte Stockfish à partir de ce moment.
          </div>
        </Card>
      )}

      <Card>
        <CardHeader><CardTitle>Nouvelle partie</CardTitle></CardHeader>
        <div className="space-y-5">
          <div>
            <div className="text-xs text-[var(--muted)] mb-2">Ouverture imposée (optionnel)</div>
            <select
              value={openingKey ?? ""}
              onChange={(e) => setOpeningKey(e.target.value || null)}
              className="w-full bg-[var(--surface)] border rounded px-2 py-2 text-sm"
            >
              <option value="">— Pas de contrainte (jeu libre) —</option>
              {openingsQ.data?.openings.map((op) => (
                <option key={op.key} value={op.key}>
                  [{op.user_color === "white" ? "B" : "N"}] {op.name} ({op.eco})
                  {op.branch_count > 0 ? ` — ${op.branch_count + 1} variantes` : ""}
                </option>
              ))}
            </select>
            {selectedOpening && (
              <div className="mt-2 text-xs text-[var(--muted)] space-y-1">
                <div>{selectedOpening.summary}</div>
                <div className="text-[var(--info)]">
                  Tu joues les <b>{selectedOpening.user_color === "white" ? "Blancs" : "Noirs"}</b>.
                  {selectedOpening.branch_count > 0 ? (
                    <> Stockfish choisira au hasard parmi {selectedOpening.branch_count + 1} variantes
                    ({["Mainline", ...selectedOpening.branches].join(", ")}) — tu dois t&apos;adapter.</>
                  ) : (
                    <> Suis la ligne théorique sur {selectedOpening.plies} demi-coups.</>
                  )}
                </div>
                <div className="text-[var(--warning,_#d97706)] inline-flex items-center gap-1.5">
                  <AlertTriangle className="size-3" /> Hors théorie → annulation auto (si budget &gt; 0), sinon défaite immédiate.
                </div>
              </div>
            )}
          </div>

          <div>
            <div className="text-xs text-[var(--muted)] mb-2">Ta couleur</div>
            <div className="flex gap-2">
              {(["white", "black"] as const).map((c) => (
                <button
                  key={c}
                  onClick={() => !selectedOpening && setColor(c)}
                  disabled={!!selectedOpening}
                  className={`text-sm px-4 py-2 rounded border ${color === c ? "bg-[var(--accent)] text-black border-[var(--accent)]" : "bg-[var(--surface-2)] text-[var(--muted)]"} ${selectedOpening ? "opacity-60 cursor-not-allowed" : ""}`}
                >
                  {c === "white" ? "Blancs" : "Noirs"}
                </button>
              ))}
            </div>
            {selectedOpening && (
              <div className="text-xs text-[var(--muted)] mt-1">Couleur fixée par l&apos;ouverture choisie.</div>
            )}
          </div>

          <div>
            <div className="text-xs text-[var(--muted)] mb-2">ELO Stockfish</div>
            <input
              type="range" min={1320} max={2400} step={20} value={elo}
              onChange={(e) => setElo(Number(e.target.value))}
              className="w-full"
            />
            <div className="flex items-baseline gap-3">
              <div className="text-2xl font-semibold tabular-nums">{elo}</div>
              <div className="text-xs text-[var(--muted)]">
                Stockfish ne descend pas sous 1320 — pour jouer plus faible, baisse le skill ci-dessous.
              </div>
            </div>
          </div>

          <div>
            <div className="text-xs text-[var(--muted)] mb-2">Skill level (0 = très faible, 20 = max)</div>
            <input
              type="range" min={0} max={20} step={1} value={skill}
              onChange={(e) => setSkill(Number(e.target.value))}
              className="w-full"
            />
            <div className="flex items-baseline gap-3">
              <div className="text-2xl font-semibold tabular-nums">{skill}</div>
              <div className="text-xs text-[var(--muted)]">
                {skill <= 3 ? "Stockfish joue souvent des coups sous-optimaux — bon pour débuter."
                  : skill <= 8 ? "Niveau amateur — Stockfish fait des erreurs régulières."
                  : skill <= 14 ? "Niveau intermédiaire."
                  : "Niveau fort — Stockfish quasi-optimal."}
              </div>
            </div>
          </div>

          <div className={selectedOpening ? "opacity-50 pointer-events-none" : ""}>
            <label className="flex items-center gap-2 text-sm cursor-pointer">
              <input
                type="checkbox"
                checked={customPos && !selectedOpening}
                disabled={!!selectedOpening}
                onChange={(e) => {
                  setCustomPos(e.target.checked);
                  if (!e.target.checked) setFen(START_FEN);
                }}
              />
              <span>Démarrer depuis une position personnalisée</span>
            </label>
            <div className="text-xs text-[var(--muted)] mt-1">
              Par défaut, la partie commence à la position initiale standard.
              Active cette option pour drill une finale ou rejouer un moment précis.
            </div>
          </div>

          {customPos && (
            <div className="rounded border bg-[var(--surface-2)] p-3">
              <PositionEditor value={fen} onChange={setFen} size={320} />
              <details className="mt-3 text-xs">
                <summary className="text-[var(--muted)] cursor-pointer hover:text-[var(--foreground)]">
                  Avancé : FEN brut
                </summary>
                <input
                  value={fen}
                  onChange={(e) => setFen(e.target.value)}
                  className="mt-2 w-full bg-[var(--surface)] border rounded px-2 py-1.5 text-[10px] font-mono"
                />
                <div className="mt-1 text-[var(--muted)]">
                  Tu peux coller un FEN copié depuis Lichess, Chess.com ou Game Review.
                </div>
              </details>
            </div>
          )}

          <div>
            <div className="text-xs text-[var(--muted)] mb-2">Annulations autorisées</div>
            <div className="grid grid-cols-2 gap-1.5">
              {(["0", "1", "3", "999"] as UndoMode[]).map((m) => (
                <button
                  key={m}
                  onClick={() => setUndoMode(m)}
                  className={cn(
                    "text-xs px-2 py-1.5 rounded border",
                    undoMode === m
                      ? "bg-[var(--accent)] text-black border-[var(--accent)]"
                      : "bg-[var(--surface-2)] text-[var(--muted)] hover:text-[var(--foreground)]",
                  )}
                >
                  {UNDO_LABELS[m]}
                </button>
              ))}
            </div>
          </div>

          <button
            onClick={() => start.mutate({
              fen, user_color: color, skill_level: skill, sf_elo: elo, depth: 12,
              max_undos: Number(undoMode),
              title: urlTitle ?? (selectedOpening ? `Drill ${selectedOpening.name}` : undefined),
              source: openingKey ? "opening_drill" : urlGameId ? "my_game" : undefined,
              source_ref: urlGameId
                ? { game_id: Number(urlGameId), ply: urlPly ? Number(urlPly) : undefined }
                : undefined,
              opening_key: openingKey,
            })}
            disabled={start.isPending}
            className="w-full py-3 rounded bg-[var(--accent)] text-black font-medium disabled:opacity-50"
          >
            {start.isPending ? "Démarrage..." : "Commencer →"}
          </button>

          {start.isError && (
            <div className="text-sm text-[var(--danger)]">
              {start.error instanceof ApiError ? JSON.stringify(start.error.body) : String(start.error)}
            </div>
          )}
        </div>
      </Card>

      <div className="mt-6 opacity-60 pointer-events-none">
        <Board fen={fen} orientation={color} allowDragging={false} size={360} />
      </div>
    </div>
  );
}
