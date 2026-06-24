"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Chessboard } from "react-chessboard";
import type { PieceDropHandlerArgs } from "react-chessboard";
import { Chess } from "chess.js";
import { AnimatePresence, motion } from "framer-motion";
import { FlipVertical2 } from "lucide-react";

export type BoardProps = {
  fen?: string;
  /** Initial orientation. Defaults to "white" so the 'a' file stays on the left
   *  regardless of which color the user plays. User can flip via the in-board
   *  button. */
  orientation?: "white" | "black";
  allowDragging?: boolean;
  /** Restrict drag/click selection to pieces of this color. */
  draggableColor?: "white" | "black";
  onMove?: (move: { from: string; to: string; promotion?: string }) => boolean;
  size?: number;
  lastMove?: { from: string; to: string } | null;
  highlightSquares?: string[];
  bestMove?: { from: string; to: string } | null;
  /** Hide the flip-board button (default: shown). */
  hideFlipButton?: boolean;
};

const STARTPOS = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";

const STYLE_LAST = { background: "rgba(127,176,105,0.30)" };
const STYLE_USER = { background: "rgba(106,166,255,0.30)" };
const STYLE_SELECTED = { background: "rgba(255,214,102,0.45)" };
const STYLE_LEGAL = {
  background:
    "radial-gradient(circle, rgba(0,0,0,0.32) 22%, transparent 23%)",
};
const STYLE_LEGAL_CAPTURE = {
  background:
    "radial-gradient(circle, transparent 58%, rgba(214,69,69,0.55) 60%, rgba(214,69,69,0.55) 64%, transparent 66%)",
};
const STYLE_CHECK = {
  background:
    "radial-gradient(circle, rgba(214,69,69,0.85) 30%, rgba(214,69,69,0.20) 60%, transparent 75%)",
};
const STYLE_WRONG = { background: "rgba(214,69,69,0.55)" };

