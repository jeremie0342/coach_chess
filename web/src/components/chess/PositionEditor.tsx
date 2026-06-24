"use client";

import { useState, useMemo, useCallback } from "react";
import { Chess } from "chess.js";
import { Chessboard } from "react-chessboard";
import { Trash2, RotateCcw, Eraser } from "lucide-react";
import { cn } from "@/lib/utils";

const START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";
const EMPTY_FEN = "8/8/8/8/8/8/8/8 w - - 0 1";

type PieceCode = "P" | "N" | "B" | "R" | "Q" | "K" | "p" | "n" | "b" | "r" | "q" | "k";

const PIECE_GLYPHS: Record<PieceCode, string> = {
  K: "♔", Q: "♕", R: "♖", B: "♗", N: "♘", P: "♙",
  k: "♚", q: "♛", r: "♜", b: "♝", n: "♞", p: "♟",
};

const WHITE_PIECES: PieceCode[] = ["K", "Q", "R", "B", "N", "P"];
const BLACK_PIECES: PieceCode[] = ["k", "q", "r", "b", "n", "p"];

type FenParts = {
  board: string;
  turn: "w" | "b";
  castling: string;
  enPassant: string;
  halfmove: string;
  fullmove: string;
};

function parseFen(fen: string): FenParts {
  const p = fen.trim().split(/\s+/);
  return {
    board: p[0] ?? "8/8/8/8/8/8/8/8",
    turn: (p[1] === "b" ? "b" : "w") as "w" | "b",
    castling: p[2] ?? "-",
    enPassant: p[3] ?? "-",
    halfmove: p[4] ?? "0",
    fullmove: p[5] ?? "1",
  };
}

function buildFen(parts: FenParts): string {
  return `${parts.board} ${parts.turn} ${parts.castling} ${parts.enPassant} ${parts.halfmove} ${parts.fullmove}`;
}

/** Convert a board placement string to an 8x8 grid (rank 8 first). */
function boardToGrid(board: string): (PieceCode | null)[][] {
  const grid: (PieceCode | null)[][] = [];
  for (const row of board.split("/")) {
    const r: (PieceCode | null)[] = [];
    for (const ch of row) {
      if (/\d/.test(ch)) {
        for (let i = 0; i < parseInt(ch, 10); i++) r.push(null);
      } else {
        r.push(ch as PieceCode);
      }
    }
    while (r.length < 8) r.push(null);
    grid.push(r.slice(0, 8));
  }
  while (grid.length < 8) grid.push(Array(8).fill(null));
  return grid.slice(0, 8);
}

function gridToBoard(grid: (PieceCode | null)[][]): string {
  return grid.map((row) => {
    let s = "";
    let blanks = 0;
    for (const c of row) {
      if (c === null) {
        blanks++;
      } else {
        if (blanks > 0) { s += String(blanks); blanks = 0; }
        s += c;
      }
    }
    if (blanks > 0) s += String(blanks);
    return s;
  }).join("/");
}

function fileRankToCoords(square: string): { file: number; rank: number } {
  const file = square.charCodeAt(0) - "a".charCodeAt(0);  // 0..7 (a=0)
  const rankFromBottom = parseInt(square[1], 10);          // 1..8
  const rank = 8 - rankFromBottom;                          // 0..7 (rank 8 row = 0)
  return { file, rank };
}

