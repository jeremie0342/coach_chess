"use client";

import { useState } from "react";

const START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";

export function FenInput({
  value,
  onChange,
  placeholder = START,
}: {
  value: string;
  onChange: (fen: string) => void;
  placeholder?: string;
}) {
  const [draft, setDraft] = useState(value);
  return (
    <div className="flex gap-2">
      <input
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        placeholder={placeholder}
        className="flex-1 bg-[var(--surface-2)] border rounded px-3 py-2 text-xs font-mono"
      />
      <button
        onClick={() => onChange(draft.trim() || placeholder)}
        className="text-xs px-3 py-2 rounded bg-[var(--accent)] text-black font-medium"
      >
        Charger
      </button>
      <button
        onClick={() => { setDraft(START); onChange(START); }}
        className="text-xs px-3 py-2 rounded border bg-[var(--surface-2)] hover:bg-[var(--surface)]"
      >
        Reset
      </button>
    </div>
  );
}