export function Board({
  fen = STARTPOS,
  orientation = "white",
  allowDragging = true,
  draggableColor,
  onMove,
  size = 480,
  lastMove,
  highlightSquares,
  bestMove,
  hideFlipButton = false,
}: BoardProps) {
  // Local flip state — initial value comes from the prop but the user can
  // override it via the flip button. Stays in sync if the prop changes.
  const [boardOrientation, setBoardOrientation] = useState<"white" | "black">(orientation);
  useEffect(() => { setBoardOrientation(orientation); }, [orientation]);
  const flip = useCallback(() => {
    setBoardOrientation((o) => (o === "white" ? "black" : "white"));
  }, []);
  // --- Derive chess.js board from FEN (memoized for legality + game-state checks)
  const chess = useMemo(() => {
    try { return new Chess(fen); } catch { return null; }
  }, [fen]);

  const inCheck = chess?.inCheck() ?? false;
  const isCheckmate = chess?.isCheckmate() ?? false;
  const isStalemate = chess?.isStalemate() ?? false;
  const isDraw = !isCheckmate && (chess?.isDraw() ?? false);

  const kingSquare = useMemo(() => {
    if (!chess || !inCheck) return null;
    const turn = chess.turn(); // 'w' | 'b'
    const board = chess.board();
    for (let r = 0; r < 8; r++) {
      for (let f = 0; f < 8; f++) {
        const p = board[r][f];
        if (p && p.type === "k" && p.color === turn) {
          return "abcdefgh"[f] + (8 - r);
        }
      }
    }
    return null;
  }, [chess, inCheck]);

  // --- Click-to-move selection state
  const [selected, setSelected] = useState<string | null>(null);
  const [legalTargets, setLegalTargets] = useState<{ to: string; capture: boolean }[]>([]);
  const [wrongSquare, setWrongSquare] = useState<string | null>(null);
  const wrongTimer = useRef<number | null>(null);

  // Reset selection if FEN changes (new puzzle / move applied)
  useEffect(() => {
    setSelected(null);
    setLegalTargets([]);
  }, [fen]);

  const flashWrong = useCallback((sq: string) => {
    if (wrongTimer.current) window.clearTimeout(wrongTimer.current);
    setWrongSquare(sq);
    wrongTimer.current = window.setTimeout(() => setWrongSquare(null), 350);
  }, []);

  useEffect(() => () => {
    if (wrongTimer.current) window.clearTimeout(wrongTimer.current);
  }, []);

  const canSelect = useCallback((square: string): boolean => {
    if (!chess) return false;
    const piece = chess.get(square as never);
    if (!piece) return false;
    if (draggableColor) {
      return draggableColor === "white" ? piece.color === "w" : piece.color === "b";
    }
    return piece.color === chess.turn();
  }, [chess, draggableColor]);

  const computeTargets = useCallback((sq: string) => {
    if (!chess) return [];
    try {
      const moves = chess.moves({ square: sq as never, verbose: true }) as Array<{
        to: string; flags: string; captured?: string;
      }>;
      const seen = new Set<string>();
      const out: { to: string; capture: boolean }[] = [];
      for (const m of moves) {
        if (seen.has(m.to)) continue;
        seen.add(m.to);
        out.push({ to: m.to, capture: !!m.captured || m.flags.includes("e") });
      }
      return out;
    } catch { return []; }
  }, [chess]);

  const trySubmit = useCallback((from: string, to: string): boolean => {
    if (!onMove) return false;
    // chess.js will reject illegal moves; we delegate validity to onMove (which builds
    // its own Chess instance). The Board only needs to know if it should clear selection.
    const ok = onMove({ from, to, promotion: "q" });
    return ok;
  }, [onMove]);

  const handleSquareClick = ({ square }: { square: string; piece?: unknown }) => {
    if (!chess) return;

    // Second click: try to move from selected to clicked square
    if (selected) {
      if (square === selected) {
        setSelected(null);
        setLegalTargets([]);
        return;
      }
      const target = legalTargets.find((t) => t.to === square);
      if (target) {
        const ok = trySubmit(selected, square);
        setSelected(null);
        setLegalTargets([]);
        if (!ok) flashWrong(selected);
        return;
      }
      // Clicked a non-legal square — if it's our own piece, switch selection.
      if (canSelect(square)) {
        setSelected(square);
        setLegalTargets(computeTargets(square));
        return;
      }
      // Otherwise: invalid target → flash + clear
      flashWrong(square);
      setSelected(null);
      setLegalTargets([]);
      return;
    }

    // First click: must select our own piece
    if (canSelect(square)) {
      setSelected(square);
      setLegalTargets(computeTargets(square));
    }
  };

  const handleDrop = ({ sourceSquare, targetSquare }: PieceDropHandlerArgs) => {
    if (!targetSquare || !onMove) return false;
    setSelected(null);
    setLegalTargets([]);
    const ok = onMove({ from: sourceSquare, to: targetSquare, promotion: "q" });
    if (!ok) flashWrong(sourceSquare);
    return ok;
  };

  // --- Compose square styles in priority order: last < highlight < legal < selected < check < wrong
  const squareStyles = useMemo(() => {
    const styles: Record<string, React.CSSProperties> = {};
    if (lastMove) {
      styles[lastMove.from] = STYLE_LAST;
      styles[lastMove.to] = STYLE_LAST;
    }
    if (highlightSquares) {
      for (const sq of highlightSquares) styles[sq] = STYLE_USER;
    }
    for (const t of legalTargets) {
      styles[t.to] = t.capture ? STYLE_LEGAL_CAPTURE : STYLE_LEGAL;
    }
    if (selected) styles[selected] = STYLE_SELECTED;
    if (kingSquare) styles[kingSquare] = STYLE_CHECK;
    if (wrongSquare) styles[wrongSquare] = STYLE_WRONG;
    return styles;
  }, [lastMove, highlightSquares, legalTargets, selected, kingSquare, wrongSquare]);

  const arrows = useMemo(() => {
    if (!bestMove) return undefined;
    return [{
      startSquare: bestMove.from,
      endSquare: bestMove.to,
      color: "rgba(127,176,105,0.7)",
    }];
  }, [bestMove]);

  const canDragPiece = useMemo(() => {
    if (!draggableColor) return undefined;
    return ({ piece }: { piece?: { pieceType?: string } | string | null }) => {
      const code = typeof piece === "string" ? piece : piece?.pieceType ?? "";
      if (!code) return false;
      return draggableColor === "white" ? code[0] === "w" : code[0] === "b";
    };
  }, [draggableColor]);

  return (
    <div style={{ width: "100%", maxWidth: size }} className="relative">
      <Chessboard
        options={{
          position: fen,
          boardOrientation,
          allowDragging,
          canDragPiece,
          onPieceDrop: handleDrop,
          onSquareClick: handleSquareClick,
          squareStyles,
          arrows,
          boardStyle: {
            borderRadius: 8,
            boxShadow: "0 8px 24px rgba(0,0,0,0.4)",
            transition: "box-shadow 200ms ease",
          },
          animationDurationInMs: 180,
        }}
      />

      {!hideFlipButton && (
        <button
          type="button"
          onClick={flip}
          aria-label="Inverser l'échiquier"
          title="Inverser l'échiquier"
          className="absolute -top-2 -right-2 z-10 size-7 rounded-full bg-[var(--surface)] border border-[var(--border)] flex items-center justify-center text-[var(--muted)] hover:text-[var(--foreground)] hover:bg-[var(--surface-2)] shadow"
        >
          <FlipVertical2 className="size-3.5" />
        </button>
      )}

      <AnimatePresence>
        {isCheckmate && (
          <motion.div
            key="mate"
            initial={{ opacity: 0, scale: 0.85 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.9 }}
            transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
            className="pointer-events-none absolute inset-0 flex items-center justify-center"
          >
            <div className="rounded-xl bg-[var(--danger)]/85 text-white px-6 py-3 text-2xl font-bold uppercase tracking-widest shadow-2xl">
              Échec et mat
            </div>
          </motion.div>
        )}

        {!isCheckmate && inCheck && (
          <motion.div
            key={`check-${kingSquare}`}
            initial={{ opacity: 0, y: -6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="pointer-events-none absolute top-2 left-1/2 -translate-x-1/2"
          >
            <div className="rounded-md bg-[var(--danger)]/85 text-white px-3 py-1 text-xs font-semibold uppercase tracking-widest shadow-lg">
              Échec
            </div>
          </motion.div>
        )}

        {!isCheckmate && (isStalemate || isDraw) && (
          <motion.div
            key="draw"
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.25 }}
            className="pointer-events-none absolute inset-0 flex items-center justify-center"
          >
            <div className="rounded-xl bg-[var(--muted)]/90 text-white px-5 py-2 text-lg font-semibold uppercase tracking-widest shadow-2xl">
              {isStalemate ? "Pat" : "Nulle"}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
