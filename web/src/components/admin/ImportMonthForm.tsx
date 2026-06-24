"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { api, ApiError } from "@/lib/api";

const MONTHS = [
  "janvier", "février", "mars", "avril", "mai", "juin",
  "juillet", "août", "septembre", "octobre", "novembre", "décembre",
];

export function ImportMonthForm() {
  const now = new Date();
  const [year, setYear] = useState(now.getUTCFullYear());
  const [month, setMonth] = useState(now.getUTCMonth() + 1);

  const m = useMutation({
    mutationFn: () =>
      api("/import/chesscom/month", { method: "POST", query: { year, month } }),
  });

  return (
    <div className="py-3 border-b border-[var(--border)] last:border-0">
      <div className="text-sm font-medium">Importer un mois précis</div>
      <div className="text-xs text-[var(--muted)] mt-0.5">Plus rapide que l'import complet si tu veux juste rattraper un mois.</div>
      <div className="mt-3 flex flex-wrap gap-2 items-center">
        <select
          value={month}
          onChange={(e) => setMonth(Number(e.target.value))}
          className="bg-[var(--surface-2)] border rounded px-2 py-1.5 text-sm"
        >
          {MONTHS.map((label, i) => (
            <option key={i} value={i + 1}>{label}</option>
          ))}
        </select>
        <input
          type="number"
          min={2000}
          max={2100}
          value={year}
          onChange={(e) => setYear(Number(e.target.value))}
          className="bg-[var(--surface-2)] border rounded px-2 py-1.5 text-sm w-20 tabular-nums"
        />
        <button
          onClick={() => m.mutate()}
          disabled={m.isPending}
          className="text-xs px-3 py-1.5 rounded border bg-[var(--surface-2)] hover:bg-[var(--surface)] disabled:opacity-50 flex items-center gap-1.5"
        >
          {m.isPending && <Loader2 className="size-3 animate-spin" />}
          {m.isPending ? "Import..." : "Importer"}
        </button>
      </div>
      {m.isSuccess && (
        <pre className="mt-2 bg-[var(--surface-2)] rounded p-2 font-mono text-[10px] max-h-32 overflow-auto">
          {JSON.stringify(m.data, null, 2)}
        </pre>
      )}
      {m.isError && (
        <div className="text-xs text-[var(--danger)] mt-2">
          {m.error instanceof ApiError ? JSON.stringify(m.error.body) : String(m.error)}
        </div>
      )}
    </div>
  );
}
