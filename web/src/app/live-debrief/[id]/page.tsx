"use client";

import { use } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api";
import { Card } from "@/components/ui/Card";
import { DebriefResult, type DebriefPayload } from "../_components";

export default function LiveDebriefDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const debriefId = Number(id);
  const router = useRouter();
  const qc = useQueryClient();

  const q = useQuery<DebriefPayload>({
    queryKey: ["live-debrief", debriefId],
    queryFn: () => api<DebriefPayload>(`/coach/live_debrief/${debriefId}`),
  });

  const del = useMutation({
    mutationFn: () => api<{ deleted: number }>(`/coach/live_debrief/${debriefId}`, { method: "DELETE" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["live-debriefs"] });
      router.push("/live-debrief");
    },
  });

  return (
    <div className="px-4 py-6 md:px-8 md:py-8 max-w-5xl">
      <header className="mb-6 flex items-end justify-between flex-wrap gap-2">
        <div>
          <Link href="/live-debrief" className="text-xs text-[var(--muted)] hover:text-[var(--foreground)]">← Tous les debriefs</Link>
          <h1 className="text-2xl font-semibold mt-1">{q.data?.title || `Debrief #${debriefId}`}</h1>
          {q.data?.created_at && (
            <div className="text-xs text-[var(--muted)] mt-1">
              {new Date(q.data.created_at).toLocaleString("fr-FR")}
              {q.data.game_id && (
                <> · <Link href={`/games/${q.data.game_id}`} className="text-[var(--info)] hover:underline">Game #{q.data.game_id}</Link></>
              )}
            </div>
          )}
        </div>
        <button
          onClick={() => {
            if (confirm("Supprimer ce debrief ?")) del.mutate();
          }}
          className="px-3 py-2 rounded border border-[var(--danger)]/40 text-[var(--danger)] text-sm hover:bg-[var(--danger)]/10"
        >
          Supprimer
        </button>
      </header>

      {q.isLoading && <div className="text-sm text-[var(--muted)]">Chargement…</div>}
      {q.isError && (
        <Card className="border-[var(--danger)]/40 text-sm text-[var(--danger)]">
          {q.error instanceof ApiError ? JSON.stringify(q.error.body) : String(q.error)}
        </Card>
      )}
      {q.data && <DebriefResult data={q.data} />}
    </div>
  );
}
