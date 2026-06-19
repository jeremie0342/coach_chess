"""Mobile-friendly compact API.

These endpoints mirror the desktop ones but with:
  - Trimmed payloads (no JSONB blobs, no nested arrays > 5 items)
  - Stable, shallow schemas (mobile clients hate schema churn)
  - Universal answer endpoint so the mobile client only learns one POST shape

Same auth as the rest of /api/v1 (X-API-Key).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models import (
    Exercise,
    Game,
    Player,
    RepertoireNode,
    Weakness,
)
from app.models.exercise import ExerciseKind
from app.models.game import GameResult
from app.models.repertoire import RepertoireColor
from app.services.exercises.solver import grade_answer as grade_exercise, pick_next_due as pick_exercise
from app.services.personality import compute_personality
from app.services.trainer.session import grade_answer as grade_node, pick_next_due as pick_card

router = APIRouter(prefix="/mobile", tags=["mobile"])


async def _me(session: AsyncSession) -> Player:
    me = (await session.execute(select(Player).where(Player.is_me.is_(True)))).scalar_one_or_none()
    if not me:
        raise HTTPException(404, "no current player")
    return me


# ---------- /mobile/home ----------

class MobileHome(BaseModel):
    username: str
    rating_rapid: int | None
    games_total: int
    games_7d: int
    winrate_white: float | None
    winrate_black: float | None
    top_weaknesses: list[dict]    # category + severity only
    cards_due: int
    puzzles_due: int


@router.get("/home", response_model=MobileHome)
async def home(session: Annotated[AsyncSession, Depends(get_session)]) -> MobileHome:
    me = await _me(session)
    now = datetime.now(timezone.utc)

    my_rating = case(
        (Game.white_player_id == me.id, Game.white_rating),
        else_=Game.black_rating,
    )
    rating = (await session.execute(
        select(my_rating)
        .where(or_(Game.white_player_id == me.id, Game.black_player_id == me.id))
        .where(Game.time_class == "rapid")
        .where(my_rating.is_not(None))
        .order_by(Game.played_at.desc())
        .limit(1)
    )).scalar()

    games_total = (await session.execute(
        select(func.count(Game.id))
        .where(or_(Game.white_player_id == me.id, Game.black_player_id == me.id))
    )).scalar_one()
    from datetime import timedelta
    games_7d = (await session.execute(
        select(func.count(Game.id))
        .where(or_(Game.white_player_id == me.id, Game.black_player_id == me.id))
        .where(Game.played_at >= now - timedelta(days=7))
    )).scalar_one()

    # winrate per color (one query, two cases)
    result = case(
        ((Game.white_player_id == me.id) & (Game.result == GameResult.WHITE_WIN), 1.0),
        ((Game.black_player_id == me.id) & (Game.result == GameResult.BLACK_WIN), 1.0),
        (Game.result == GameResult.DRAW, 0.5),
        else_=0.0,
    )
    color_label = case((Game.white_player_id == me.id, "white"), else_="black").label("color")
    wr_rows = (await session.execute(
        select(color_label, func.avg(result), func.count(Game.id))
        .where(or_(Game.white_player_id == me.id, Game.black_player_id == me.id))
        .group_by("color")
    )).all()
    wr = {c: round(float(s), 3) for c, s, n in wr_rows if n}

    top_w = list((await session.execute(
        select(Weakness)
        .where(Weakness.player_id == me.id)
        .order_by(Weakness.severity.desc())
        .limit(3)
    )).scalars())

    cards_due = (await session.execute(
        select(func.count(RepertoireNode.id))
        .where(RepertoireNode.is_my_move.is_(True))
        .where(RepertoireNode.sr_due_at.is_not(None), RepertoireNode.sr_due_at <= now)
    )).scalar_one()
    puzzles_due = (await session.execute(
        select(func.count(Exercise.id))
        .where(Exercise.sr_due_at.is_not(None), Exercise.sr_due_at <= now)
        .where(Exercise.sr_repetitions > 0)
    )).scalar_one()

    return MobileHome(
        username=me.chesscom_username,
        rating_rapid=rating,
        games_total=games_total,
        games_7d=games_7d,
        winrate_white=wr.get("white"),
        winrate_black=wr.get("black"),
        top_weaknesses=[
            {"category": w.category, "severity": round(w.severity, 2)} for w in top_w
        ],
        cards_due=cards_due,
        puzzles_due=puzzles_due,
    )


# ---------- /mobile/profile ----------

class MobileProfile(BaseModel):
    username: str
    style: dict[str, float]
    dominant_trait: str
    closest_gm: str | None


@router.get("/profile", response_model=MobileProfile)
async def profile(session: Annotated[AsyncSession, Depends(get_session)]) -> MobileProfile:
    me = await _me(session)
    r = await compute_personality(session, me)
    return MobileProfile(
        username=me.chesscom_username,
        style=r.style.as_dict(),
        dominant_trait=r.dominant_trait,
        closest_gm=r.closest_gm,
    )


# ---------- /mobile/training/next ----------

class MobileTrainingItem(BaseModel):
    type: Literal["repertoire", "puzzle"]
    id: int                  # node_id or exercise_id
    fen: str
    side_to_move: str        # "w" | "b"
    color_orientation: str   # who's the user playing as in this card
    title: str | None
    hint: str | None         # difficulty / theme list


@router.get("/training/next", response_model=MobileTrainingItem | None)
async def training_next(
    session: Annotated[AsyncSession, Depends(get_session)],
    prefer: Annotated[Literal["repertoire", "puzzle", "auto"], Query()] = "auto",
) -> MobileTrainingItem | None:
    """Pick the next thing the user should drill. Mobile client doesn't have to
    decide between repertoire and puzzles — server picks."""
    # If "auto": pick whatever is due. Repertoire first (memory hygiene), else puzzle.
    if prefer in ("auto", "repertoire"):
        card = await pick_card(session)
        if card:
            import chess
            board = chess.Board(card.node.fen)
            return MobileTrainingItem(
                type="repertoire", id=card.node.id, fen=card.node.fen,
                side_to_move="w" if board.turn == chess.WHITE else "b",
                color_orientation=str(card.node.color).split(".")[-1].lower(),
                title=card.node.label,
                hint=None,
            )
    if prefer in ("auto", "puzzle"):
        # Pull current rapid rating for ELO-targeted puzzles
        me = await _me(session)
        my_rating = case(
            (Game.white_player_id == me.id, Game.white_rating),
            else_=Game.black_rating,
        )
        rating = (await session.execute(
            select(my_rating)
            .where(or_(Game.white_player_id == me.id, Game.black_player_id == me.id))
            .where(Game.time_class == "rapid")
            .where(my_rating.is_not(None))
            .order_by(Game.played_at.desc())
            .limit(1)
        )).scalar()
        nxt = await pick_exercise(session, rating=rating, rating_window=200)
        if nxt:
            ex = nxt.exercise
            themes = ", ".join((ex.theme_tags or [])[:3])
            return MobileTrainingItem(
                type="puzzle", id=ex.id, fen=ex.fen,
                side_to_move=ex.side_to_move,
                color_orientation="white" if ex.side_to_move == "w" else "black",
                title=ex.title,
                hint=f"diff {ex.difficulty} · {themes}" if themes else f"diff {ex.difficulty}",
            )
    return None


# ---------- /mobile/answer ----------

class MobileAnswerIn(BaseModel):
    type: Literal["repertoire", "puzzle"]
    id: int
    move: str
    time_ms: int | None = None


class MobileAnswerOut(BaseModel):
    correct: bool
    expected_move: str
    user_move: str | None
    next_review_in_days: int


@router.post("/answer", response_model=MobileAnswerOut)
async def answer(
    payload: MobileAnswerIn,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> MobileAnswerOut:
    if payload.type == "repertoire":
        node = (await session.execute(
            select(RepertoireNode).where(RepertoireNode.id == payload.id)
        )).scalar_one_or_none()
        if not node:
            raise HTTPException(404, "node not found")
        r = await grade_node(session, node, payload.move, time_ms=payload.time_ms)
        return MobileAnswerOut(
            correct=r.correct,
            expected_move=r.expected_san or r.expected_uci or "?",
            user_move=r.user_uci,
            next_review_in_days=r.new_interval_days,
        )
    # puzzle
    ex = (await session.execute(
        select(Exercise).where(Exercise.id == payload.id)
    )).scalar_one_or_none()
    if not ex:
        raise HTTPException(404, "exercise not found")
    r = await grade_exercise(session, ex, payload.move, time_ms=payload.time_ms)
    return MobileAnswerOut(
        correct=r.correct,
        expected_move=r.expected_san or r.expected_uci,
        user_move=r.user_uci,
        next_review_in_days=r.new_interval_days,
    )
