"""DGT electronic chess board reader.

DGT (Digital Game Technology) boards are the standard tournament e-boards.
They communicate over USB serial — on Windows they appear as a virtual
COM port via the FTDI driver. The protocol is documented in DGT's official
spec (DGTProtocol.pdf, freely available on dgtprojects.com).

We implement the minimum to:
  - Auto-detect a connected DGT board (by FTDI VID:PID or description)
  - Send DGT_SEND_BRD (0x42) and parse the 67-byte DGT_BOARD_DUMP reply
  - Convert the 64 piece codes into a chess.Board / FEN
  - Optional mock mode for testing without hardware

Important caveats:
  - Side-to-move is NOT in the board dump (a static piece map). We infer it
    by tracking moves over time, or the caller supplies it.
  - Castling rights and en-passant cannot be derived from the piece map.

Wiring into the rest of the project: the CLI can stream FENs to
POST /api/v1/coach/live_debrief for an auto-debrief at the end of the game.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import chess

try:
    import serial
    from serial.tools import list_ports
    _HAS_PYSERIAL = True
except ImportError:
    _HAS_PYSERIAL = False

logger = logging.getLogger(__name__)


# --- DGT commands ---
DGT_SEND_RESET = 0x40
DGT_SEND_CLK = 0x41
DGT_SEND_BRD = 0x42
DGT_SEND_UPDATE = 0x43
DGT_SEND_UPDATE_BRD = 0x44
DGT_SEND_VERSION = 0x4D
DGT_SEND_TRADEMARK = 0x4C

# --- DGT message headers ---
DGT_BOARD_DUMP = 0x86
DGT_VERSION = 0x91

# --- Piece codes returned by the board ---
PIECE_CODES = {
    0x00: None,                          # empty
    0x01: chess.Piece(chess.PAWN, chess.WHITE),
    0x02: chess.Piece(chess.ROOK, chess.WHITE),
    0x03: chess.Piece(chess.KNIGHT, chess.WHITE),
    0x04: chess.Piece(chess.BISHOP, chess.WHITE),
    0x05: chess.Piece(chess.KING, chess.WHITE),
    0x06: chess.Piece(chess.QUEEN, chess.WHITE),
    0x07: chess.Piece(chess.PAWN, chess.BLACK),
    0x08: chess.Piece(chess.ROOK, chess.BLACK),
    0x09: chess.Piece(chess.KNIGHT, chess.BLACK),
    0x0A: chess.Piece(chess.BISHOP, chess.BLACK),
    0x0B: chess.Piece(chess.KING, chess.BLACK),
    0x0C: chess.Piece(chess.QUEEN, chess.BLACK),
}


@dataclass
class DgtSnapshot:
    fen: str
    board: chess.Board
    raw_bytes: bytes
    timestamp: float


def find_dgt_port() -> str | None:
    """Auto-detect a DGT board on the USB bus. Returns the COM port or None.

    DGT typically uses an FTDI USB-serial chip (VID 0x0403). The description
    string usually contains "DGT" when the driver is installed.
    """
    if not _HAS_PYSERIAL:
        return None
    for p in list_ports.comports():
        if p.vid == 0x0403:    # FTDI generic — could be a DGT
            desc = (p.description or "").upper()
            if "DGT" in desc or "FT232" in desc:
                return p.device
    # Fallback: any FTDI device
    for p in list_ports.comports():
        if p.vid == 0x0403:
            return p.device
    return None


class DgtBoard:
    def __init__(self, port: str | None = None, baudrate: int = 9600):
        if not _HAS_PYSERIAL:
            raise RuntimeError("pyserial not installed")
        self._port_name = port
        self._baudrate = baudrate
        self._ser: serial.Serial | None = None

    def connect(self) -> None:
        port = self._port_name or find_dgt_port()
        if not port:
            raise RuntimeError("No DGT board detected; pass port=COMx explicitly")
        self._ser = serial.Serial(port, self._baudrate, timeout=1.0)
        # Reset + drain
        self._ser.write(bytes([DGT_SEND_RESET]))
        time.sleep(0.2)
        self._ser.reset_input_buffer()
        logger.info("DGT board connected on %s", port)

    def close(self) -> None:
        if self._ser:
            try:
                self._ser.close()
            except Exception:
                pass
            self._ser = None

    def _send(self, cmd: int) -> None:
        if not self._ser:
            raise RuntimeError("not connected")
        self._ser.write(bytes([cmd]))

    def _read_response(self, expected_header: int) -> bytes:
        if not self._ser:
            raise RuntimeError("not connected")
        # DGT messages: header(1) + length(2 big endian) + payload
        head = self._ser.read(1)
        if not head:
            raise TimeoutError("no response from board")
        if head[0] != expected_header:
            # Drain a few bytes then raise — sometimes the board responds with
            # stale chunks we should skip
            self._ser.read(64)
            raise IOError(f"unexpected header 0x{head[0]:02X} (want 0x{expected_header:02X})")
        length_bytes = self._ser.read(2)
        if len(length_bytes) != 2:
            raise IOError("truncated length header")
        msg_len = (length_bytes[0] << 7) | length_bytes[1]   # DGT 2-byte length is 7-bit each
        payload_len = max(0, msg_len - 3)
        payload = self._ser.read(payload_len)
        if len(payload) != payload_len:
            raise IOError(f"truncated payload ({len(payload)}/{payload_len})")
        return payload

    def read_position(self) -> DgtSnapshot:
        if not self._ser:
            raise RuntimeError("not connected")
        self._send(DGT_SEND_BRD)
        payload = self._read_response(DGT_BOARD_DUMP)
        if len(payload) != 64:
            raise IOError(f"expected 64 squares, got {len(payload)}")
        board = self._payload_to_board(payload)
        return DgtSnapshot(
            fen=board.fen(),
            board=board,
            raw_bytes=payload,
            timestamp=time.time(),
        )

    @staticmethod
    def _payload_to_board(payload: bytes) -> chess.Board:
        # DGT order: a8 b8 c8 ... h8, a7 ... h7, ..., a1 ... h1
        board = chess.Board.empty()
        for i, byte in enumerate(payload):
            piece = PIECE_CODES.get(byte)
            if piece is None:
                continue
            # i = 0 → a8 (file=0, rank=7); i = 7 → h8; i = 8 → a7 ...
            file = i % 8
            rank = 7 - (i // 8)
            board.set_piece_at(chess.square(file, rank), piece)
        # Default castling rights stay empty (we can't infer them)
        return board


# ---- Mock board ----

class MockDgtBoard(DgtBoard):
    """Stand-in for a real board: returns scripted positions in sequence.

    Useful for tests and demos when no hardware is plugged in.
    """
    def __init__(self, fens: list[str] | None = None):
        self._fens = fens or [chess.STARTING_FEN]
        self._idx = 0
        # Skip parent __init__ — we don't need pyserial
        self._ser = "mock"   # type: ignore[assignment]

    def connect(self) -> None:
        logger.info("MockDgtBoard connected (no hardware)")

    def close(self) -> None:
        pass

    def read_position(self) -> DgtSnapshot:
        fen = self._fens[min(self._idx, len(self._fens) - 1)]
        self._idx += 1
        board = chess.Board(fen)
        return DgtSnapshot(
            fen=board.fen(),
            board=board,
            raw_bytes=b"",
            timestamp=time.time(),
        )
