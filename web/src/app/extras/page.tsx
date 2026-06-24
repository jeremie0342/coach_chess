"use client";

import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { ChevronDown, Eye, Loader2, X } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import { DownloadButton } from "@/components/ui/DownloadButton";
import { cn } from "@/lib/utils";

const START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";

export default function ExtrasPage() {
  return (
    <div className="px-4 py-6 md:px-8 md:py-8 max-w-5xl">
      <header className="mb-6">
        <div className="text-xs uppercase tracking-widest text-[var(--muted)]">Outils</div>
        <h1 className="text-3xl font-semibold mt-1">Extras</h1>
        <p className="text-sm text-[var(--muted)] mt-2">
          Image cards, Lichess studies, OCR de position.
        </p>
      </header>

      <div className="space-y-6">
        <CardsSection />
        <LichessSection />
        <OcrSection />
      </div>
    </div>
  );
}

/* ---------- Cards ---------- */

type GameOpt = { id: number; played_at: string | null; color: string; opening: string | null; result: string; opp_username: string | null };
type ExerciseOpt = { id: number; rating: number | null; theme_tags?: string[]; kind?: string | null; created_at?: string; title?: string | null };

function useDebounce<T>(value: T, ms: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return debounced;
}

type ComboboxOption = { value: number; label: string };

