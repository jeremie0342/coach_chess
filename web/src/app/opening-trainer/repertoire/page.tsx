"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2, Flame, Crown, ArrowLeft, BookOpen, Play } from "lucide-react";
import { api } from "@/lib/api";
import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import { cn } from "@/lib/utils";
import type { OpeningGroupsResponse } from "@/types/opening-trainer";

type RepertoireEntry = {
  id: number;
  opening_key: string;
  base_name: string;
  name: string;
  eco: string | null;
  summary: string | null;
  user_color: "white" | "black";
  position: number;
  notes: string | null;
  added_at: string | null;
  missing_from_library: boolean;
  progress: {
    status: string;
    streak_days: number;
    best_streak: number;
    attempts: number;
    perfect_runs: number;
  } | null;
};

type RepertoireResp = {
  white: RepertoireEntry[];
  black: RepertoireEntry[];
};

export default function MyRepertoirePage() {
  const qc = useQueryClient();
  const [browseSide, setBrowseSide] = useState<"white" | "black">("white");

  const repertoire = useQuery<RepertoireResp>({
    queryKey: ["opening-repertoire"],
    queryFn: () => api<RepertoireResp>("/trainer/opening/repertoire"),
  });

  const library = useQuery<OpeningGroupsResponse>({
    queryKey: ["opening-trainer-list-grouped"],
    queryFn: () =>
      api<OpeningGroupsResponse>("/trainer/opening/list", { query: { grouped: "true" } }),
  });

  const addMut = useMutation({
    mutationFn: (opening_key: string) =>
      api("/trainer/opening/repertoire", { json: { opening_key } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["opening-repertoire"] }),
  });

  const removeMut = useMutation({
    mutationFn: (opening_key: string) =>
      api(`/trainer/opening/repertoire/${opening_key}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["opening-repertoire"] }),
  });

  const myKeys = useMemo(() => {
    const r = repertoire.data;
    if (!r) return new Set<string>();
    return new Set([...r.white, ...r.black].map((e) => e.opening_key));
  }, [repertoire.data]);

  const groupsForSide = (library.data?.groups ?? []).filter(
    (g) => g.user_color === browseSide
  );

  const myEntries =
    browseSide === "white" ? repertoire.data?.white ?? [] : repertoire.data?.black ?? [];

  return (
    <div className="px-4 py-6 md:px-8 md:py-8 max-w-6xl">
      <header className="mb-6">
        <div className="text-xs uppercase tracking-widest text-[var(--muted)]">
          <Link href="/opening-trainer" className="inline-flex items-center gap-1 hover:text-[var(--foreground)]">
            <ArrowLeft className="size-3" /> Opening trainer
          </Link>
        </div>
        <h1 className="text-3xl font-semibold mt-1">Mon répertoire</h1>
        <p className="text-sm text-[var(--muted)] mt-2 max-w-2xl">
          Choisis les ouvertures que tu veux travailler. Elles apparaîtront ici avec
          leur progression — clique sur une carte pour lancer une session de drill.
        </p>
      </header>

      <div className="mb-4 flex gap-1.5">
        {(["white", "black"] as const).map((c) => (
          <button
            key={c}
            onClick={() => setBrowseSide(c)}
            className={cn(
              "text-xs px-3 py-1.5 rounded border",
              browseSide === c
                ? "bg-[var(--accent)] text-black border-[var(--accent)]"
                : "bg-[var(--surface-2)] text-[var(--muted)] hover:text-[var(--foreground)]"
            )}
          >
            {c === "white" ? "Blancs" : "Noirs"}
          </button>
        ))}
      </div>

      <section className="mb-8">
        <div className="text-xs uppercase tracking-widest text-[var(--muted)] mb-3">
          {browseSide === "white" ? "Mes ouvertures blanches" : "Mes défenses noires"}
        </div>
        {myEntries.length === 0 ? (
          <Card>
            <div className="text-sm text-[var(--muted)]">
              Aucune ouverture pour les {browseSide === "white" ? "blancs" : "noirs"} pour
              l&apos;instant. Ajoute-en une depuis le catalogue ci-dessous.
            </div>
          </Card>
        ) : (
          <div className="grid md:grid-cols-2 gap-4">
            {myEntries.map((e) => (
              <Card key={e.id} className="flex flex-col">
                <CardHeader>
                  <div className="min-w-0">
                    <CardTitle>{e.base_name}</CardTitle>
                    <div className="text-sm font-medium mt-1 truncate">{e.name}</div>
                    <div className="text-xs text-[var(--muted)] mt-1 font-mono">
                      {e.eco ?? "—"} · {e.user_color === "white" ? "Blancs" : "Noirs"}
                    </div>
                  </div>
                  <button
                    onClick={() => {
                      if (confirm(`Retirer ${e.base_name} de ton répertoire ?`)) {
                        removeMut.mutate(e.opening_key);
                      }
                    }}
                    className="text-[var(--muted)] hover:text-[var(--danger)] p-1"
                    title="Retirer"
                  >
                    <Trash2 className="size-4" />
                  </button>
                </CardHeader>

                {e.summary && (
                  <p className="text-sm text-[var(--foreground)]/80 leading-relaxed mb-3">
                    {e.summary}
                  </p>
                )}

                {e.progress ? (
                  <div className="text-xs text-[var(--muted)] mb-3 flex items-center gap-3 tabular-nums">
                    {e.progress.status === "OpeningProgressStatus.MASTERED" ||
                    e.progress.status === "mastered" ? (
                      <span className="inline-flex items-center gap-1 text-[var(--warning)]">
                        <Crown className="size-3" /> Maîtrisée
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1">
                        <Flame
                          className={cn(
                            "size-3",
                            e.progress.streak_days > 0
                              ? "text-[var(--accent)]"
                              : "text-[var(--muted)]"
                          )}
                        />
                        Streak : <b className="text-[var(--foreground)]">{e.progress.streak_days}j</b>
                      </span>
                    )}
                    <span>
                      {e.progress.perfect_runs} runs parfaits / {e.progress.attempts}
                    </span>
                  </div>
                ) : (
                  <div className="text-xs text-[var(--muted)] mb-3 italic">
                    Pas encore travaillée
                  </div>
                )}

                <div className="mt-auto">
                  <Link
                    href={`/opening-trainer?opening_key=${encodeURIComponent(e.opening_key)}`}
                    className="inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded bg-[var(--accent)] text-black font-medium hover:opacity-90"
                  >
                    <Play className="size-3" /> Drill
                  </Link>
                </div>
              </Card>
            ))}
          </div>
        )}
      </section>

      <section>
        <div className="text-xs uppercase tracking-widest text-[var(--muted)] mb-3 flex items-center gap-2">
          <BookOpen className="size-3" />
          Catalogue — ajoute à ton répertoire
        </div>
        {library.isLoading && <div className="text-[var(--muted)]">Chargement…</div>}
        <div className="grid md:grid-cols-2 gap-4">
          {groupsForSide.map((g) => {
            const allVariantKeys = g.variants.map((v) => v.key);
            const someInRepertoire = allVariantKeys.some((k) => myKeys.has(k));
            return (
              <Card key={g.base_name} className={cn(someInRepertoire && "border-[var(--accent)]/40")}>
                <CardHeader>
                  <div className="min-w-0">
                    <CardTitle>{g.base_name}</CardTitle>
                    <div className="text-xs text-[var(--muted)] mt-1">
                      <span className="font-mono">{g.eco ?? "—"}</span> ·{" "}
                      {g.variants.length} variante{g.variants.length > 1 ? "s" : ""}
                    </div>
                  </div>
                </CardHeader>
                <p className="text-sm text-[var(--foreground)]/80 leading-relaxed mb-3">
                  {g.summary}
                </p>
                <div className="space-y-1.5">
                  {g.variants.map((v) => {
                    const inRep = myKeys.has(v.key);
                    return (
                      <div
                        key={v.key}
                        className="flex items-center justify-between gap-3 px-3 py-2 rounded border bg-[var(--surface-2)]"
                      >
                        <div className="min-w-0">
                          <div className="text-sm truncate">
                            {v.name.startsWith(g.base_name + " - ")
                              ? v.name.slice(g.base_name.length + 3)
                              : v.name}
                          </div>
                          <div className="text-xs text-[var(--muted)] font-mono">
                            {v.eco ?? ""} · {v.plies} plis
                          </div>
                        </div>
                        {inRep ? (
                          <span className="text-xs text-[var(--accent)] inline-flex items-center gap-1 shrink-0">
                            ✓ ajoutée
                          </span>
                        ) : (
                          <button
                            onClick={() => addMut.mutate(v.key)}
                            disabled={addMut.isPending}
                            className="inline-flex items-center gap-1 text-xs px-2.5 py-1 rounded border border-[var(--accent)]/40 text-[var(--accent)] hover:bg-[var(--accent)]/10 shrink-0 disabled:opacity-50"
                          >
                            <Plus className="size-3" /> Ajouter
                          </button>
                        )}
                      </div>
                    );
                  })}
                </div>
              </Card>
            );
          })}
        </div>
      </section>
    </div>
  );
}
