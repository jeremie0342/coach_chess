from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models import Game, Player
from app.services.coach.explainer import explain_move
from app.services.coach.game_review import review_player_mistakes
from app.services.coach.lesson_message import generate_message
from app.services.coach.lesson_plan import compose_daily_plan
from app.services.live_debrief import live_debrief
from app.services.scout.scout import scout_opponent

router = APIRouter(prefix="/coach", tags=["coach"])


class ScoutIn(BaseModel):
    opponent_username: str = Field(..., description="Chess.com username of the opponent")
    max_months: int = Field(3, ge=1, le=24)
    max_games: int = Field(100, ge=10, le=500)
    generate_plan: bool = True


class LiveDebriefIn(BaseModel):
    pgn: str = Field(..., description="The full PGN text of the game to debrief")
    my_color: str | None = Field(
        None, description="'white' or 'black'. Auto-detected from PGN if omitted."
    )
    depth: int | None = Field(
        None, ge=8, le=30, description="Stockfish depth, defaults to env value"
    )
    max_blunders: int = Field(5, ge=1, le=20)
    generate_puzzles: bool = True
    explain_with_llm: bool = True


@router.post("/games/{game_id}/explain_move")
async def explain(
    game_id: int,
    ply: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    use_cache: bool = True,
) -> dict:
    game = (await session.execute(select(Game).where(Game.id == game_id))).scalar_one_or_none()
    if not game:
        raise HTTPException(404, "game not found")
    return await explain_move(session, game, ply, use_cache=use_cache)


@router.post("/games/{game_id}/review")
async def review(
    game_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    max_items: int = 5,
) -> dict:
    game = (await session.execute(select(Game).where(Game.id == game_id))).scalar_one_or_none()
    if not game:
        raise HTTPException(404, "game not found")
    me = (await session.execute(select(Player).where(Player.is_me.is_(True)))).scalar_one_or_none()
    if not me:
        raise HTTPException(404, "current player not imported")
    items = await review_player_mistakes(session, game, me, max_items=max_items)
    return {
        "game_id": game_id,
        "items": [
            {
                "ply": i.ply,
                "side_to_move": i.side_to_move,
                "played": i.played,
                "best": i.best,
                "quality": i.quality,
                "cp_loss": i.cp_loss,
                "explanation": i.explanation,
            }
            for i in items
        ],
    }