function Combobox({
  value, onChange, options, placeholder, searchValue, onSearchChange, searchPlaceholder, footer, isLoading,
}: {
  value: number | "";
  onChange: (v: number | "") => void;
  options: ComboboxOption[];
  placeholder: string;
  searchValue: string;
  onSearchChange: (s: string) => void;
  searchPlaceholder: string;
  footer?: string;
  isLoading?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);

  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 0);
  }, [open]);

  const selected = options.find((o) => o.value === value);

  return (
    <div ref={ref} className="relative w-full min-w-0">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between gap-2 bg-[var(--surface-2)] border rounded px-2 py-1.5 text-sm font-mono text-left hover:bg-[var(--surface)]"
      >
        <span className="truncate">{selected ? selected.label : placeholder}</span>
        <ChevronDown className={cn("size-4 shrink-0 transition-transform", open && "rotate-180")} />
      </button>

      {open && (
        <div className="absolute z-50 top-full mt-1 left-0 right-0 rounded border bg-[var(--surface)] shadow-lg max-h-80 flex flex-col">
          <div className="p-2 border-b border-[var(--border)] flex items-center gap-1">
            <input
              ref={inputRef}
              value={searchValue}
              onChange={(e) => onSearchChange(e.target.value)}
              placeholder={searchPlaceholder}
              className="flex-1 bg-[var(--surface-2)] border rounded px-2 py-1 text-xs"
            />
            {searchValue && (
              <button
                onClick={() => onSearchChange("")}
                className="p-1 text-[var(--muted)] hover:text-[var(--foreground)]"
                title="Effacer"
              >
                <X className="size-3.5" />
              </button>
            )}
          </div>
          <div className="overflow-y-auto flex-1">
            {isLoading && (
              <div className="px-3 py-2 text-xs text-[var(--muted)] inline-flex items-center gap-1.5">
                <Loader2 className="size-3 animate-spin" /> Chargement…
              </div>
            )}
            {!isLoading && options.length === 0 && (
              <div className="px-3 py-3 text-xs text-[var(--muted)] italic">Aucun résultat</div>
            )}
            {!isLoading && options.map((o) => (
              <button
                key={o.value}
                onClick={() => { onChange(o.value); setOpen(false); }}
                className={cn(
                  "w-full text-left px-3 py-1.5 text-xs font-mono hover:bg-[var(--surface-2)] truncate",
                  o.value === value && "bg-[var(--accent)]/15 text-[var(--accent)]",
                )}
              >
                {o.label}
              </button>
            ))}
          </div>
          {footer && (
            <div className="px-3 py-1.5 border-t border-[var(--border)] text-[10px] text-[var(--muted)]">
              {footer}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function CardsSection() {
  const sp = useSearchParams();
  const initialGameId = sp?.get("game_id");
  const initialExId = sp?.get("exercise_id");

  const [fen, setFen] = useState(START);
  const [title, setTitle] = useState("Position du jour");
  const [gameId, setGameId] = useState<number | "">(initialGameId ? Number(initialGameId) : "");
  const [exId, setExId] = useState<number | "">(initialExId ? Number(initialExId) : "");

  // Search inputs with debounce so we don't hit the API on every keystroke
  const [gameSearch, setGameSearch] = useState("");
  const [exSearch, setExSearch] = useState("");
  const gameQuery = useDebounce(gameSearch, 250);
  const exQuery = useDebounce(exSearch, 250);

  const gamesQ = useQuery<{ total: number; items: GameOpt[] }>({
    queryKey: ["extras-games", gameQuery],
    queryFn: () => api<{ total: number; items: GameOpt[] }>("/games", {
      query: { limit: 30, scope: "all", ...(gameQuery ? { q: gameQuery } : {}) },
    }),
  });
  const exercisesQ = useQuery<ExerciseOpt[]>({
    queryKey: ["extras-exercises", exQuery],
    queryFn: () => api<ExerciseOpt[]>("/exercises", {
      query: { limit: 30, sort: "recent", ...(exQuery ? { q: exQuery } : {}) },
    }),
  });

  return (
    <Card>
      <CardHeader><CardTitle>Cards (image / GIF)</CardTitle></CardHeader>

      <div className="space-y-6 text-sm">

        {/* ---- Position PNG ---- */}
        <div>
          <div className="text-xs uppercase tracking-widest text-[var(--muted)] mb-2">Position PNG</div>
          <div className="space-y-2">
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Titre (visible sur l'image)"
              className="w-full bg-[var(--surface-2)] border rounded px-2 py-1.5 text-sm"
            />
            <input
              value={fen}
              onChange={(e) => setFen(e.target.value)}
              className="w-full bg-[var(--surface-2)] border rounded px-2 py-1.5 text-xs font-mono"
              placeholder="FEN"
            />
            <button onClick={() => setFen(START)} className="text-xs text-[var(--muted)] hover:text-[var(--foreground)]">
              ↺ Position de départ
            </button>
          </div>
          <div className="mt-3 grid md:grid-cols-[1fr_auto] gap-3 items-start">
            <div className="rounded border bg-[var(--surface-2)] overflow-hidden">
              <img
                src={`/api/proxy/cards/position.png?fen=${encodeURIComponent(fen)}&title=${encodeURIComponent(title)}`}
                alt="Preview de la position"
                className="w-full max-w-md"
              />
            </div>
            <div className="flex flex-col gap-2">
              <a
                href={`/api/proxy/cards/position.png?fen=${encodeURIComponent(fen)}&title=${encodeURIComponent(title)}`}
                target="_blank"
                className="text-xs px-3 py-2 rounded border bg-[var(--surface-2)] hover:bg-[var(--surface)] inline-flex items-center justify-center gap-1.5"
              >
                <Eye className="size-3.5" /> Voir
              </a>
              <DownloadButton
                href={`/api/proxy/cards/position.png?fen=${encodeURIComponent(fen)}&title=${encodeURIComponent(title)}&download=1`}
                label="Télécharger .png"
                className="text-xs px-3 py-2 rounded bg-[var(--accent)] text-black font-medium"
              />
            </div>
          </div>
        </div>

        {/* ---- Game GIF ---- */}
        <div className="border-t border-[var(--border)] pt-5">
          <div className="text-xs uppercase tracking-widest text-[var(--muted)] mb-2">GIF de partie</div>
          <div className="grid md:grid-cols-[minmax(0,1fr)_auto] gap-2 items-start">
            <Combobox
              value={gameId}
              onChange={setGameId}
              placeholder="— Choisis une partie —"
              searchValue={gameSearch}
              onSearchChange={setGameSearch}
              searchPlaceholder="Filtrer : adversaire, ouverture, ECO ou ID…"
              isLoading={gamesQ.isFetching}
              footer={gameQuery
                ? `${gamesQ.data?.items.length ?? 0} résultat(s) pour "${gameQuery}"`
                : "30 plus récentes (toutes parties)"
              }
              options={(gamesQ.data?.items ?? []).map((g) => ({
                value: g.id,
                label: `#${g.id} · ${g.played_at ? new Date(g.played_at).toLocaleDateString("fr-FR") : "?"} · (${g.color === "white" ? "B" : "N"}) vs ${g.opp_username ?? "?"}${g.opening ? ` (${g.opening})` : ""}${g.result === "win" ? " (W)" : g.result === "loss" ? " (L)" : ""}`,
              }))}
            />
            <div className="flex gap-2">
              <a
                href={gameId === "" ? "#" : `/api/proxy/cards/game.gif?game_id=${gameId}`}
                target="_blank"
                onClick={(e) => { if (gameId === "") e.preventDefault(); }}
                className={`text-xs px-2 py-2 rounded border font-medium inline-flex items-center gap-1.5 ${gameId === "" ? "bg-[var(--surface-2)] text-[var(--muted)] cursor-not-allowed" : "bg-[var(--surface-2)] hover:bg-[var(--surface)]"}`}
              >
                <Eye className="size-3.5" /> Voir
              </a>
              <DownloadButton
                href={gameId === "" ? "#" : `/api/proxy/cards/game.gif?game_id=${gameId}&download=1`}
                disabled={gameId === ""}
                label=".gif"
                className="text-xs px-2 py-2 rounded border font-medium bg-[var(--surface-2)] hover:bg-[var(--surface)]"
              />
              <DownloadButton
                href={gameId === "" ? "#" : `/api/proxy/cards/game.mp4?game_id=${gameId}&download=1`}
                disabled={gameId === ""}
                title="MP4 = pausable, scrubbable, plus léger que le GIF"
                label=".mp4"
                className="text-xs px-2 py-2 rounded font-medium bg-[var(--accent)] text-black"
              />
            </div>
          </div>
        </div>

        {/* ---- Exercise GIF ---- */}
        <div className="border-t border-[var(--border)] pt-5">
          <div className="text-xs uppercase tracking-widest text-[var(--muted)] mb-2">GIF de puzzle (solution animée)</div>
          <div className="grid md:grid-cols-[minmax(0,1fr)_auto] gap-2 items-start">
            <Combobox
              value={exId}
              onChange={setExId}
              placeholder="— Choisis un puzzle —"
              searchValue={exSearch}
              onSearchChange={setExSearch}
              searchPlaceholder="Filtrer : titre, thème (fork, pin, mate…) ou ID…"
              isLoading={exercisesQ.isFetching}
              footer={exQuery
                ? `${exercisesQ.data?.length ?? 0} résultat(s) pour "${exQuery}"`
                : "30 plus récents"
              }
              options={(exercisesQ.data ?? []).map((ex) => ({
                value: ex.id,
                label: `#${ex.id}${ex.rating ? ` · rating ${ex.rating}` : ""}${ex.kind ? ` · ${ex.kind}` : ""}${ex.theme_tags && ex.theme_tags.length > 0 ? ` · ${ex.theme_tags.slice(0, 2).join(", ")}` : ""}`,
              }))}
            />
            <div className="flex gap-2">
              <a
                href={exId === "" ? "#" : `/api/proxy/cards/exercise.gif?exercise_id=${exId}`}
                target="_blank"
                onClick={(e) => { if (exId === "") e.preventDefault(); }}
                className={`text-xs px-2 py-2 rounded border font-medium inline-flex items-center gap-1.5 ${exId === "" ? "bg-[var(--surface-2)] text-[var(--muted)] cursor-not-allowed" : "bg-[var(--surface-2)] hover:bg-[var(--surface)]"}`}
              >
                <Eye className="size-3.5" /> Voir
              </a>
              <DownloadButton
                href={exId === "" ? "#" : `/api/proxy/cards/exercise.gif?exercise_id=${exId}&download=1`}
                disabled={exId === ""}
                label=".gif"
                className="text-xs px-2 py-2 rounded border font-medium bg-[var(--surface-2)] hover:bg-[var(--surface)]"
              />
              <DownloadButton
                href={exId === "" ? "#" : `/api/proxy/cards/exercise.mp4?exercise_id=${exId}&download=1`}
                disabled={exId === ""}
                title="MP4 pausable"
                label=".mp4"
                className="text-xs px-2 py-2 rounded font-medium bg-[var(--accent)] text-black"
              />
            </div>
          </div>
        </div>

      </div>
    </Card>
  );
}

/* ---------- Lichess ---------- */

type LichessStatus = { configured: boolean; username: string | null; detail: string | null };

function extractStudyId(input: string): string {
  // Accept full URL, study URL with chapter, or bare ID. Lichess study IDs are
  // 8 alphanumeric chars.
  const trimmed = input.trim();
  // Look for /study/<id> pattern
  const m = trimmed.match(/lichess\.org\/study\/([A-Za-z0-9]{8})/);
  if (m) return m[1];
  // Otherwise take first 8 alphanumeric chars
  const m2 = trimmed.match(/^[A-Za-z0-9]{8}/);
  return m2 ? m2[0] : trimmed;
}

function LichessSection() {
  const [studyRaw, setStudyRaw] = useState("");
  const [color, setColor] = useState<"" | "white" | "black">("");
  const [eco, setEco] = useState("");
  const [onlyLosses, setOnlyLosses] = useState(false);
  const [limit, setLimit] = useState(10);
  const [showHelp, setShowHelp] = useState(false);

  const studyId = extractStudyId(studyRaw);
  const studyIdValid = /^[A-Za-z0-9]{8}$/.test(studyId);

  const statusQ = useQuery<LichessStatus>({
    queryKey: ["lichess-status"],
    queryFn: () => api<LichessStatus>("/lichess/status"),
    staleTime: 60_000,
  });

  const push = useMutation({
    mutationFn: () =>
      api<{ chapters_pushed: number; chapters_failed: number; errors: string[] }>("/lichess/push_study", {
        json: {
          study_id: studyId,
          eco: eco || undefined,
          color: color || undefined,
          only_losses: onlyLosses,
          limit,
        },
      }),
  });

  const bundleUrl = `/api/proxy/lichess/export_bundle.pgn?limit=${limit}` +
    (color ? `&color=${color}` : "") +
    (eco ? `&eco=${eco}` : "") +
    (onlyLosses ? "&only_losses=true" : "");

  return (
    <Card>
      <CardHeader>
        <CardTitle>Export vers Lichess</CardTitle>
        <button onClick={() => setShowHelp((v) => !v)} className="text-xs text-[var(--info)] hover:underline">
          {showHelp ? "− Masquer l'aide" : "+ C'est quoi un Lichess study ?"}
        </button>
      </CardHeader>

      {showHelp && (
        <div className="mb-4 rounded border bg-[var(--surface-2)]/50 p-3 text-xs text-[var(--muted)] space-y-2">
          <div>
            Un <b className="text-[var(--foreground)]">study</b> Lichess est un dossier d&apos;analyse en ligne où tu regroupes plusieurs parties annotées. Tu peux les ré-analyser sur n&apos;importe quel appareil, partager le lien, et profiter de l&apos;interface complète Lichess (moteur cloud, mode entraînement, etc).
          </div>
          <div>
            <b className="text-[var(--foreground)]">Pour push direct depuis ici :</b>
            <ol className="list-decimal ml-5 mt-1 space-y-0.5">
              <li>Crée un study sur <a href="https://lichess.org/study" target="_blank" rel="noopener" className="text-[var(--info)] hover:underline">lichess.org/study</a> (+ nouveau study)</li>
              <li>Copie l&apos;URL ou l&apos;ID de 8 caractères depuis la barre du navigateur</li>
              <li>Configure <code className="font-mono">LICHESS_TOKEN</code> dans le <code className="font-mono">.env</code> du backend (token avec scope <code className="font-mono">study:write</code>, créé sur <a href="https://lichess.org/account/oauth/token" target="_blank" rel="noopener" className="text-[var(--info)] hover:underline">lichess.org/account/oauth/token</a>)</li>
            </ol>
          </div>
          <div>
            <b className="text-[var(--foreground)]">Sans token :</b> tu peux quand même télécharger le PGN ci-dessous puis l&apos;importer manuellement sur Lichess via le bouton « Importer PGN » du study.
          </div>
        </div>
      )}

      {/* Token status */}
      <div className="mb-4 rounded border px-3 py-2 text-xs flex items-center gap-2"
        style={{
          borderColor: statusQ.data?.username ? "var(--accent)" : "var(--border)",
          background: statusQ.data?.username ? "color-mix(in srgb, var(--accent) 8%, transparent)" : "var(--surface-2)",
        }}
      >
        {statusQ.isLoading && <Loader2 className="size-3 animate-spin" />}
        {statusQ.data?.username && (
          <span>
            <span className="text-[var(--accent)] font-medium">Connecté</span> en tant que{" "}
            <b className="font-mono text-[var(--foreground)]">{statusQ.data.username}</b> · push direct activé
          </span>
        )}
        {statusQ.data && !statusQ.data.username && (
          <span className="text-[var(--muted)]">
            Token non configuré — <code className="font-mono">LICHESS_TOKEN</code> manquant.
            Tu peux toujours télécharger le PGN ci-dessous.
            {statusQ.data.detail && <span className="text-[var(--danger)] ml-2">({statusQ.data.detail})</span>}
          </span>
        )}
      </div>

      {/* Filters */}
      <div className="text-xs uppercase tracking-widest text-[var(--muted)] mb-2">1. Quelles parties exporter</div>
      <div className="grid md:grid-cols-2 gap-3 text-sm mb-4">
        <label className="flex items-center gap-2">
          <span className="text-[var(--muted)] w-20">Couleur</span>
          <select value={color} onChange={(e) => setColor(e.target.value as "" | "white" | "black")}
            className="bg-[var(--surface-2)] border rounded px-2 py-1.5 text-sm flex-1">
            <option value="">toutes</option>
            <option value="white">blancs</option>
            <option value="black">noirs</option>
          </select>
        </label>
        <label className="flex items-center gap-2">
          <span className="text-[var(--muted)] w-20">ECO</span>
          <input value={eco} onChange={(e) => setEco(e.target.value.toUpperCase())} placeholder="ex. C50"
            className="bg-[var(--surface-2)] border rounded px-2 py-1.5 text-sm font-mono flex-1" />
        </label>
        <label className="flex items-center gap-2">
          <span className="text-[var(--muted)] w-20">Nombre</span>
          <input type="number" min={1} max={32} value={limit} onChange={(e) => setLimit(Number(e.target.value))}
            className="bg-[var(--surface-2)] border rounded px-2 py-1.5 text-sm w-20 tabular-nums" />
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={onlyLosses} onChange={(e) => setOnlyLosses(e.target.checked)} />
          <span>défaites uniquement</span>
        </label>
      </div>

      {/* Two paths */}
      <div className="grid md:grid-cols-2 gap-4">
        {/* Option A: download PGN */}
        <div className="rounded border bg-[var(--surface-2)]/30 p-3">
          <div className="text-xs uppercase tracking-widest text-[var(--muted)] mb-2">A. Télécharger le PGN</div>
          <p className="text-xs text-[var(--muted)] mb-3">
            Récupère un fichier <code className="font-mono">.pgn</code> que tu importes ensuite manuellement dans n&apos;importe quel study Lichess via leur bouton « Importer ».
          </p>
          <DownloadButton
            href={bundleUrl}
            label="Télécharger .pgn"
            className="text-xs px-3 py-1.5 rounded bg-[var(--accent)] text-black font-medium"
          />
        </div>

        {/* Option B: push to existing study */}
        <div className={cn("rounded border p-3", statusQ.data?.username ? "bg-[var(--surface-2)]/30" : "bg-[var(--surface-2)]/30 opacity-70")}>
          <div className="text-xs uppercase tracking-widest text-[var(--muted)] mb-2">B. Push direct vers un study</div>
          <p className="text-xs text-[var(--muted)] mb-2">
            Colle l&apos;URL complète <span className="font-mono">lichess.org/study/...</span> ou juste l&apos;ID de 8 caractères. L&apos;ID est extrait automatiquement.
          </p>
          <input
            value={studyRaw}
            onChange={(e) => setStudyRaw(e.target.value)}
            placeholder="https://lichess.org/study/abcd1234 ou abcd1234"
            className="w-full bg-[var(--surface-2)] border rounded px-2 py-1.5 text-sm font-mono mb-2"
          />
          {studyRaw && (
            <div className="text-xs mb-2">
              {studyIdValid
                ? <span className="text-[var(--accent)]">ID détecté : <span className="font-mono">{studyId}</span></span>
                : <span className="text-[var(--warning)]">Impossible d&apos;extraire un ID valide (8 chars alphanumériques)</span>
              }
            </div>
          )}
          <button
            onClick={() => push.mutate()}
            disabled={!studyIdValid || push.isPending || !statusQ.data?.username}
            className="w-full text-xs px-3 py-1.5 rounded bg-[var(--accent)] text-black font-medium disabled:opacity-50 inline-flex items-center justify-center gap-1.5"
          >
            {push.isPending && <Loader2 className="size-3 animate-spin" />}
            Push vers le study
          </button>
          {!statusQ.data?.username && !statusQ.isLoading && (
            <div className="text-xs text-[var(--muted)] mt-2 italic">
              Configure LICHESS_TOKEN pour activer cette option.
            </div>
          )}
        </div>
      </div>

      {push.isSuccess && (
        <div className="mt-3 rounded border border-[var(--accent)]/40 bg-[var(--accent)]/10 p-3 text-sm">
          <div className="text-[var(--accent)] font-medium mb-1">
            {push.data.chapters_pushed} partie(s) ajoutées au study
          </div>
          {push.data.chapters_failed > 0 && (
            <div className="text-xs text-[var(--warning)]">
              {push.data.chapters_failed} échec(s) — {push.data.errors?.slice(0, 2).join(" / ")}
            </div>
          )}
          <a
            href={`https://lichess.org/study/${studyId}`}
            target="_blank"
            rel="noopener"
            className="text-xs text-[var(--info)] hover:underline"
          >
            Ouvrir le study sur Lichess ↗
          </a>
        </div>
      )}
      {push.isError && (
        <div className="mt-3 text-xs text-[var(--danger)]">
          {push.error instanceof ApiError ? JSON.stringify(push.error.body) : String(push.error)}
        </div>
      )}
    </Card>
  );
}

/* ---------- OCR ---------- */

type OcrResult = {
  fen: string;
  mean_confidence: number;
  min_confidence: number;
  low_confidence_cells: { square: string; guess: string; conf: number }[];
};

function OcrSection() {
  const [side, setSide] = useState<"w" | "b">("w");
  const [flip, setFlip] = useState(false);
  const [result, setResult] = useState<OcrResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);

  const onFile = async (f: File) => {
    setBusy(true); setError(null); setResult(null); setCopied(false);
    try {
      const fd = new FormData();
      fd.append("file", f);
      const res = await fetch(`/api/proxy/board/ocr?side_to_move=${side}&flip=${flip}`, {
        method: "POST", body: fd,
      });
      const text = await res.text();
      let data: unknown = text;
      try { data = JSON.parse(text); } catch {}
      if (!res.ok) {
        setError(typeof data === "string" ? data : JSON.stringify(data));
      } else {
        setResult(data as OcrResult);
      }
    } catch (e) {
      setError(String(e));
    } finally { setBusy(false); }
  };

  // Verdict computation
  const verdict = (() => {
    if (!result) return null;
    const mc = result.mean_confidence;
    if (mc >= 0.85) return { tone: "good", title: "Position détectée avec confiance",
      sub: `Confiance moyenne ${Math.round(mc * 100)}%. Tu peux utiliser la FEN directement.` };
    if (mc >= 0.65) return { tone: "ok", title: "Position détectée — à vérifier",
      sub: `Confiance moyenne ${Math.round(mc * 100)}%. Compare visuellement la position détectée à ton screenshot avant utilisation.` };
    return { tone: "bad", title: "OCR raté",
      sub: `Confiance moyenne ${Math.round(mc * 100)}%. La position détectée est probablement fausse. Reprends un screenshot plus net (board cadré, pièces standard, pas d'annotations).` };
  })();

  const copyFen = async () => {
    if (!result) return;
    try {
      await navigator.clipboard.writeText(result.fen);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch { /* ignore */ }
  };

  return (
    <Card>
      <CardHeader><CardTitle>OCR de position</CardTitle></CardHeader>
      <p className="text-xs text-[var(--muted)] mb-3">
        Upload un screenshot d&apos;échiquier (Twitter, livre, Lichess, capture d&apos;écran…) et on essaie d&apos;en déduire la FEN.
        L&apos;outil ne devine pas qui a le trait — tu lui dis.
      </p>

      <div className="flex flex-wrap items-center gap-3 mb-3 text-sm">
        <label className="flex items-center gap-2">
          <span className="text-[var(--muted)]">Trait</span>
          <select value={side} onChange={(e) => setSide(e.target.value as "w" | "b")}
            className="bg-[var(--surface-2)] border rounded px-2 py-1.5 text-sm">
            <option value="w">blancs</option>
            <option value="b">noirs</option>
          </select>
        </label>
        <label className="flex items-center gap-2 text-sm" title="Coche si ton screenshot a les pièces noires en bas (board flippé)">
          <input type="checkbox" checked={flip} onChange={(e) => setFlip(e.target.checked)} />
          <span>Board flippé (noirs en bas)</span>
        </label>
      </div>

      <input
        type="file"
        accept="image/*"
        onChange={(e) => e.target.files?.[0] && onFile(e.target.files[0])}
        disabled={busy}
        className="block text-sm file:mr-3 file:py-1.5 file:px-3 file:rounded file:border-0 file:bg-[var(--accent)] file:text-black file:font-medium file:cursor-pointer disabled:opacity-50"
      />

      {busy && (
        <div className="mt-3 text-xs text-[var(--muted)] flex items-center gap-2">
          <Loader2 className="size-3 animate-spin" /> Analyse de l&apos;image…
        </div>
      )}

      {error && (
        <div className="mt-3 rounded border border-[var(--danger)]/40 bg-[var(--danger)]/10 p-3 text-sm text-[var(--danger)]">
          <div className="font-medium">Erreur OCR</div>
          <div className="text-xs mt-1">{error}</div>
        </div>
      )}

      {result && verdict && (
        <div className="mt-4 space-y-3">
          {/* Verdict banner */}
          <div className={cn(
            "rounded border-l-4 p-3",
            verdict.tone === "good" && "border-l-[var(--accent)] bg-[var(--accent)]/10",
            verdict.tone === "ok" && "border-l-[var(--warning)] bg-[var(--warning)]/10",
            verdict.tone === "bad" && "border-l-[var(--danger)] bg-[var(--danger)]/10",
          )}>
            <div className={cn(
              "text-sm font-medium",
              verdict.tone === "good" && "text-[var(--accent)]",
              verdict.tone === "ok" && "text-[var(--warning)]",
              verdict.tone === "bad" && "text-[var(--danger)]",
            )}>{verdict.title}</div>
            <div className="text-xs text-[var(--muted)] mt-1">{verdict.sub}</div>
          </div>

          {/* Detected position summary */}
          <div className="grid md:grid-cols-2 gap-3">
            <div className="rounded border bg-[var(--surface-2)]/40 p-3">
              <div className="text-xs uppercase tracking-widest text-[var(--muted)] mb-1">Position détectée</div>
              <pre className="text-[10px] font-mono break-all whitespace-pre-wrap text-[var(--foreground)]">{result.fen}</pre>
              <div className="text-xs text-[var(--muted)] mt-2 tabular-nums">
                Trait : {side === "w" ? "blancs" : "noirs"} · roques par défaut <span className="font-mono">KQkq</span>
              </div>
              <div className="text-xs text-[var(--muted)] tabular-nums">
                Confiance min sur une case : {Math.round(result.min_confidence * 100)}%
              </div>
            </div>

            <div className="rounded border bg-[var(--surface-2)]/40 p-3">
              <div className="text-xs uppercase tracking-widest text-[var(--muted)] mb-2">Que faire avec cette FEN</div>
              <div className="flex flex-col gap-1.5">
                <button
                  onClick={copyFen}
                  className="text-xs px-3 py-1.5 rounded border bg-[var(--surface-2)] hover:bg-[var(--surface)] text-left"
                >
                  {copied ? "Copié dans le presse-papier" : "Copier la FEN"}
                </button>
                <a
                  href={`/explorer?fen=${encodeURIComponent(result.fen)}`}
                  className="text-xs px-3 py-1.5 rounded border bg-[var(--surface-2)] hover:bg-[var(--surface)] inline-block"
                >
                  Ouvrir dans /explorer →
                </a>
                <a
                  href={`/play?fen=${encodeURIComponent(result.fen)}&title=Position OCR`}
                  className="text-xs px-3 py-1.5 rounded border bg-[var(--surface-2)] hover:bg-[var(--surface)] inline-block"
                >
                  Jouer vs Stockfish →
                </a>
                <a
                  href={`/tablebase?fen=${encodeURIComponent(result.fen)}`}
                  className="text-xs px-3 py-1.5 rounded border bg-[var(--surface-2)] hover:bg-[var(--surface)] inline-block"
                  title="Si c'est une finale ≤ 7 pièces"
                >
                  Sonder la tablebase →
                </a>
              </div>
            </div>
          </div>

          {/* Low confidence cells warning */}
          {result.low_confidence_cells.length > 0 && (
            <div className="rounded border border-[var(--warning)]/40 bg-[var(--warning)]/10 p-3 text-xs">
              <div className="font-medium text-[var(--warning)] mb-2">
                {result.low_confidence_cells.length} case(s) à vérifier
              </div>
              <div className="text-[var(--muted)] mb-2">
                L&apos;OCR n&apos;est pas sûr de ces cases. Compare-les visuellement à ton screenshot avant de te fier à la FEN.
              </div>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-1 font-mono">
                {result.low_confidence_cells.slice(0, 12).map((c, i) => (
                  <div key={i} className="flex justify-between">
                    <span><b>{c.square}</b> {c.guess || "vide"}</span>
                    <span className="text-[var(--muted)] tabular-nums">{Math.round(c.conf * 100)}%</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Raw JSON for debug */}
          <details className="text-xs">
            <summary className="text-[var(--muted)] cursor-pointer hover:text-[var(--foreground)]">
              JSON brut (debug)
            </summary>
            <pre className="mt-2 bg-[var(--surface-2)] rounded p-2 font-mono text-[10px] max-h-40 overflow-auto">
              {JSON.stringify(result, null, 2)}
            </pre>
          </details>
        </div>
      )}
    </Card>
  );
}