export function PositionEditor({
  value,
  onChange,
  size = 360,
}: {
  value: string;
  onChange: (fen: string) => void;
  size?: number;
}) {
  const parts = useMemo(() => parseFen(value), [value]);
  const [selected, setSelected] = useState<PieceCode | null>(null);
  const [eraseMode, setEraseMode] = useState(false);

  const placePiece = useCallback((square: string, piece: PieceCode | null) => {
    const grid = boardToGrid(parts.board);
    const { file, rank } = fileRankToCoords(square);
    grid[rank][file] = piece;
    onChange(buildFen({ ...parts, board: gridToBoard(grid) }));
  }, [parts, onChange]);

  const handleSquareClick = useCallback(({ square }: { square: string }) => {
    if (eraseMode) {
      placePiece(square, null);
      return;
    }
    if (selected) {
      placePiece(square, selected);
    }
  }, [selected, eraseMode, placePiece]);

  const handleDrop = useCallback(
    ({ sourceSquare, targetSquare }: { sourceSquare: string; targetSquare: string | null }) => {
      if (!targetSquare || sourceSquare === targetSquare) return false;
      const grid = boardToGrid(parts.board);
      const src = fileRankToCoords(sourceSquare);
      const dst = fileRankToCoords(targetSquare);
      const piece = grid[src.rank][src.file];
      if (!piece) return false;
      grid[src.rank][src.file] = null;
      grid[dst.rank][dst.file] = piece;
      onChange(buildFen({ ...parts, board: gridToBoard(grid) }));
      return true;
    }, [parts, onChange],
  );

  const setTurn = (t: "w" | "b") => onChange(buildFen({ ...parts, turn: t }));
  const toggleCastling = (c: string) => {
    const has = parts.castling.includes(c);
    let next = has ? parts.castling.replace(c, "") : (parts.castling === "-" ? c : parts.castling + c);
    if (!next) next = "-";
    onChange(buildFen({ ...parts, castling: next }));
  };

  const validity = useMemo(() => {
    try {
      const c = new Chess();
      c.load(value);
      return { ok: true, msg: "Position légale" };
    } catch (e) {
      return { ok: false, msg: String((e as Error).message ?? e) };
    }
  }, [value]);

  return (
    <div className="space-y-3">
      {/* Palette pièces noires */}
      <div className="flex items-center justify-between gap-2">
        <div className="text-[10px] uppercase tracking-wider text-[var(--muted)]">Noirs</div>
        <div className="flex gap-1">
          {BLACK_PIECES.map((p) => (
            <PieceButton key={p} piece={p} active={selected === p && !eraseMode} onClick={() => { setSelected(p); setEraseMode(false); }} />
          ))}
        </div>
      </div>

      <div style={{ width: "100%", maxWidth: size, margin: "0 auto" }}>
        <Chessboard
          options={{
            position: parts.board,
            allowDragging: true,
            onPieceDrop: handleDrop as never,
            onSquareClick: handleSquareClick,
            boardStyle: { borderRadius: 8, boxShadow: "0 4px 12px rgba(0,0,0,0.3)" },
          }}
        />
      </div>

      {/* Palette pièces blanches */}
      <div className="flex items-center justify-between gap-2">
        <div className="text-[10px] uppercase tracking-wider text-[var(--muted)]">Blancs</div>
        <div className="flex gap-1">
          {WHITE_PIECES.map((p) => (
            <PieceButton key={p} piece={p} active={selected === p && !eraseMode} onClick={() => { setSelected(p); setEraseMode(false); }} />
          ))}
        </div>
      </div>

      {/* Outils */}
      <div className="flex flex-wrap gap-2 items-center">
        <button
          onClick={() => { setEraseMode((v) => !v); setSelected(null); }}
          className={cn(
            "text-xs px-3 py-1.5 rounded border inline-flex items-center gap-1.5",
            eraseMode ? "bg-[var(--danger)] text-white border-[var(--danger)]" : "bg-[var(--surface-2)] hover:bg-[var(--surface)]",
          )}
          title="Cliquez sur une case pour la vider"
        >
          <Eraser className="size-3" /> {eraseMode ? "Mode gomme ON" : "Gomme"}
        </button>
        <button
          onClick={() => onChange(START_FEN)}
          className="text-xs px-3 py-1.5 rounded border bg-[var(--surface-2)] hover:bg-[var(--surface)] inline-flex items-center gap-1.5"
        >
          <RotateCcw className="size-3" /> Position initiale
        </button>
        <button
          onClick={() => onChange(EMPTY_FEN)}
          className="text-xs px-3 py-1.5 rounded border bg-[var(--surface-2)] hover:bg-[var(--surface)] inline-flex items-center gap-1.5"
        >
          <Trash2 className="size-3" /> Vider
        </button>
      </div>

      {/* Trait + roques */}
      <div className="grid grid-cols-2 gap-3 text-xs">
        <div>
          <div className="text-[var(--muted)] uppercase tracking-wider mb-1">Trait aux</div>
          <div className="flex gap-1">
            {(["w", "b"] as const).map((t) => (
              <button
                key={t}
                onClick={() => setTurn(t)}
                className={cn(
                  "text-xs px-3 py-1.5 rounded border flex-1",
                  parts.turn === t ? "bg-[var(--accent)] text-black border-[var(--accent)]" : "bg-[var(--surface-2)] text-[var(--muted)]",
                )}
              >
                {t === "w" ? "Blancs" : "Noirs"}
              </button>
            ))}
          </div>
        </div>
        <div>
          <div className="text-[var(--muted)] uppercase tracking-wider mb-1">Roques possibles</div>
          <div className="flex gap-1 flex-wrap">
            {[
              { c: "K", label: "♔ O-O" },
              { c: "Q", label: "♔ O-O-O" },
              { c: "k", label: "♚ O-O" },
              { c: "q", label: "♚ O-O-O" },
            ].map(({ c, label }) => (
              <button
                key={c}
                onClick={() => toggleCastling(c)}
                className={cn(
                  "text-xs px-2 py-1 rounded border font-mono",
                  parts.castling.includes(c)
                    ? "bg-[var(--accent)]/20 text-[var(--accent)] border-[var(--accent)]/40"
                    : "bg-[var(--surface-2)] text-[var(--muted)]",
                )}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Validity */}
      <div className={cn("text-xs", validity.ok ? "text-[var(--accent)]" : "text-[var(--danger)]")}>
        {validity.ok ? "✓ Position valide" : `⚠ ${validity.msg}`}
      </div>
    </div>
  );
}

function PieceButton({ piece, active, onClick }: { piece: PieceCode; active: boolean; onClick: () => void }) {
  const isWhite = piece === piece.toUpperCase();
  return (
    <button
      onClick={onClick}
      className={cn(
        "w-9 h-9 rounded border text-2xl leading-none flex items-center justify-center transition-all",
        active
          ? "border-[var(--accent)] bg-[var(--accent)]/20 scale-110"
          : "border-[var(--border)] bg-[var(--surface-2)] hover:border-[var(--accent)]/60",
        isWhite ? "text-white" : "text-black bg-[var(--foreground)]/90",
      )}
      title={`Placer ${piece}`}
    >
      <span style={{ textShadow: isWhite ? "0 0 2px rgba(0,0,0,0.6)" : undefined }}>
        {PIECE_GLYPHS[piece]}
      </span>
    </button>
  );
}
