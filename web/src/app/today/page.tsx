"use client";

import Link from "next/link";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import { cn } from "@/lib/utils";
import { resolveItemAction, kindLabel } from "@/lib/plan-items";

type PlanItem = {
  id: number;
  order: number;
  kind: string;
  title: string;
  target_count: number;
  estimated_minutes: number;
  filters: Record<string, unknown> | null;
  rationale: string | null;
  completed_count: number;
  completed_at: string | null;
};

type TodayPlan = {
  date: string;
  target_minutes: number;
  weakness_focus: string | null;
  coach_message: string | null;
  completed_at: string | null;
  items: PlanItem[];
};

export default function TodayPage() {
  const qc = useQueryClient();
  const q = useQuery<TodayPlan>({
    queryKey: ["today"],
    queryFn: () => api<TodayPlan>("/coach/me/today"),
  });

  const complete = useMutation({
    mutationFn: (id: number) => api(`/coach/me/today/items/${id}/complete`, { json: { delta_count: 1 } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["today"] }),
  });

  const regen = useMutation({
    mutationFn: () => api<TodayPlan>("/coach/me/today", { query: { regenerate: true } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["today"] }),
  });

  return (
    <div className="px-4 py-6 md:px-8 md:py-8 max-w-5xl">
      <header className="mb-6 flex items-end justify-between">
        <div>
          <div className="text-xs uppercase tracking-widest text-[var(--muted)]">Coach</div>
          <h1 className="text-3xl font-semibold mt-1">Plan du jour</h1>
          {q.data && (
            <div className="text-sm text-[var(--muted)] mt-1">
              {q.data.target_minutes} min visées · focus :{" "}
              <span className="text-[var(--foreground)]">{q.data.weakness_focus ?? "—"}</span>
            </div>
          )}
        </div>
        <button
          onClick={() => regen.mutate()}
          disabled={regen.isPending}
          className="text-xs px-3 py-1.5 rounded border bg-[var(--surface-2)] hover:bg-[var(--surface)] disabled:opacity-50"
        >
          {regen.isPending ? "..." : "Régénérer"}
        </button>
      </header>

      {q.isLoading && <Card className="animate-pulse h-32" />}

      {q.data?.coach_message && (
        <Card className="mb-6 border-l-4 border-l-[var(--accent)]">
          <div className="text-xs uppercase tracking-widest text-[var(--muted)] mb-2">Message du coach</div>
          <div className="text-sm leading-relaxed whitespace-pre-wrap">{q.data.coach_message}</div>
        </Card>
      )}

      <div className="space-y-3">
        {q.data?.items.map((it) => {
          const done = it.completed_at != null;
          const action = resolveItemAction(it.kind, it.filters);
          return (
            <Card key={it.id} className={cn("transition-opacity", done && "opacity-60")}>
              <div className="flex items-start gap-4">
                <div className="text-xs text-[var(--muted)] tabular-nums w-6 mt-1">#{it.order + 1}</div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-3 flex-wrap">
                    <div className="text-sm font-medium">{it.title}</div>
                    <span className="text-[10px] uppercase px-1.5 py-0.5 rounded bg-[var(--surface-2)] text-[var(--muted)]">{kindLabel(it.kind)}</span>
                  </div>
                  {it.rationale && (
                    <div className="text-xs text-[var(--muted)] mt-1">{it.rationale}</div>
                  )}
                  <div className="text-xs text-[var(--muted)] mt-2 flex gap-4 tabular-nums">
                    <span>{it.completed_count} / {it.target_count}</span>
                    <span>≈ {it.estimated_minutes} min</span>
                  </div>
                </div>
                <div className="flex gap-2 shrink-0">
                  {action.type === "link" && !done && (
                    <Link href={action.href} className="text-xs px-3 py-1.5 rounded bg-[var(--accent)] text-black font-medium">
                      {action.label}
                    </Link>
                  )}
                  {action.type === "note" && !done && (
                    <button
                      onClick={() => complete.mutate(it.id)}
                      disabled={complete.isPending}
                      className="text-xs px-3 py-1.5 rounded bg-[var(--accent)] text-black font-medium disabled:opacity-50"
                    >
                      {action.label}
                    </button>
                  )}
                  {done && (
                    <span className="text-xs text-[var(--accent)] font-medium px-3 py-1.5">✓ Terminé</span>
                  )}
                </div>
              </div>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
