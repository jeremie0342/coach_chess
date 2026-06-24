"use client";

import { useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { celebrate } from "@/lib/toast-store";
import { kindLabel } from "@/lib/plan-items";

type PlanItem = {
  id: number;
  kind: string;
  title: string;
  target_count: number;
  completed_count: number;
  completed_at: string | null;
};
type TodayResp = { items: PlanItem[] };

/**
 * Polls the daily plan and fires a celebratory toast each time an item
 * transitions from "incomplete" to "complete". Stateless across reloads —
 * we only celebrate transitions observed in this browser tab. We persist a
 * set of already-celebrated item IDs in sessionStorage to avoid showing
 * the same toast twice after a remount in the same session.
 */
const STORAGE_KEY = "coach.celebrated-items-v1";

function loadCelebrated(): Set<number> {
  if (typeof window === "undefined") return new Set();
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return new Set();
    return new Set(JSON.parse(raw) as number[]);
  } catch {
    return new Set();
  }
}

function saveCelebrated(s: Set<number>) {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(Array.from(s)));
  } catch { /* ignore */ }
}

export function usePlanCompletionWatcher() {
  const celebrated = useRef<Set<number>>(loadCelebrated());

  // Refetch every 30s while the page is visible so toasts fire even when
  // the user is on a different page than /today (e.g. /puzzles).
  const q = useQuery<TodayResp>({
    queryKey: ["today", "watcher"],
    queryFn: () => api<TodayResp>("/coach/me/today", { query: { generate_message_llm: false } }),
    refetchInterval: 30_000,
    refetchOnWindowFocus: true,
  });

  useEffect(() => {
    if (!q.data) return;
    let changed = false;
    for (const it of q.data.items) {
      if (!it.completed_at) continue;
      if (celebrated.current.has(it.id)) continue;
      // New completion — fire a toast.
      celebrated.current.add(it.id);
      changed = true;
      const msg = celebrationMessage(it);
      celebrate(msg.title, msg.body, "/today");
    }
    if (changed) saveCelebrated(celebrated.current);
  }, [q.data]);
}

function celebrationMessage(it: PlanItem): { title: string; body: string } {
  const tgt = it.target_count;
  switch (it.kind) {
    case "puzzle_focused":
      return {
        title: `🎯 ${tgt} puzzles tactiques bouclés !`,
        body: "Objectif du jour atteint. Tu peux continuer librement.",
      };
    case "endgame_practice":
      return {
        title: `♔ ${tgt} finales du jour résolues`,
        body: "Tu accroches les patterns de finale — c'est ce qui décide les parties.",
      };
    case "blunder_review":
      return {
        title: `🔍 ${tgt} blunders revus`,
        body: "Tu transformes tes erreurs en apprentissage. Continue.",
      };
    case "repertoire_drill":
      return {
        title: `📚 ${tgt} cartes répertoire validées`,
        body: "Ton répertoire est de plus en plus stable.",
      };
    case "opening_study":
      return {
        title: "♟ Ouverture du jour validée",
        body: `${it.title} — sans-faute aujourd'hui, le streak avance.`,
      };
    case "coach_note":
      return {
        title: `✓ ${it.title}`,
        body: "Note du coach marquée comme lue.",
      };
    default:
      return {
        title: `Objectif atteint — ${kindLabel(it.kind)}`,
        body: it.title,
      };
  }
}
