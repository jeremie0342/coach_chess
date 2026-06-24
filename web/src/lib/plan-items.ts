/**
 * Resolves a DailyPlanItem (from /coach/me/today) to a navigation target
 * or a "note" action. Aligned with backend DailyItemKind enum:
 *   repertoire_drill | puzzle_focused | blunder_review |
 *   endgame_practice | opening_study | coach_note
 */

export type PlanFilters = Record<string, unknown> | null | undefined;

export type ItemAction =
  | { type: "link"; href: string; label: string }
  | { type: "note"; label: string };

function qs(params: Record<string, string | number | undefined>): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "") sp.set(k, String(v));
  }
  const s = sp.toString();
  return s ? `?${s}` : "";
}

/**
 * @param itemId If provided, appended as ?plan_item=ID for auto-tracking.
 */
export function resolveItemAction(kind: string, filters: PlanFilters, itemId?: number): ItemAction {
  const f = (filters ?? {}) as Record<string, unknown>;
  const pid = itemId != null ? { plan_item: itemId } : {};

  switch (kind) {
    case "repertoire_drill":
      return { type: "link", label: "Drill", href: `/repertoire${qs(pid as never)}` };

    case "puzzle_focused": {
      // Plan items often store multiple coach-recommended themes (e.g.
      // ['hangingPiece', 'trapped', 'fork']). Pass them as CSV `themes=` so the
      // backend can OR them and the front can auto-exclude mate tags.
      const themesArr = Array.isArray(f.themes) ? (f.themes as string[]) : null;
      const params: Record<string, string | number | undefined> = {
        ...pid,
        rating: f.rating as number | undefined,
        rating_window: f.rating_window as number | undefined,
        source_kind: f.source_kind as string | undefined,
      };
      if (themesArr && themesArr.length > 0) {
        params.themes = themesArr.join(",");
      } else if (f.theme) {
        params.theme = f.theme as string;
      }
      return { type: "link", label: "Résoudre", href: `/puzzles${qs(params as never)}` };
    }

    case "blunder_review":
      return { type: "link", label: "Revoir", href: `/puzzles${qs({ ...pid, source_kind: "blunder" } as never)}` };

    case "endgame_practice":
      return { type: "link", label: "Finale", href: `/puzzles${qs({ ...pid, theme: "endgame" } as never)}` };

    case "opening_study": {
      const params: Record<string, string | number | undefined> = { ...pid };
      const ok = f.opening_key as string | undefined;
      if (ok) params.opening_key = ok;
      return { type: "link", label: "Étudier", href: `/opening-trainer${qs(params as never)}` };
    }

    case "coach_note": {
      // Some coach_notes encode an objective filter — surface a real action.
      if (f.needs_lab_review) {
        return { type: "link", label: "Lab", href: `/lab${qs(pid as never)}` };
      }
      if (f.time_controls) {
        return { type: "note", label: "Marquer lu" };
      }
      return { type: "note", label: "Marquer lu" };
    }

    default:
      return { type: "link", label: "Ouvrir", href: "/today" };
  }
}

const KIND_LABELS: Record<string, string> = {
  repertoire_drill: "Répertoire",
  puzzle_focused: "Puzzles",
  blunder_review: "Mes blunders",
  endgame_practice: "Finales",
  opening_study: "Ouvertures",
  coach_note: "Note",
};

export function kindLabel(kind: string): string {
  return KIND_LABELS[kind] ?? kind;
}
