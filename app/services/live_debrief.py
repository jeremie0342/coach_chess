"""Live PGN debrief: paste a PGN, get an immediate coaching report.

Pipeline:
  1. Parse PGN, derive my_color (explicit param > White/Black header match
     against my chesscom_username).
  2. Upsert as a Game with source='manual_pgn' and external_id=sha1(pgn).
     Idempotent: re-pasting the same PGN returns the same Game.
  3. Persist Moves (FEN before/after each ply).
  4. Run Stockfish analysis on all of MY moves only (skip opponent moves and
     book moves), at the requested depth.
  5. Produce a structured report:
        - per-phase mistake counts
        - top N blunders with LLM explanations
        - generated puzzles
"""
from __future__ import annotations

import hashlib
import io
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

import chess
import chess.pgn
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Exercise, Game, Move, MoveAnalysis, Player
from app.models.analysis import MoveQuality
from app.models.game import GameResult, TimeControlCategory
from app.services.analyzer import analyze_game
from app.services.coach.explainer import explain_move
from app.services.exercises.generator import generate_for_player
from app.services.openings.out_of_book import compute_out_of_book_for_game
from app.services.pgn_importer import _get_or_create_player, _parse_result
from app.services.stockfish import get_engine

logger = logging.getLogger(__name__)


@dataclass
class PhaseStats:
    blunders: int = 0
    mistakes: int = 0
    inaccuracies: int = 0


@dataclass
class DebriefItem:
    ply: int
    side: str
    played_san: str
    best_san: str | None
    quality: str | None
    cp_loss: int | None
    explanation: str
    exercise_id: int | None = None


@dataclass
class DebriefReport:
    game_id: int
    pgn_hash: str
    me_username: str
    my_color: str
    opening: str | None
    eco: str | None
    my_out_of_book_ply: int | None
    moves_analyzed: int
    phases: dict[str, PhaseStats]
    top_blunders: list[DebriefItem] = field(default_factory=list)
    exercises_generated: int = 0
    elapsed_s: float = 0.0


def _pgn_hash(pgn_text: str) -> str:
    return hashlib.sha1(pgn_text.strip().encode("utf-8")).hexdigest()


def _classify_phase(ply: int) -> str:
    if ply <= 20:
        return "opening"
    if ply <= 40:
        return "middlegame"
    return "endgame"


def _derive_my_color(
    pgn_game: chess.pgn.Game,
    my_username: str,
    explicit: str | None,
) -> str | None:
    if explicit in ("white", "black"):
        return explicit
    headers = pgn_game.headers
    if headers.get("White", "").lower() == my_username.lower():
        return "white"
    if headers.get("Black", "").lower() == my_username.lower():
        return "black"
    return None


async def _ingest_pgn(
    session: AsyncSession, pgn_text: str, me: Player, my_color_hint: str | None
) -> tuple[Game, str]:
    """Persist (or return existing) Game built from a manual PGN."""
    pgn_hash = _pgn_hash(pgn_text)
    external_id = f"pgn:{pgn_hash}"
    existing = (await session.execute(
        select(Game).where(Game.external_id == external_id)
    )).scalar_one_or_none()
    if existing:
        return existing, "existing"

    pgn_game = chess.pgn.read_game(io.StringIO(pgn_text))
    if pgn_game is None:
        raise ValueError("Could not parse PGN")
    headers = pgn_game.headers

    derived_color = _derive_my_color(pgn_game, me.chesscom_username, my_color_hint)
    # If we still don't know — assume the player is me by header name
    white_name = headers.get("White") or "?"
    black_name = headers.get("Black") or "?"
    if derived_color == "white":
        white_name = me.chesscom_username
    elif derived_color == "black":
        black_name = me.chesscom_username

    white_player = await _get_or_create_player(
        session, white_name, is_me=(derived_color == "white")
    )
    black_player = await _get_or_create_player(
        session, black_name, is_me=(derived_color == "black")
    )

    def _safe_int(v: object) -> int | None:
        try:
            return int(v)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None

    def _tc() -> TimeControlCategory | None:
        try:
            return TimeControlCategory((headers.get("TimeClass") or "").lower())
        except (ValueError, TypeError):
            return None

    game = Game(
        external_id=external_id,
        source="manual_pgn",
        url=headers.get("Site"),
        white_player_id=white_player.id,
        black_player_id=black_player.id,
        white_rating=_safe_int(headers.get("WhiteElo")),
        black_rating=_safe_int(headers.get("BlackElo")),
        result=_parse_result(headers.get("Result")),
        termination=headers.get("Termination"),
        time_control=headers.get("TimeControl"),
        time_class=_tc(),
        rated=False,
        eco=headers.get("ECO"),
        opening_name=headers.get("Opening") or headers.get("ECOUrl"),
        pgn=pgn_text,
        analysis_status="pending",
    )
    session.add(game)
    await session.flush()

    # Walk moves
    board = pgn_game.board()
    node = pgn_game
    ply = 0
    while node.variations:
        nxt = node.variation(0)
        mv = nxt.move
        if mv is None:
            break
        fen_before = board.fen()
        san = board.san(mv)
        move_number = board.fullmove_number
        is_white = board.turn == chess.WHITE
        board.push(mv)
        ply += 1
        session.add(Move(
            game_id=game.id,
            ply=ply,
            move_number=move_number,
            is_white=is_white,
            san=san,
            uci=mv.uci(),
            fen_before=fen_before,
            fen_after=board.fen(),
        ))
        node = nxt
    game.ply_count = ply
    await session.commit()
    return game, "new"


