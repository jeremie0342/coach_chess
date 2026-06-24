"use client";

import { useEffect } from "react";
import Link from "next/link";
import { AnimatePresence, motion } from "framer-motion";
import { CheckCircle2, Info, AlertTriangle, XCircle, X } from "lucide-react";
import { useToastStore, type Toast } from "@/lib/toast-store";
import { cn } from "@/lib/utils";

const ICONS = {
  success: CheckCircle2,
  info: Info,
  warning: AlertTriangle,
  error: XCircle,
};

const BORDERS = {
  success: "border-l-[var(--accent)]",
  info: "border-l-[var(--info)]",
  warning: "border-l-[var(--warning)]",
  error: "border-l-[var(--danger)]",
};

const ICON_TONES = {
  success: "text-[var(--accent)]",
  info: "text-[var(--info)]",
  warning: "text-[var(--warning)]",
  error: "text-[var(--danger)]",
};

export function Toaster() {
  const toasts = useToastStore((s) => s.toasts);
  return (
    <div className="pointer-events-none fixed top-3 left-1/2 -translate-x-1/2 z-[100] w-full max-w-md px-3 flex flex-col items-stretch gap-2">
      <AnimatePresence initial={false}>
        {toasts.map((t) => (
          <ToastCard key={t.id} toast={t} />
        ))}
      </AnimatePresence>
    </div>
  );
}

function ToastCard({ toast }: { toast: Toast }) {
  const dismiss = useToastStore((s) => s.dismiss);
  const Icon = ICONS[toast.variant];

  useEffect(() => {
    if (toast.duration <= 0) return;
    const t = window.setTimeout(() => dismiss(toast.id), toast.duration);
    return () => window.clearTimeout(t);
  }, [toast.id, toast.duration, dismiss]);

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: -16, scale: 0.96 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: -12, scale: 0.96 }}
      transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
      className={cn(
        "pointer-events-auto rounded-lg border border-[var(--border)] border-l-4 bg-[var(--surface)] shadow-lg px-3 py-3 flex items-start gap-3",
        BORDERS[toast.variant],
      )}
    >
      <Icon className={cn("size-4 shrink-0 mt-0.5", ICON_TONES[toast.variant])} />
      <div className="flex-1 min-w-0">
        <div className="text-sm font-medium leading-tight">{toast.title}</div>
        {toast.message && (
          <div className="text-xs text-[var(--muted)] mt-0.5 leading-snug">{toast.message}</div>
        )}
        {toast.href && (
          <Link
            href={toast.href}
            onClick={() => dismiss(toast.id)}
            className="text-xs text-[var(--info)] hover:underline mt-1.5 inline-block"
          >
            {toast.hrefLabel ?? "Voir →"}
          </Link>
        )}
      </div>
      <button
        onClick={() => dismiss(toast.id)}
        aria-label="Fermer"
        className="p-1 -m-1 rounded text-[var(--muted)] hover:text-[var(--foreground)]"
      >
        <X className="size-3.5" />
      </button>
    </motion.div>
  );
}
