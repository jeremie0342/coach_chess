"use client";

import { useEffect } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { FlaskConical, ArrowRight, CheckCircle2 } from "lucide-react";
import { api } from "@/lib/api";
import { Card, CardHeader, CardTitle } from "@/components/ui/Card";

type LabTarget = {
  has_target: boolean;
  needs_review?: boolean;
  game_id?: number;
  played_at?: string | null;
  opening?: string | null;
  eco?: string | null;
};

export default function LabPage() {
  const router = useRouter();
  const sp = useSearchParams();
  const planItem = sp?.get("plan_item");

  const q = useQuery<LabTarget>({
    queryKey: ["lab-target"],
    queryFn: () => api<LabTarget>("/games/me/next_lab_target"),
  });

  // Auto-forward to the actual review page once we have a target. Preserve
  // ?plan_item= so the Game Review page can credit the daily plan via the
  // auto-credit pipeline (a fresh lab_reviewed_at row).
  useEffect(() => {
    if (!q.data) return;
    if (!q.data.has_target) return;
    if (!q.data.needs_review) return; // already reviewed — stay so user can decide
    const params = new URLSearchParams();
    if (planItem) params.set("plan_item", planItem);
    const tail = params.toString() ? `?${params.toString()}` : "";
    router.replace(`/games/${q.data.game_id}${tail}`);
  }, [q.data, planItem, router]);

  return (
    <div className="px-4 py-6 md:px-8 md:py-8 max-w-3xl">
      <header className="mb-6 flex items-center gap-3">
        <FlaskConical className="size-5 text-[var(--accent)]" />
        <div>
          <div className="text-xs uppercase tracking-widest text-[var(--muted)]">Coach</div>
          <h1 className="text-3xl font-semibold mt-1">Lab d'analyse</h1>
        </div>
      </header>

      {q.isLoading && <Card className="animate-pulse h-24" />}

      {q.data?.has_target === false && (
        <Card>
          <div className="text-sm">Aucune partie à analyser. Tu n'as encore importé aucune défaite.</div>
          <Link href="/games" className="text-xs text-[var(--info)] hover:underline mt-2 inline-block">
            Voir mes parties →
          </Link>
        </Card>
      )}

      {q.data?.has_target && q.data.needs_review === false && (
        <Card>
          <CardHeader>
            <CardTitle>Tout analysé</CardTitle>
            <CheckCircle2 className="size-5 text-[var(--accent)]" />
          </CardHeader>
          <div className="text-sm leading-relaxed">
            Tu as déjà ouvert toutes tes défaites importées dans le Lab. Beau travail.
          </div>
          {q.data.game_id && (
            <div className="mt-4 border-t border-[var(--border)] pt-3">
              <div className="text-xs text-[var(--muted)] uppercase tracking-wider mb-1">
                Dernière défaite (déjà analysée)
              </div>
              <div className="flex items-center justify-between gap-3">
                <div>
                  <div className="text-sm">{q.data.opening ?? "—"}</div>
                  <div className="text-xs text-[var(--muted)] font-mono">
                    {q.data.eco ?? ""}
                    {q.data.played_at && ` · ${new Date(q.data.played_at).toLocaleDateString("fr-FR")}`}
                  </div>
                </div>
                <Link
                  href={`/games/${q.data.game_id}`}
                  className="text-xs px-3 py-1.5 rounded border bg-[var(--surface-2)] hover:bg-[var(--surface)] flex items-center gap-1"
                >
                  Revoir <ArrowRight className="size-3" />
                </Link>
              </div>
            </div>
          )}
        </Card>
      )}

      {q.data?.has_target && q.data.needs_review && (
        <Card>
          <div className="text-sm text-[var(--muted)]">Redirection vers la prochaine défaite à analyser…</div>
        </Card>
      )}

      <div className="mt-4 text-xs text-[var(--muted)]">
        Le Lab te conduit automatiquement vers ta défaite la plus récente non encore analysée.
        L'ouverture d'une partie marque automatiquement la révision (une fois suffit, pas de double-crédit).
      </div>
    </div>
  );
}