async def live_debrief(
    session: AsyncSession,
    pgn_text: str,
    *,
    my_color: str | None = None,
    depth: int | None = None,
    max_blunders: int = 5,
    generate_puzzles: bool = True,
    explain_with_llm: bool = True,
) -> DebriefReport:
    started = time.perf_counter()

    me = (await session.execute(select(Player).where(Player.is_me.is_(True)))).scalar_one_or_none()
    if not me:
        raise ValueError("No 'is_me' player in DB. Run a Chess.com import first.")

    game, _status = await _ingest_pgn(session, pgn_text, me, my_color_hint=my_color)

    # Compute opening / out-of-book
    await compute_out_of_book_for_game(session, game, me_player_id=me.id)
    await session.commit()

    # Analyze with Stockfish — single shared engine
    engine = await get_engine()
    await analyze_game(session, game, engine, depth=depth, force=False)

    # Per-phase stats over MY moves
    my_is_white = game.white_player_id == me.id
    rows = list((await session.execute(
        select(Move.ply, MoveAnalysis.quality, MoveAnalysis.cp_loss)
        .join(MoveAnalysis, MoveAnalysis.move_id == Move.id)
        .where(Move.game_id == game.id)
        .where(Move.is_white == my_is_white)
    )).all())
    phases: dict[str, PhaseStats] = {
        "opening": PhaseStats(),
        "middlegame": PhaseStats(),
        "endgame": PhaseStats(),
    }
    for ply, q, _cp in rows:
        ph = phases[_classify_phase(ply)]
        if q == MoveQuality.BLUNDER:
            ph.blunders += 1
        elif q == MoveQuality.MISTAKE:
            ph.mistakes += 1
        elif q == MoveQuality.INACCURACY:
            ph.inaccuracies += 1

    # Top blunders with LLM explanation
    worst_q = (
        select(Move.ply, MoveAnalysis.cp_loss, MoveAnalysis.quality)
        .join(MoveAnalysis, MoveAnalysis.move_id == Move.id)
        .where(Move.game_id == game.id)
        .where(Move.is_white == my_is_white)
        .where(MoveAnalysis.quality.in_((MoveQuality.BLUNDER, MoveQuality.MISTAKE)))
        .order_by(MoveAnalysis.cp_loss.desc().nullslast())
        .limit(max_blunders)
    )
    worst_plies = [r[0] for r in (await session.execute(worst_q)).all()]
    items: list[DebriefItem] = []
    for ply in worst_plies:
        explanation = ""
        played_san = best_san = quality = None
        cp_loss = None
        if explain_with_llm:
            r = await explain_move(session, game, ply, use_cache=True)
            if "error" in r:
                continue
            explanation = r["explanation"]
            played_san = r["played"]
            best_san = r.get("best")
            quality = r.get("quality")
            cp_loss = r.get("cp_loss")
        else:
            mv = (await session.execute(
                select(Move).where(Move.game_id == game.id, Move.ply == ply)
            )).scalar_one()
            ma = (await session.execute(
                select(MoveAnalysis).where(MoveAnalysis.move_id == mv.id)
            )).scalar_one()
            played_san, best_san = mv.san, ma.best_move_san
            quality = str(ma.quality) if ma.quality else None
            cp_loss = ma.cp_loss

        items.append(DebriefItem(
            ply=ply,
            side="white" if my_is_white else "black",
            played_san=played_san or "",
            best_san=best_san,
            quality=quality,
            cp_loss=cp_loss,
            explanation=explanation,
        ))

    # Generate puzzles from this game's blunders
    exercises_generated = 0
    if generate_puzzles:
        ex_stats = await generate_for_player(session, me)
        exercises_generated = ex_stats.inserted
        # Link puzzle IDs to corresponding debrief items
        ex_rows = list((await session.execute(
            select(Exercise.id, Move.ply)
            .join(Move, Move.id == Exercise.source_move_id)
            .where(Move.game_id == game.id)
        )).all())
        ply_to_ex = {ply: ex_id for ex_id, ply in ex_rows}
        for it in items:
            it.exercise_id = ply_to_ex.get(it.ply)

    opening_name = None
    eco = None
    if game.deepest_opening_id:
        from app.models.opening import Opening
        op = (await session.execute(
            select(Opening).where(Opening.id == game.deepest_opening_id)
        )).scalar_one_or_none()
        if op:
            opening_name = op.name
            eco = op.eco

    return DebriefReport(
        game_id=game.id,
        pgn_hash=_pgn_hash(pgn_text),
        me_username=me.chesscom_username,
        my_color="white" if my_is_white else "black",
        opening=opening_name,
        eco=eco,
        my_out_of_book_ply=game.my_out_of_book_ply,
        moves_analyzed=len(rows),
        phases=phases,
        top_blunders=items,
        exercises_generated=exercises_generated,
        elapsed_s=time.perf_counter() - started,
    )
