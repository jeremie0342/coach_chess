"use client";

import { usePlanCompletionWatcher } from "@/hooks/usePlanCompletionWatcher";

/** Mount-only side-effect: watches today's plan for newly-completed items
 *  and fires a celebratory toast on each transition. */
export function PlanWatcher() {
  usePlanCompletionWatcher();
  return null;
}