@router.post("/live_debrief", summary="Debrief a freshly-played game (paste PGN)")
async def live_debrief_endpoint(
    payload: LiveDebriefIn,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    report = await live_debrief(
        session,
        pgn_text=payload.pgn,
        my_color=payload.my_color,
        depth=payload.depth,
        max_blunders=payload.max_blunders,
        generate_puzzles=payload.generate_puzzles,
        explain_with_llm=payload.explain_with_llm,
    )
    return {
        "game_id": report.game_id,
        "pgn_hash": report.pgn_hash,
        "me": report.me_username,
        "my_color": report.my_color,
        "opening": report.opening,
        "eco": report.eco,
        "my_out_of_book_ply": report.my_out_of_book_ply,
        "moves_analyzed": report.moves_analyzed,
        "phases": {
            phase: {
                "blunders": p.blunders,
                "mistakes": p.mistakes,
                "inaccuracies": p.inaccuracies,
            }
            for phase, p in report.phases.items()
        },
        "top_blunders": [
            {
                "ply": it.ply,
                "side": it.side,
                "played_san": it.played_san,
                "best_san": it.best_san,
                "quality": it.quality,
                "cp_loss": it.cp_loss,
                "explanation": it.explanation,
                "exercise_id": it.exercise_id,
            }
            for it in report.top_blunders
        ],
        "exercises_generated": report.exercises_generated,
        "elapsed_s": round(report.elapsed_s, 2),
    }


@router.get(
    "/me/today",
    summary="Today's adaptive training plan (auto-composed)",
)
async def get_today(
    session: Annotated[AsyncSession, Depends(get_session)],
    target_minutes: int = 30,
    regenerate: bool = False,
    generate_message_llm: bool = True,
) -> dict:
    me = (await session.execute(
        select(Player).where(Player.is_me.is_(True))
    )).scalar_one_or_none()
    if not me:
        raise HTTPException(404, "current player not imported")
    plan = await compose_daily_plan(
        session, me, target_minutes=target_minutes, force=regenerate,
    )
    # Generate or refresh the coach message only when needed
    if generate_message_llm and (regenerate or not plan.coach_message):
        msg = await generate_message(session, plan)
        if msg:
            plan.coach_message = msg
            await session.commit()
    from app.models import DailyPlanItem
    items = list((await session.execute(
        select(DailyPlanItem)
        .where(DailyPlanItem.plan_id == plan.id)
        .order_by(DailyPlanItem.order_index)
    )).scalars())
    return {
        "date": plan.plan_date.isoformat(),
        "target_minutes": plan.target_minutes,
        "weakness_focus": plan.weakness_focus,
        "coach_message": plan.coach_message,
        "completed_at": plan.completed_at.isoformat() if plan.completed_at else None,
        "items": [
            {
                "id": it.id,
                "order": it.order_index,
                "kind": str(it.kind),
                "title": it.title,
                "target_count": it.target_count,
                "estimated_minutes": it.estimated_minutes,
                "filters": it.filters,
                "rationale": it.rationale,
                "completed_count": it.completed_count,
                "completed_at": it.completed_at.isoformat() if it.completed_at else None,
            }
            for it in items
        ],
    }


class CompleteItemIn(BaseModel):
    delta_count: int = Field(1, ge=1, le=100)


@router.post("/me/today/items/{item_id}/complete")
async def complete_item(
    item_id: int,
    payload: CompleteItemIn,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    from datetime import datetime, timezone
    from app.models import DailyPlanItem
    it = (await session.execute(
        select(DailyPlanItem).where(DailyPlanItem.id == item_id)
    )).scalar_one_or_none()
    if not it:
        raise HTTPException(404, "item not found")
    it.completed_count = (it.completed_count or 0) + payload.delta_count
    if it.completed_count >= it.target_count and it.completed_at is None:
        it.completed_at = datetime.now(timezone.utc)
    await session.commit()
    return {
        "id": it.id,
        "completed_count": it.completed_count,
        "target_count": it.target_count,
        "completed_at": it.completed_at.isoformat() if it.completed_at else None,
    }


class TapeGameSummary(BaseModel):
    id: int
    played_at: str | None
    color: str
    result: str
    rating_mine: int | None
    opponent: str | None
    opponent_rating: int | None
    ply_count: int
    blunders: int
    mistakes: int
    inaccuracies: int
    opening_name: str | None
    eco: str | None


class TapeResponse(BaseModel):
    games: list[TapeGameSummary]
    total: int
    offset: int
    limit: int


@router.get(
    "/me/games",
    response_model=TapeResponse,
    summary="Paginated list of my games with per-game stats for the Tape timeline",
)
async def list_my_games(
    session: Annotated[AsyncSession, Depends(get_session)],
    offset: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=1000),
    order: str = Query("asc", pattern="^(asc|desc)$"),
) -> TapeResponse:
    from sqlalchemy import case, func, or_
    from app.models import Game, Move, Player
    from app.models.analysis import MoveAnalysis, MoveQuality

    me = (await session.execute(
        select(Player).where(Player.is_me.is_(True))
    )).scalar_one_or_none()
    if not me:
        raise HTTPException(404, "current player not imported")

    my_games_filter = or_(Game.white_player_id == me.id, Game.black_player_id == me.id)
    total = (await session.execute(
        select(func.count(Game.id)).where(my_games_filter)
    )).scalar_one()

    order_col = Game.played_at.asc().nullslast() if order == "asc" else Game.played_at.desc().nullslast()

    rows = list((await session.execute(
        select(Game)
        .where(my_games_filter)
        .order_by(order_col, Game.id.asc() if order == "asc" else Game.id.desc())
        .offset(offset)
        .limit(limit)
    )).scalars())

    if not rows:
        return TapeResponse(games=[], total=total, offset=offset, limit=limit)

    game_ids = [g.id for g in rows]
    # One pass to count quality buckets per game for moves played by me
    is_white_move = Move.is_white.is_(True)
    color_match = case(
        (Game.white_player_id == me.id, is_white_move),
        else_=Move.is_white.is_(False),
    )
    q_rows = (await session.execute(
        select(
            Move.game_id,
            func.sum(case((MoveAnalysis.quality == MoveQuality.BLUNDER, 1), else_=0)).label("b"),
            func.sum(case((MoveAnalysis.quality == MoveQuality.MISTAKE, 1), else_=0)).label("m"),
            func.sum(case((MoveAnalysis.quality == MoveQuality.INACCURACY, 1), else_=0)).label("i"),
        )
        .join(MoveAnalysis, MoveAnalysis.move_id == Move.id)
        .join(Game, Game.id == Move.game_id)
        .where(Move.game_id.in_(game_ids))
        .where(color_match)
        .group_by(Move.game_id)
    )).all()
    stats_by_game = {gid: (b or 0, m or 0, i or 0) for gid, b, m, i in q_rows}

    # Opponent usernames in one fetch
    opp_ids = set()
    for g in rows:
        opp_ids.add(g.black_player_id if g.white_player_id == me.id else g.white_player_id)
    opp_map = {}
    if opp_ids:
        opps = (await session.execute(
            select(Player).where(Player.id.in_(opp_ids))
        )).scalars()
        opp_map = {p.id: p for p in opps}

    games_out: list[TapeGameSummary] = []
    for g in rows:
        i_am_white = g.white_player_id == me.id
        color = "white" if i_am_white else "black"
        if g.result == "1-0":
            result = "win" if i_am_white else "loss"
        elif g.result == "0-1":
            result = "loss" if i_am_white else "win"
        else:
            result = "draw"
        rating_mine = g.white_rating if i_am_white else g.black_rating
        opp_id = g.black_player_id if i_am_white else g.white_player_id
        opp = opp_map.get(opp_id)
        opponent = opp.chesscom_username if opp else None
        opponent_rating = g.black_rating if i_am_white else g.white_rating
        b, m, i = stats_by_game.get(g.id, (0, 0, 0))
        games_out.append(TapeGameSummary(
            id=g.id,
            played_at=g.played_at.isoformat() if g.played_at else None,
            color=color,
            result=result,
            rating_mine=rating_mine,
            opponent=opponent,
            opponent_rating=opponent_rating,
            ply_count=g.ply_count,
            blunders=int(b),
            mistakes=int(m),
            inaccuracies=int(i),
            opening_name=g.opening_name,
            eco=g.eco,
        ))

    return TapeResponse(games=games_out, total=total, offset=offset, limit=limit)


@router.post("/scout", summary="Scout a Chess.com opponent and produce a battle plan")
async def scout(
    payload: ScoutIn,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    r = await scout_opponent(
        session,
        opponent_username=payload.opponent_username,
        max_months=payload.max_months,
        max_games=payload.max_games,
        generate_plan=payload.generate_plan,
    )
    o = r.opening_report
    return {
        "opponent": r.opponent_username,
        "games_imported": r.games_imported,
        "games_skipped_existing": r.games_skipped,
        "elapsed_s": round(r.elapsed_s, 2),
        "opening_profile": {
            "games_seen": o.games_seen,
            "avg_out_of_book_ply": round(o.avg_out_of_book_ply, 1) if o.avg_out_of_book_ply else None,
            "first_move_as_white": [m.__dict__ | {"winrate": round(m.winrate, 3)} for m in o.first_move_as_white],
            "response_to_e4": [m.__dict__ | {"winrate": round(m.winrate, 3)} for m in o.response_to_e4],
            "response_to_d4": [m.__dict__ | {"winrate": round(m.winrate, 3)} for m in o.response_to_d4],
            "response_to_nf3": [m.__dict__ | {"winrate": round(m.winrate, 3)} for m in o.response_to_nf3],
            "top_openings_white": [op.__dict__ for op in o.top_openings_white],
            "top_openings_black": [op.__dict__ for op in o.top_openings_black],
        },
        "weaknesses": r.weaknesses,
        "battle_plan": r.battle_plan,
    }
