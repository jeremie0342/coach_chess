"use client";

import { useCallback, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";

export type ActivePlanItem = {
  id: number;
  kind: string;
  title: string;
  target_count: number;
  completed_count: number;
  completed_at: string | null;
};

type TodayResp = { items: ActivePlanItem[] };

/**
 * If the current page was opened from `/today` with `?plan_item=ID`, returns
 * the plan item + an `increment()` helper that bumps the backend counter by 1.
 *
 * Pages should call `increment()` once per successful drill action (correct
 * puzzle, validated SR card, completed opening line, etc.). Counter stops
 * counting once it hits target_count.
 */
export function useActivePlanItem() {
  const sp = useSearchParams();
  const router = useRouter();
  const qc = useQueryClient();
  const raw = sp?.get("plan_item");
  const id = raw ? Number(raw) : null;

  const today = useQuery<TodayResp>({
    queryKey: ["today", "items-only"],
    queryFn: () => api<TodayResp>("/coach/me/today", { query: { generate_message_llm: false } }),
    enabled: id != null,
  });

  const item = today.data?.items.find((i) => i.id === id) ?? null;

  const complete = useMutation({
    mutationFn: () => api(`/coach/me/today/items/${id}/complete`, { json: { delta_count: 1 } }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["today"] });
    },
  });

  const increment = useCallback(() => {
    if (id == null) return;
    // Optimistic: always fire if we have a plan_item id. The backend handles
    // the target_count ceiling via completed_at. Don't gate on `item` —
    // between rapid successive puzzles, the today-query may not have
    // refetched yet, and stale `item` would silently swallow increments.
    complete.mutate();
  }, [id, complete]);

  const clear = useCallback(() => {
    const params = new URLSearchParams(sp?.toString() ?? "");
    params.delete("plan_item");
    const qsStr = params.toString();
    router.replace(qsStr ? `?${qsStr}` : window.location.pathname);
  }, [sp, router]);

  // Auto-clear once the item is finished, so the banner disappears.
  useEffect(() => {
    if (item?.completed_at != null) {
      // keep the URL — user might want to confirm. Just stop.
    }
  }, [item?.completed_at]);

  return { id, item, increment, clear, isBusy: complete.isPending };
}
