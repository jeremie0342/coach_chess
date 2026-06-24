"use client";

import { useMutation } from "@tanstack/react-query";
import { Loader2, CheckCircle2, AlertCircle } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";

export function SyncJobButton<TBody = Record<string, unknown>>({
  label,
  description,
  path,
  body,
  query,
  method = "POST",
  variant = "default",
}: {
  label: string;
  description?: string;
  path: string;
  body?: TBody;
  query?: Record<string, string | number | boolean>;
  method?: "POST" | "GET";
  variant?: "default" | "danger";
}) {
  const m = useMutation({
    mutationFn: () => api(path, { method, json: body, query }),
  });

  const tone =
    variant === "danger"
      ? "border-[var(--danger)]/40 hover:bg-[var(--danger)]/10 text-[var(--danger)]"
      : "border-[var(--border)] bg-[var(--surface-2)] hover:bg-[var(--surface)]";

  return (
    <div className="flex items-start gap-3 py-3 border-b border-[var(--border)] last:border-0">
      <div className="flex-1 min-w-0">
        <div className="text-sm font-medium">{label}</div>
        {description && <div className="text-xs text-[var(--muted)] mt-0.5">{description}</div>}
        {m.isSuccess && (
          <details className="text-xs mt-1">
            <summary className="text-[var(--accent)] cursor-pointer">résultat</summary>
            <pre className="mt-1 bg-[var(--surface-2)] rounded p-2 font-mono text-[10px] max-h-40 overflow-auto">
              {JSON.stringify(m.data, null, 2)}
            </pre>
          </details>
        )}
        {m.isError && (
          <div className="text-xs text-[var(--danger)] mt-1">
            {m.error instanceof ApiError ? JSON.stringify(m.error.body) : String(m.error)}
          </div>
        )}
      </div>
      <button
        onClick={() => m.mutate()}
        disabled={m.isPending}
        className={cn(
          "text-xs px-3 py-1.5 rounded border min-w-[110px] flex items-center justify-center gap-1.5",
          tone,
          "disabled:opacity-60",
        )}
      >
        {m.isPending ? (
          <><Loader2 className="size-3 animate-spin" /> En cours…</>
        ) : m.isSuccess ? (
          <><CheckCircle2 className="size-3 text-[var(--accent)]" /> Terminé</>
        ) : m.isError ? (
          <><AlertCircle className="size-3" /> Réessayer</>
        ) : (
          "Lancer"
        )}
      </button>
    </div>
  );
}
