"use client";

import { useEffect } from "react";

export function useKeyNav({
  onPrev,
  onNext,
  onFirst,
  onLast,
  enabled = true,
}: {
  onPrev?: () => void;
  onNext?: () => void;
  onFirst?: () => void;
  onLast?: () => void;
  enabled?: boolean;
}) {
  useEffect(() => {
    if (!enabled) return;
    const handler = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      const tag = target?.tagName?.toLowerCase();
      if (tag === "input" || tag === "textarea" || target?.isContentEditable) return;
      switch (e.key) {
        case "ArrowLeft": e.preventDefault(); onPrev?.(); break;
        case "ArrowRight": e.preventDefault(); onNext?.(); break;
        case "Home": e.preventDefault(); onFirst?.(); break;
        case "End": e.preventDefault(); onLast?.(); break;
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [enabled, onPrev, onNext, onFirst, onLast]);
}
