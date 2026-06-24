"use client";

import { create } from "zustand";

export type ToastVariant = "success" | "info" | "warning" | "error";

export type Toast = {
  id: string;
  title: string;
  message?: string;
  variant: ToastVariant;
  /** ms before auto-dismiss. 0 = persistent until clicked. */
  duration: number;
  href?: string;        // optional CTA link
  hrefLabel?: string;
};

type ToastState = {
  toasts: Toast[];
  push: (t: Omit<Toast, "id" | "duration"> & { duration?: number }) => string;
  dismiss: (id: string) => void;
  clear: () => void;
};

let _idCounter = 0;
const nextId = () => `t-${Date.now()}-${++_idCounter}`;

export const useToastStore = create<ToastState>((set) => ({
  toasts: [],
  push: (t) => {
    const id = nextId();
    const toast: Toast = {
      id,
      title: t.title,
      message: t.message,
      variant: t.variant,
      duration: t.duration ?? 6000,
      href: t.href,
      hrefLabel: t.hrefLabel,
    };
    set((s) => ({ toasts: [...s.toasts, toast] }));
    return id;
  },
  dismiss: (id) =>
    set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
  clear: () => set({ toasts: [] }),
}));

/**
 * Helper for the most common case — celebrating a daily-plan item completion.
 */
export function celebrate(title: string, message?: string, href?: string) {
  return useToastStore.getState().push({
    title,
    message,
    href,
    hrefLabel: href ? "Voir le plan" : undefined,
    variant: "success",
    duration: 8000,
  });
}
