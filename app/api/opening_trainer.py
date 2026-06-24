from __future__ import annotations

import random
from typing import Annotated

import chess
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.services.opening_trainer import (
    LIBRARY, list_openings, get_opening, materialize_branch,
)

router = APIRouter(prefix="/trainer/opening", tags=["trainer"])


# Simple in-memory session store. Single-user backend, restarts wipe state.
_SESSIONS: dict[int, "_TrainerSession"] = {}
_NEXT_ID = 1


class _TrainerSession:
    def __init__(self, opening_key: str):
        self.opening_key = opening_key
        self.ply_index = 0
        self.board = chess.Board()
        self.wrong_moves = 0
        self.recorded = False
        self.variant_label = "Ligne principale"

        op = LIBRARY.get(opening_key)
        if op is None:
            return

        # Decide if we pick a branch this session (35% chance per session if
        # branches exist). Branches force the user to adapt rather than memorize
        # a single line.
        chosen_moves = list(op.moves)
        if op.branches and random.random() < 0.35:
            branch = random.choice(op.branches)
            chosen_moves = materialize_branch(op, branch)
            self.variant_label = branch.label

        # Recompute prelude + paired line from the chosen path.
        from app.services.opening_trainer import TrainerNode
        user_color = op.user_color
        first_user_idx = next(
            (i for i, m in enumerate(chosen_moves) if m.color == user_color),
            len(chosen_moves),
        )
        self.prelude = list(chosen_moves[:first_user_idx])
        self.line: list[TrainerNode] = []
        i = first_user_idx
        while i < len(chosen_moves):
            user_mv = chosen_moves[i]
            opp_mv = chosen_moves[i + 1] if (i + 1 < len(chosen_moves) and chosen_moves[i + 1].color != user_color) else None
            self.line.append(TrainerNode(
                user_move=user_mv.uci,
                user_san=user_mv.san,
                user_explanation=user_mv.explanation,
                opponent_reply=opp_mv.uci if opp_mv else None,
                opponent_san=opp_mv.san if opp_mv else None,
            ))
            i += 2 if opp_mv else 1

        for mv in self.prelude:
            try:
                move = chess.Move.from_uci(mv.uci)
                if move in self.board.legal_moves:
                    self.board.push(move)
            except (ValueError, chess.InvalidMoveError):
                pass


class StartIn(BaseModel):
    opening_key: str = Field(..., description="key from /trainer/opening/list")


@router.get("/list")
async def list_endpoint(
    _: Annotated[AsyncSession, Depends(get_session)],
    grouped: bool = False,
) -> dict:
    from app.services.opening_trainer import list_openings_grouped
    if grouped:
        return {"groups": list_openings_grouped()}
    return {"openings": list_openings()}


