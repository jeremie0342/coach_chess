"use client";

import { Loader2, CheckCircle2, AlertCircle } from "lucide-react";
import { useAsyncJob } from "@/hooks/useAsyncJob";
import { cn } from "@/lib/utils";

export function JobButton<TBody = Record<string, unknown>>({
  label,
  description,
  path,
  body,
  variant = "default",
  onComplete,
}: {
  label: string;
  description?: string;
  path: string;
  body?: TBody;
  variant?: "default" | "danger";
  onComplete?: (result: unknown) => void;
}) {
  const job = useAsyncJob<TBody>(path);

  const handleClick = async () => {
    if (job.isRunning) return;
    await job.start(body);
  };

  const tone =
    variant === "danger"
      ? "border-[var(--danger)]/40 hover:bg-[var(--danger)]/10 text-[var(--danger)]"
      : "border-[var(--border)] bg-[var(--surface-2)] hover:bg-[var(--surface)]";

  return (
    <div className="flex items-start gap-3 py-3 border-b border-[var(--border)] last:border-0">
      <div className="flex-1 min-w-0">
        <div className="text-sm font-medium">{label}</div>
        {description && <div className="text-xs text-[var(--muted)] mt-0.5">{description}</div>}
        {job.jobId && (
          <div className="text-[10px] text-[var(--muted)] mt-1 font-mono">
            job {job.jobId.slice(0, 8)}… · {job.status}
          </div>
        )}
        {job.isComplete && job.result != null && (
          <details className="text-xs mt-1">
            <summary className="text-[var(--accent)] cursor-pointer">résultat</summary>
            <pre className="mt-1 bg-[var(--surface-2)] rounded p-2 font-mono text-[10px] max-h-40 overflow-auto">
              {JSON.stringify(job.result, null, 2)}
            </pre>
          </details>
        )}
        {job.error && <div className="text-xs text-[var(--danger)] mt-1">{job.error}</div>}
      </div>
      <button
        onClick={handleClick}
        disabled={job.isRunning}
        className={cn(
          "text-xs px-3 py-1.5 rounded border min-w-[110px] flex items-center justify-center gap-1.5",
          tone,
          "disabled:opacity-60",
        )}
      >
        {job.isRunning ? (
          <><Loader2 className="size-3 animate-spin" /> En cours…</>
        ) : job.isComplete ? (
          <><CheckCircle2 className="size-3 text-[var(--accent)]" /> Terminé</>
        ) : job.isFailed ? (
          <><AlertCircle className="size-3" /> Réessayer</>
        ) : (
          "Lancer"
        )}
      </button>
    </div>
  );
}
