from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models import Exercise, Player
from app.models.exercise import ExerciseKind
from app.services.exercises.generator import generate_for_player
from app.services.exercises.solver import (
    compute_stats,
    grade_answer,
    pick_next_due,
)
from app.services.llm.ollama import ChatMessage, OllamaClient

router = APIRouter(prefix="/exercises", tags=["exercises"])


class SolveIn(BaseModel):
    exercise_id: int
    move: str           # SAN or UCI
    time_ms: int | None = None
    step: int = 0       # which user step (0 = first user move)


@router.post("/generate")
async def generate(
    session: Annotated[AsyncSession, Depends(get_session)],
    min_cp_loss: int = 120,
) -> dict:
    me = (await session.execute(select(Player).where(Player.is_me.is_(True)))).scalar_one_or_none()
    if not me:
        raise HTTPException(404, "current player not imported")
    stats = await generate_for_player(session, me, min_cp_loss=min_cp_loss)
    return {
        "inserted": stats.inserted,
        "skipped_existing": stats.skipped_existing,
        "skipped_no_best": stats.skipped_no_best,
        "failed": stats.failed,
    }


@router.get("", summary="List exercises (recent or by rating, optional search)")
async def list_exercises(
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
    sort: Annotated[str, Query(pattern="^(recent|rating)$")] = "recent",
    q: Annotated[str | None, Query(description="Free-text search across title + theme tags + ID")] = None,
) -> list[dict]:
    from sqlalchemy import or_, cast, String
    query = select(Exercise)
    if q:
        term = q.strip()
        filters = [
            Exercise.title.ilike(f"%{term}%"),
            cast(Exercise.theme_tags, String).ilike(f"%{term}%"),
        ]
        if term.isdigit():
            filters.append(Exercise.id == int(term))
        query = query.where(or_(*filters))
    if sort == "rating":
        query = query.order_by(Exercise.difficulty.desc().nullslast())
    else:
        query = query.order_by(Exercise.created_at.desc())
    rows = list((await session.execute(query.limit(limit))).scalars())
    return [
        {
            "id": e.id,
            "rating": e.difficulty,
            "kind": str(e.kind) if e.kind else None,
            "title": e.title,
            "theme_tags": e.theme_tags or [],
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in rows
    ]


@router.get("/next")
async def next_exercise(
    session: Annotated[AsyncSession, Depends(get_session)],
    kind: ExerciseKind | None = None,
    theme: str | None = None,
    themes: str | None = None,           # CSV : "fork,pin,hangingPiece"
    exclude_themes: str | None = None,    # CSV : "mate,mateIn1,mateIn2"
    source_kind: str | None = None,
    rating: int | None = None,
    rating_window: int = 150,
) -> dict:
    themes_list = [t.strip() for t in themes.split(",") if t.strip()] if themes else None
    exclude_list = [t.strip() for t in exclude_themes.split(",") if t.strip()] if exclude_themes else None
    nxt = await pick_next_due(
        session, kind=kind, theme=theme,
        themes=themes_list, exclude_themes=exclude_list,
        source_kind=source_kind, rating=rating, rating_window=rating_window,
    )
    if not nxt:
        return {"has_exercise": False}
    ex = nxt.exercise

    # Lichess convention: raw fen is BEFORE the opponent's trigger move
    # (solution_uci[0]). The real puzzle position shown to the user is AFTER
    # applying that trigger. We compute the "effective" starting position here
    # so the frontend doesn't have to know about the Lichess layout.
    import chess as _chess
    effective_fen = ex.fen
    user_color = "white" if (ex.side_to_move or "w") == "b" else "black"
    total_user_steps = 1
    if ex.solution_uci:
        total_user_steps = max(1, len(ex.solution_uci) // 2)
        try:
            b = _chess.Board(ex.fen)
            first = ex.solution_uci[0]
            mv = _chess.Move.from_uci(first)
            if mv in b.legal_moves:
                b.push(mv)
                effective_fen = b.fen()
                user_color = "white" if b.turn else "black"
        except Exception:
            pass

    return {
        "has_exercise": True,
        "is_new": nxt.is_new,
        "due_now": nxt.due_now,
        "exercise": {
            "id": ex.id,
            "title": ex.title,
            "fen": effective_fen,            # ← board to display
            "raw_fen": ex.fen,                # ← unchanged Lichess FEN (debug)
            "user_color": user_color,
            "total_user_steps": total_user_steps,
            "side_to_move": "w" if user_color == "white" else "b",
            "kind": str(ex.kind),
            "difficulty": ex.difficulty,
            "themes": ex.theme_tags,
            "source_game_id": ex.source_game_id,
        },
    }


@router.post("/answer")
async def answer(
    payload: SolveIn,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    ex = (await session.execute(
        select(Exercise).where(Exercise.id == payload.exercise_id)
    )).scalar_one_or_none()
    if not ex:
        raise HTTPException(404, "exercise not found")
    r = await grade_answer(
        session, ex, payload.move,
        time_ms=payload.time_ms, step=payload.step,
    )
    return {
        "exercise_id": r.exercise_id,
        "correct": r.correct,
        "grade": r.grade,
        "step": r.step,
        "complete": r.complete,
        "user_uci": r.user_uci,
        "expected_uci": r.expected_uci,
        "expected_san": r.expected_san,
        "opponent_uci": r.opponent_uci,
        "opponent_san": r.opponent_san,
        "fen_after_opponent": r.fen_after_opponent,
        "next_expected_uci": r.next_expected_uci,
        "next_expected_san": r.next_expected_san,
        "new_interval_days": r.new_interval_days,
        "new_due_at": r.new_due_at.isoformat(),
    }


@router.post("/{exercise_id}/explain/stream", summary="LLM commentary on a puzzle's solution (streamed)")
async def explain_exercise_stream(
    exercise_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> StreamingResponse:
    """Generate a French coach explanation of the puzzle's solution. Used by the
    UI after the user abandons or finishes the puzzle. Streams tokens."""
    import chess as _chess

    ex = (await session.execute(select(Exercise).where(Exercise.id == exercise_id))).scalar_one_or_none()
    if not ex:
        raise HTTPException(404, "exercise not found")

    solution = list(ex.solution_uci or [])
    # Compute effective FEN (after trigger) + the user's move sequence in SAN.
    board = _chess.Board(ex.fen)
    if solution:
        try:
            board.push(_chess.Move.from_uci(solution[0]))
        except Exception:
            pass
    effective_fen = board.fen()
    side = "Blancs" if board.turn else "Noirs"

    # Build user solution in SAN by walking solution[1:] starting from effective board
    walk = _chess.Board(effective_fen)
    san_pairs: list[str] = []
    for u in solution[1:]:
        try:
            mv = _chess.Move.from_uci(u)
            if mv in walk.legal_moves:
                san_pairs.append(walk.san(mv))
                walk.push(mv)
        except Exception:
            break
    sol_text = " ".join(san_pairs) if san_pairs else "(pas de solution stockée)"

    themes = ", ".join(ex.theme_tags or []) or "—"

    system = (
        "Tu es un coach d'échecs francophone, pédagogue, qui s'adresse à un joueur "
        "amateur autour de 450 ELO. Explique en 2-4 phrases courtes :\n"
        "- l'idée tactique derrière la solution (motif, mécanisme)\n"
        "- pourquoi le coup-clé fonctionne\n"
        "- ce qu'il faut retenir pour reconnaître ce pattern à l'avenir\n"
        "Texte fluide, pas de listes."
    )
    user = (
        f"Position (toi de jouer pour les {side}) :\n{effective_fen}\n\n"
        f"Thèmes Lichess : {themes}\n"
        f"Difficulté : {ex.difficulty}\n\n"
        f"Solution (la séquence de coups gagnante) : {sol_text}\n\n"
        "Explique en français à un joueur de 450 ELO l'idée principale."
    )

    async def gen():
        async with OllamaClient() as client:
            async for chunk in client.chat_stream(
                [ChatMessage(role="system", content=system),
                 ChatMessage(role="user", content=user)],
            ):
                yield chunk

    return StreamingResponse(
        gen(),
        media_type="text/plain; charset=utf-8",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


@router.get("/{exercise_id}/legal")
async def exercise_legal(
    exercise_id: int,
    square: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    import chess as _ch
    ex = (await session.execute(
        select(Exercise).where(Exercise.id == exercise_id)
    )).scalar_one_or_none()
    if not ex:
        raise HTTPException(404, "exercise not found")
    board = _ch.Board(ex.fen)
    sq = (square or "").strip().lower()
    if len(sq) != 2 or sq[0] not in "abcdefgh" or sq[1] not in "12345678":
        raise HTTPException(400, "square must be like 'e2'")
    src = _ch.parse_square(sq)
    piece = board.piece_at(src)
    if piece is None:
        return {"from": sq, "to": [], "owner": None}
    dests = []
    promos = []
    for m in board.legal_moves:
        if m.from_square != src:
            continue
        d = _ch.square_name(m.to_square)
        if m.promotion is not None:
            if d not in promos: promos.append(d)
        else:
            if d not in dests: dests.append(d)
    return {
        "from": sq,
        "to": dests + promos,
        "promotions": promos,
        "owner": "white" if piece.color == _ch.WHITE else "black",
    }


@router.get("/recommended_rating", summary="Adaptive puzzle rating based on recent success rate")
async def recommended_rating(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    """Adaptive target rating for puzzles.

    Logic:
      - base = player's current Rapid rating (or 800 if unknown)
      - look at the last 30 puzzles where the user actually attempted (attempts>0)
      - compute success_rate = successes/attempts (weighted by difficulty)
      - bump:
          ≥ 0.85 → +200    (you're crushing it, go harder)
          0.70-0.85 → +100 (comfortable, push up)
          0.50-0.70 → 0    (in the zone)
          0.30-0.50 → -75  (struggling, back off)
          < 0.30   → -150  (way too hard)
    """
    from sqlalchemy import desc, func
    from app.models import Game
    from app.models.game import GameResult  # noqa: F401

    me = (await session.execute(select(Player).where(Player.is_me.is_(True)))).scalar_one_or_none()
    base_rating = 800
    if me:
        from sqlalchemy import case, or_
        my_rating_col = case(
            (Game.white_player_id == me.id, Game.white_rating),
            else_=Game.black_rating,
        )
        latest = (await session.execute(
            select(my_rating_col)
            .where(or_(Game.white_player_id == me.id, Game.black_player_id == me.id))
            .where(Game.time_class == "rapid")
            .where(my_rating_col.is_not(None))
            .order_by(desc(Game.played_at))
            .limit(1)
        )).scalar()
        if latest:
            base_rating = int(latest)

    # Look at the last 30 attempted puzzles
    rows = list((await session.execute(
        select(Exercise.difficulty, Exercise.attempts, Exercise.successes)
        .where(Exercise.attempts > 0)
        .order_by(desc(Exercise.sr_last_reviewed_at))
        .limit(30)
    )).all())

    sample_size = len(rows)
    if sample_size == 0:
        return {
            "rating": base_rating,
            "base_rating": base_rating,
            "adjustment": 0,
            "success_rate": None,
            "sample_size": 0,
            "rating_window": 200,
            "reason": "Pas encore d'historique — on commence à ton ELO Rapid.",
        }

    total_attempts = sum(r.attempts or 0 for r in rows)
    total_successes = sum(r.successes or 0 for r in rows)
    success_rate = total_successes / max(1, total_attempts)

    if success_rate >= 0.85:
        adj = 200
        reason = f"Tu écrases ({round(success_rate * 100)}% sur {sample_size} puzzles). On monte la difficulté."
    elif success_rate >= 0.70:
        adj = 100
        reason = f"Confortable ({round(success_rate * 100)}%). On pousse un peu."
    elif success_rate >= 0.50:
        adj = 0
        reason = f"Dans la zone ({round(success_rate * 100)}%). Niveau cohérent."
    elif success_rate >= 0.30:
        adj = -75
        reason = f"Ça résiste ({round(success_rate * 100)}%). On baisse légèrement."
    else:
        adj = -150
        reason = f"Trop dur ({round(success_rate * 100)}%). On revient à du plus accessible."

    target = max(400, base_rating + adj)
    return {
        "rating": target,
        "base_rating": base_rating,
        "adjustment": adj,
        "success_rate": round(success_rate, 3),
        "sample_size": sample_size,
        "rating_window": 200,
        "reason": reason,
    }


@router.get("/stats")
async def stats(
    session: Annotated[AsyncSession, Depends(get_session)],
    kind: ExerciseKind | None = None,
) -> dict:
    s = await compute_stats(session, kind=kind)
    return {
        "total": s.total,
        "new": s.new,
        "learning": s.learning,
        "due_today": s.due_today,
        "next_due_at": s.next_due_at.isoformat() if s.next_due_at else None,
    }