@router.get("/mastery", summary="My opening-mastery progress (streak + status per variant)")
async def mastery_endpoint(
    db: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    from sqlalchemy import select as _select
    from app.models import Player as _Player
    from app.services.opening_mastery import (
        get_or_seed_active, list_progress, MASTERY_STREAK,
    )

    me = (await db.execute(_select(_Player).where(_Player.is_me.is_(True)))).scalar_one_or_none()
    if me is None:
        raise HTTPException(404, "current player not imported")
    # Make sure both color slots have an active variant assigned.
    await get_or_seed_active(db, me, "white")
    await get_or_seed_active(db, me, "black")
    await db.commit()

    rows = await list_progress(db, me)
    today = __import__('datetime').datetime.now(__import__('datetime').timezone.utc).date()
    return {
        "mastery_streak": MASTERY_STREAK,
        "items": [
            {
                "opening_key": r.opening_key,
                "base_name": r.base_name,
                "user_color": r.user_color,
                "status": str(r.status),
                "streak_days": r.streak_days,
                "best_streak": r.best_streak,
                "attempts": r.attempts,
                "perfect_runs": r.perfect_runs,
                "last_perfect_date": r.last_perfect_date.isoformat() if r.last_perfect_date else None,
                "perfect_today": bool(r.last_perfect_date and r.last_perfect_date == today),
                "mastered_at": r.mastered_at.isoformat() if r.mastered_at else None,
            }
            for r in rows
        ],
    }


@router.get("/repertoire", summary="My personal opening repertoire (list)")
async def repertoire_list_endpoint(
    db: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    from sqlalchemy import select as _select
    from app.models import Player as _Player, PlayerRepertoireEntry
    from app.services.opening_mastery import list_progress
    from app.services.opening_trainer import LIBRARY as _LIB

    me = (await db.execute(_select(_Player).where(_Player.is_me.is_(True)))).scalar_one_or_none()
    if me is None:
        raise HTTPException(404, "current player not imported")

    entries = list((await db.execute(
        _select(PlayerRepertoireEntry)
        .where(PlayerRepertoireEntry.player_id == me.id)
        .order_by(PlayerRepertoireEntry.user_color, PlayerRepertoireEntry.position, PlayerRepertoireEntry.id)
    )).scalars())

    # Mastery progress lookup
    progress_rows = await list_progress(db, me)
    prog_by_key = {p.opening_key: p for p in progress_rows}

    def _serialize(e: PlayerRepertoireEntry) -> dict:
        op = _LIB.get(e.opening_key)
        p = prog_by_key.get(e.opening_key)
        return {
            "id": e.id,
            "opening_key": e.opening_key,
            "base_name": e.base_name,
            "name": op.name if op else e.base_name,
            "eco": op.eco if op else None,
            "summary": op.summary if op else None,
            "user_color": e.user_color,
            "position": e.position,
            "notes": e.notes,
            "added_at": e.added_at.isoformat() if e.added_at else None,
            "missing_from_library": op is None,
            "progress": (
                {
                    "status": str(p.status),
                    "streak_days": p.streak_days,
                    "best_streak": p.best_streak,
                    "attempts": p.attempts,
                    "perfect_runs": p.perfect_runs,
                }
                if p else None
            ),
        }

    return {
        "white": [_serialize(e) for e in entries if e.user_color == "white"],
        "black": [_serialize(e) for e in entries if e.user_color == "black"],
    }


class RepertoireAddIn(BaseModel):
    opening_key: str = Field(..., description="key from /trainer/opening/list")
    notes: str | None = Field(None, description="Optional personal notes")


@router.post("/repertoire", summary="Add an opening to my repertoire")
async def repertoire_add_endpoint(
    payload: RepertoireAddIn,
    db: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    from sqlalchemy import select as _select, func as _func
    from app.models import Player as _Player, PlayerRepertoireEntry

    op = get_opening(payload.opening_key)
    if op is None:
        raise HTTPException(404, f"unknown opening '{payload.opening_key}'")

    me = (await db.execute(_select(_Player).where(_Player.is_me.is_(True)))).scalar_one_or_none()
    if me is None:
        raise HTTPException(404, "current player not imported")

    existing = (await db.execute(
        _select(PlayerRepertoireEntry)
        .where(PlayerRepertoireEntry.player_id == me.id)
        .where(PlayerRepertoireEntry.opening_key == payload.opening_key)
    )).scalar_one_or_none()
    if existing is not None:
        if payload.notes is not None:
            existing.notes = payload.notes
            await db.commit()
        return {"ok": True, "already_present": True, "id": existing.id}

    next_pos = (await db.execute(
        _select(_func.coalesce(_func.max(PlayerRepertoireEntry.position), -1))
        .where(PlayerRepertoireEntry.player_id == me.id)
        .where(PlayerRepertoireEntry.user_color == op.user_color)
    )).scalar() or 0
    entry = PlayerRepertoireEntry(
        player_id=me.id,
        opening_key=op.key,
        base_name=op.base_name,
        user_color=op.user_color,
        position=int(next_pos) + 1,
        notes=payload.notes,
    )
    db.add(entry)
    await db.commit()
    return {"ok": True, "id": entry.id, "already_present": False}


@router.delete("/repertoire/{opening_key}", summary="Remove an opening from my repertoire")
async def repertoire_remove_endpoint(
    opening_key: str,
    db: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    from sqlalchemy import select as _select, delete as _delete
    from app.models import Player as _Player, PlayerRepertoireEntry

    me = (await db.execute(_select(_Player).where(_Player.is_me.is_(True)))).scalar_one_or_none()
    if me is None:
        raise HTTPException(404, "current player not imported")

    res = await db.execute(
        _delete(PlayerRepertoireEntry)
        .where(PlayerRepertoireEntry.player_id == me.id)
        .where(PlayerRepertoireEntry.opening_key == opening_key)
    )
    await db.commit()
    return {"ok": True, "removed": res.rowcount or 0}


class RepertoireUpdateIn(BaseModel):
    notes: str | None = None
    position: int | None = None


@router.patch("/repertoire/{opening_key}", summary="Update notes or position")
async def repertoire_update_endpoint(
    opening_key: str,
    payload: RepertoireUpdateIn,
    db: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    from sqlalchemy import select as _select
    from app.models import Player as _Player, PlayerRepertoireEntry

    me = (await db.execute(_select(_Player).where(_Player.is_me.is_(True)))).scalar_one_or_none()
    if me is None:
        raise HTTPException(404, "current player not imported")

    entry = (await db.execute(
        _select(PlayerRepertoireEntry)
        .where(PlayerRepertoireEntry.player_id == me.id)
        .where(PlayerRepertoireEntry.opening_key == opening_key)
    )).scalar_one_or_none()
    if entry is None:
        raise HTTPException(404, "not in repertoire")
    if payload.notes is not None:
        entry.notes = payload.notes
    if payload.position is not None:
        entry.position = payload.position
    await db.commit()
    return {"ok": True}


@router.post("/start")
async def start_endpoint(
    payload: StartIn,
    _: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    op = get_opening(payload.opening_key)
    if op is None:
        raise HTTPException(404, f"unknown opening '{payload.opening_key}'")
    global _NEXT_ID
    sid = _NEXT_ID
    _NEXT_ID += 1
    sess = _TrainerSession(payload.opening_key)
    _SESSIONS[sid] = sess
    first_node = sess.line[0] if sess.line else None
    return {
        "id": sid,
        "opening": {
            "key": op.key,
            "name": op.name,
            "base_name": op.base_name,
            "eco": op.eco,
            "user_color": op.user_color,
            "summary": op.summary,
            "plan": op.plan,
            "variant_label": sess.variant_label,
        },
        "current_fen": sess.board.fen(),
        "expected_user_uci": first_node.user_move if first_node else None,
        "expected_user_san": first_node.user_san if first_node else None,
        "coach_hint": first_node.user_explanation if first_node else None,
        "ply": 0,
        "total_plies": len(sess.line) * 2,
    }


class MoveIn(BaseModel):
    move: str = Field(..., description="UCI move from the user")


@router.post("/{session_id}/move")
async def move_endpoint(
    session_id: int,
    payload: MoveIn,
    db: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    sess = _SESSIONS.get(session_id)
    if sess is None:
        raise HTTPException(404, "trainer session not found")
    op = get_opening(sess.opening_key)
    if op is None:
        raise HTTPException(500, "opening missing")
    if sess.ply_index >= len(sess.line):
        return {
            "status": "completed",
            "current_fen": sess.board.fen(),
            "correct": None,
            "message": "Tu as termine la ligne principale. Belle exec.",
        }

    node = sess.line[sess.ply_index]
    expected = node.user_move
    move_input = (payload.move or "").strip()
    user_move = None
    try:
        user_move = chess.Move.from_uci(move_input)
        if user_move not in sess.board.legal_moves:
            user_move = None
    except (ValueError, chess.InvalidMoveError):
        user_move = None

    if user_move is None:
        sess.wrong_moves += 1
        return {
            "status": "illegal",
            "correct": False,
            "current_fen": sess.board.fen(),
            "expected_user_uci": expected,
            "expected_user_san": node.user_san,
            "coach_hint": node.user_explanation,
            "message": "Coup illegal. Essaie le coup attendu pour cette ouverture.",
        }

    if expected and move_input.lower() != expected.lower():
        # Wrong book move
        sess.wrong_moves += 1
        return {
            "status": "wrong_book",
            "correct": False,
            "current_fen": sess.board.fen(),
            "your_san": sess.board.san(user_move),
            "expected_user_uci": expected,
            "expected_user_san": node.user_san,
            "coach_hint": node.user_explanation,
            "message": (
                f"Pas le coup theorique. Ici la {op.name} joue "
                f"{node.user_san} : {node.user_explanation}"
            ),
        }

    # Correct: push user move
    sess.board.push(user_move)
    user_san = node.user_san or sess.board.san(user_move)

    # Push opponent reply if any
    opponent_uci = node.opponent_reply
    opponent_san = node.opponent_san
    if opponent_uci:
        try:
            opp = chess.Move.from_uci(opponent_uci)
            if opp in sess.board.legal_moves:
                sess.board.push(opp)
        except (ValueError, chess.InvalidMoveError):
            pass
    sess.ply_index += 1

    # Next node info (hint for the user's next move)
    next_uci = next_san = next_hint = None
    if sess.ply_index < len(sess.line):
        nxt = sess.line[sess.ply_index]
        next_uci = nxt.user_move
        next_san = nxt.user_san
        next_hint = nxt.user_explanation

    status = "ok" if sess.ply_index < len(sess.line) else "completed"

    # On completion : record the attempt result against the mastery tracker.
    mastery_payload: dict | None = None
    if status == "completed" and not sess.recorded:
        sess.recorded = True
        from sqlalchemy import select as _select
        from app.models import Player as _Player
        from app.services.opening_mastery import record_attempt, MASTERY_STREAK
        me = (await db.execute(
            _select(_Player).where(_Player.is_me.is_(True))
        )).scalar_one_or_none()
        if me is not None:
            prog = await record_attempt(
                db, me, sess.opening_key,
                is_perfect=(sess.wrong_moves == 0),
            )
            if prog is not None:
                await db.commit()
                mastery_payload = {
                    "perfect": sess.wrong_moves == 0,
                    "wrong_moves": sess.wrong_moves,
                    "streak_days": prog.streak_days,
                    "mastery_target": MASTERY_STREAK,
                    "status": str(prog.status),
                    "newly_mastered": bool(prog.mastered_at and prog.streak_days >= MASTERY_STREAK),
                    "best_streak": prog.best_streak,
                }

    return {
        "status": status,
        "correct": True,
        "current_fen": sess.board.fen(),
        "your_san": user_san,
        "opponent_uci": opponent_uci,
        "opponent_san": opponent_san,
        "expected_user_uci": next_uci,
        "expected_user_san": next_san,
        "coach_hint": next_hint,
        "ply": sess.ply_index * 2,
        "total_plies": len(sess.line) * 2,
        "mastery": mastery_payload,
        "message": (
            "Belle execution." if status == "ok"
            else "Tu as fini la ligne principale. Tu peux relancer."
        ),
    }


@router.get("/{session_id}/legal")
async def trainer_legal(
    session_id: int,
    square: str,
) -> dict:
    sess = _SESSIONS.get(session_id)
    if sess is None:
        raise HTTPException(404, "trainer session not found")
    sq = (square or "").strip().lower()
    if len(sq) != 2 or sq[0] not in "abcdefgh" or sq[1] not in "12345678":
        raise HTTPException(400, "square must be like 'e2'")
    src = chess.parse_square(sq)
    piece = sess.board.piece_at(src)
    if piece is None:
        return {"from": sq, "to": [], "owner": None, "in_check": sess.board.is_check()}
    destinations = []
    promotions = []
    for m in sess.board.legal_moves:
        if m.from_square != src:
            continue
        dest = chess.square_name(m.to_square)
        if m.promotion is not None:
            if dest not in promotions:
                promotions.append(dest)
        else:
            if dest not in destinations:
                destinations.append(dest)
    return {
        "from": sq,
        "to": destinations + promotions,
        "promotions": promotions,
        "owner": "white" if piece.color == chess.WHITE else "black",
        "in_check": sess.board.is_check(),
    }


@router.delete("/{session_id}")
async def end_endpoint(session_id: int) -> dict:
    _SESSIONS.pop(session_id, None)
    return {"ok": True}
