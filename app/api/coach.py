from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models import Game, Player
from app.services.coach.explainer import (
    SYSTEM_PROMPT,
    build_context_for_move,
    explain_move,
    render_user_prompt,
)
from app.services.llm.ollama import ChatMessage, OllamaClient
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


@router.post("/games/{game_id}/explain_move/stream")
async def explain_stream(
    game_id: int,
    ply: int,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> StreamingResponse:
    """Stream the LLM explanation token by token as text/plain."""
    game = (await session.execute(select(Game).where(Game.id == game_id))).scalar_one_or_none()
    if not game:
        raise HTTPException(404, "game not found")
    ctx = await build_context_for_move(session, game, ply)
    if not ctx:
        raise HTTPException(404, f"No move at ply {ply}")

    prompt = render_user_prompt(ctx)

    async def gen():
        async with OllamaClient() as client:
            async for chunk in client.chat_stream(
                [
                    ChatMessage(role="system", content=SYSTEM_PROMPT),
                    ChatMessage(role="user", content=prompt),
                ],
            ):
                yield chunk

    return StreamingResponse(
        gen(),
        media_type="text/plain; charset=utf-8",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


@router.post("/games/{game_id}/review")
async def review(
    game_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    max_items: int = 5,
    include_llm: bool = False,
) -> dict:
    """Top mistakes in the game. Returns Stockfish data instantly.

    `include_llm=true` enriches each item with an Ollama explanation — much
    slower (10-30s per item).
    """
    game = (await session.execute(select(Game).where(Game.id == game_id))).scalar_one_or_none()
    if not game:
        raise HTTPException(404, "game not found")
    me = (await session.execute(select(Player).where(Player.is_me.is_(True)))).scalar_one_or_none()
    if not me:
        raise HTTPException(404, "current player not imported")
    items = await review_player_mistakes(
        session, game, me, max_items=max_items, include_llm=include_llm,
    )
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
                "pv": i.pv,
            }
            for i in items
        ],
    }


def _serialize_live_debrief(report) -> dict:
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


def _summarize_live_debrief(payload: dict) -> dict:
    phases = payload.get("phases") or {}
    blunders_total = sum((p or {}).get("blunders", 0) for p in phases.values())
    mistakes_total = sum((p or {}).get("mistakes", 0) for p in phases.values())
    return {
        "opening": payload.get("opening"),
        "eco": payload.get("eco"),
        "my_color": payload.get("my_color"),
        "moves_analyzed": payload.get("moves_analyzed"),
        "blunders": blunders_total,
        "mistakes": mistakes_total,
        "top_cp_loss": (payload.get("top_blunders") or [{}])[0].get("cp_loss") if payload.get("top_blunders") else None,
        "exercises_generated": payload.get("exercises_generated", 0),
    }


@router.post("/live_debrief", summary="Debrief a freshly-played game and persist it")
async def live_debrief_endpoint(
    payload: LiveDebriefIn,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    from app.models import LiveDebriefReport

    report = await live_debrief(
        session,
        pgn_text=payload.pgn,
        my_color=payload.my_color,
        depth=payload.depth,
        max_blunders=payload.max_blunders,
        generate_puzzles=payload.generate_puzzles,
        explain_with_llm=payload.explain_with_llm,
    )
    out = _serialize_live_debrief(report)
    title = f"{out.get('opening') or 'Partie'} — {out.get('my_color') or '?'}"
    snap = LiveDebriefReport(
        game_id=out.get("game_id"),
        payload=out,
        summary=_summarize_live_debrief(out),
        title=title,
    )
    session.add(snap)
    await session.commit()
    out["debrief_id"] = snap.id
    out["created_at"] = snap.created_at.isoformat()
    return out


@router.get("/live_debrief", summary="List all persisted live debriefs")
async def list_live_debriefs(
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: int = 50,
) -> dict:
    from app.models import LiveDebriefReport

    rows = list((await session.execute(
        select(LiveDebriefReport)
        .order_by(LiveDebriefReport.created_at.desc())
        .limit(limit)
    )).scalars())
    return {
        "items": [
            {
                "debrief_id": r.id,
                "game_id": r.game_id,
                "created_at": r.created_at.isoformat(),
                "title": r.title,
                "summary": r.summary or {},
            }
            for r in rows
        ],
        "total": len(rows),
    }


@router.get("/live_debrief/{debrief_id}", summary="Get a persisted live debrief by ID")
async def get_live_debrief(
    debrief_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    from app.models import LiveDebriefReport

    snap = (await session.execute(
        select(LiveDebriefReport).where(LiveDebriefReport.id == debrief_id)
    )).scalar_one_or_none()
    if not snap:
        raise HTTPException(404, f"Live debrief #{debrief_id} not found")
    return {
        "debrief_id": snap.id,
        "created_at": snap.created_at.isoformat(),
        "title": snap.title,
        **(snap.payload or {}),
    }


@router.delete("/live_debrief/{debrief_id}", summary="Delete a live debrief")
async def delete_live_debrief(
    debrief_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    from app.models import LiveDebriefReport
    from sqlalchemy import delete as sa_delete

    res = await session.execute(
        sa_delete(LiveDebriefReport).where(LiveDebriefReport.id == debrief_id)
    )
    await session.commit()
    return {"deleted": res.rowcount or 0}


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

    # Lazy auto-credit: bump COACH_NOTE items whose `time_controls` filter is
    # already satisfied by games played since the plan's creation.
    from app.services.coach.plan_autocredit import auto_credit_from_games
    credit = await auto_credit_from_games(session, plan, me)
    if credit.items_updated:
        await session.commit()
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
    # Cap at target_count so the counter never overshoots, and idempotent
    # once the item is already complete.
    if it.completed_at is not None:
        await session.commit()
        return {
            "id": it.id,
            "completed_count": it.completed_count,
            "target_count": it.target_count,
            "completed_at": it.completed_at.isoformat(),
        }
    new_count = (it.completed_count or 0) + payload.delta_count
    it.completed_count = min(new_count, it.target_count)
    if it.completed_count >= it.target_count:
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


def _serialize_scout_report(r) -> dict:
    """Build the dict payload for a ScoutReport (used by POST + GET)."""
    o = r.opening_report
    p = r.profile
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
        "profile": None if p is None else {
            "games_total": p.games_total,
            "wins": p.wins,
            "losses": p.losses,
            "draws": p.draws,
            "last_10": p.last_10,
            "current_rating": p.current_rating,
            "peak_rating": p.peak_rating,
            "by_time_class": [
                {"time_class": t.time_class, "games": t.games, "wins": t.wins, "losses": t.losses, "draws": t.draws, "winrate": round(t.winrate, 3)}
                for t in p.by_time_class
            ],
            "by_color": [
                {"color": c.color, "games": c.games, "wins": c.wins, "losses": c.losses, "draws": c.draws, "winrate": round(c.winrate, 3)}
                for c in p.by_color
            ],
        },
        "phase_quality": [
            {
                "phase": ph.phase,
                "moves": ph.moves,
                "blunders": ph.blunders,
                "mistakes": ph.mistakes,
                "inaccuracies": ph.inaccuracies,
                "blunder_rate": round(ph.blunder_rate, 3),
            }
            for ph in r.phase_quality
        ],
        "vs_my_repertoire": [
            {
                "my_color": b.my_color,
                "line_san": b.line_san,
                "last_ply": b.last_ply,
                "opponent_responses": b.opponent_responses,
            }
            for b in r.vs_my_repertoire
        ],
        "vs_learning_openings": [
            {
                "opening_key": p.opening_key,
                "name": p.name,
                "base_name": p.base_name,
                "branch_label": p.branch_label,
                "user_color": p.user_color,
                "eco": p.eco,
                "summary": p.summary,
                "full_line_san": p.full_line_san,
                "games_in_opening": p.games_in_opening,
                "steps": [
                    {
                        "ply": s.ply,
                        "expected_san": s.expected_san,
                        "expected_uci": s.expected_uci,
                        "actual_responses": s.actual_responses,
                        "games_reaching": s.games_reaching,
                    }
                    for s in p.steps
                ],
            }
            for p in r.vs_learning_openings
        ],
        "structured_plan": r.structured_plan,
        "weaknesses": r.weaknesses,
        "battle_plan": r.battle_plan,
    }


def _summarize_for_index(payload: dict) -> dict:
    """Extract the small subset shown in the /scout list view."""
    p = payload.get("profile") or {}
    weak = payload.get("weaknesses") or []
    return {
        "games_total": p.get("games_total"),
        "wins": p.get("wins"),
        "losses": p.get("losses"),
        "draws": p.get("draws"),
        "current_rating": p.get("current_rating"),
        "peak_rating": p.get("peak_rating"),
        "last_10": p.get("last_10") or [],
        "top_weakness": (weak[0]["category"] if weak else None),
    }


@router.post("/scout", summary="Scout a Chess.com opponent and persist a snapshot")
async def scout(
    payload: ScoutIn,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    from app.models import ScoutSnapshot

    r = await scout_opponent(
        session,
        opponent_username=payload.opponent_username,
        max_months=payload.max_months,
        max_games=payload.max_games,
        generate_plan=payload.generate_plan,
    )
    out = _serialize_scout_report(r)
    snap = ScoutSnapshot(
        opponent_username=r.opponent_username.lower(),
        payload=out,
        summary=_summarize_for_index(out),
    )
    session.add(snap)
    await session.commit()
    out["snapshot_id"] = snap.id
    out["scouted_at"] = snap.scouted_at.isoformat()
    return out


@router.get("/scout", summary="List all scouted opponents (latest snapshot per username)")
async def list_scouts(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    from app.models import ScoutSnapshot

    rows = list((await session.execute(
        select(ScoutSnapshot).order_by(ScoutSnapshot.scouted_at.desc())
    )).scalars())
    seen: dict[str, ScoutSnapshot] = {}
    counts: dict[str, int] = {}
    for r in rows:
        counts[r.opponent_username] = counts.get(r.opponent_username, 0) + 1
        if r.opponent_username not in seen:
            seen[r.opponent_username] = r
    items = [
        {
            "opponent_username": uname,
            "last_scouted_at": snap.scouted_at.isoformat(),
            "snapshot_id": snap.id,
            "snapshot_count": counts[uname],
            "summary": snap.summary or {},
        }
        for uname, snap in seen.items()
    ]
    items.sort(key=lambda x: x["last_scouted_at"], reverse=True)
    return {"items": items, "total": len(items)}


@router.get("/scout/{username}", summary="Latest scout snapshot for an opponent")
async def get_latest_scout(
    username: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    from app.models import ScoutSnapshot

    snap = (await session.execute(
        select(ScoutSnapshot)
        .where(ScoutSnapshot.opponent_username == username.lower())
        .order_by(ScoutSnapshot.scouted_at.desc())
        .limit(1)
    )).scalar_one_or_none()
    if not snap:
        raise HTTPException(404, f"No scout snapshot found for '{username}'. Scout them first.")
    return {
        "snapshot_id": snap.id,
        "scouted_at": snap.scouted_at.isoformat(),
        **snap.payload,
    }


@router.get("/scout/{username}/history", summary="All snapshots metadata for an opponent")
async def get_scout_history(
    username: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    from app.models import ScoutSnapshot

    rows = list((await session.execute(
        select(ScoutSnapshot)
        .where(ScoutSnapshot.opponent_username == username.lower())
        .order_by(ScoutSnapshot.scouted_at.asc())
    )).scalars())
    if not rows:
        raise HTTPException(404, f"No scout snapshots found for '{username}'.")
    # Light payload: each snapshot returns only summary + top-3 weaknesses + first_move stats.
    history = []
    for snap in rows:
        payload = snap.payload or {}
        history.append({
            "snapshot_id": snap.id,
            "scouted_at": snap.scouted_at.isoformat(),
            "summary": snap.summary or {},
            "weaknesses": [
                {
                    "category": w.get("category"),
                    "phase": w.get("phase"),
                    "severity": w.get("severity"),
                    "occurrences": w.get("occurrences"),
                }
                for w in (payload.get("weaknesses") or [])[:10]
            ],
            "opening_profile": {
                "first_move_as_white": (payload.get("opening_profile") or {}).get("first_move_as_white") or [],
                "response_to_e4": (payload.get("opening_profile") or {}).get("response_to_e4") or [],
                "response_to_d4": (payload.get("opening_profile") or {}).get("response_to_d4") or [],
            },
        })
    return {"opponent_username": username.lower(), "history": history}


class SimulateScoutIn(BaseModel):
    my_color: str = Field("white", description="'white' or 'black' — your color in the simulation")
    max_undos: int = Field(0, ge=0, le=999)
    skill_override: int | None = Field(None, ge=0, le=20)


@router.post("/scout/{username}/simulate", summary="Start a play session vs Stockfish mimicking the opponent")
async def simulate_vs_scout(
    username: str,
    payload: SimulateScoutIn,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    from app.models import Player, ScoutSnapshot
    from app.services.play_engine import start_session
    from app.services.scout.enrichment import compute_opponent_engine_script

    if payload.my_color not in ("white", "black"):
        raise HTTPException(400, "my_color must be 'white' or 'black'")
    opp_color = "black" if payload.my_color == "white" else "white"

    # Resolve opponent Player row
    opp = (await session.execute(
        select(Player).where(Player.chesscom_username == username.lower())
    )).scalar_one_or_none()
    if opp is None:
        raise HTTPException(404, f"Opponent '{username}' not found — scout them first.")

    # Latest snapshot for ELO + skill heuristic
    snap = (await session.execute(
        select(ScoutSnapshot)
        .where(ScoutSnapshot.opponent_username == username.lower())
        .order_by(ScoutSnapshot.scouted_at.desc())
        .limit(1)
    )).scalar_one_or_none()

    rating = None
    if snap and snap.payload:
        rating = (snap.payload.get("profile") or {}).get("current_rating")
    # Clamp rating to Stockfish's UCI limits (1320..3190); below 1320 Stockfish
    # cannot reduce further, so we also lower the Skill Level to compensate.
    if rating is None or rating < 1000:
        sf_elo = 1320
        skill = 3
    elif rating < 1320:
        sf_elo = 1320
        skill = max(0, min(8, (rating - 600) // 100))  # ~3 at 1000, ~7 at 1300
    else:
        sf_elo = min(3190, rating)
        skill = max(0, min(20, (rating - 1000) // 100))

    if payload.skill_override is not None:
        skill = payload.skill_override

    # Build the opponent's typical opening script
    engine_script = await compute_opponent_engine_script(
        session, opp, opp_color, max_plies=14,
    )

    # Materialize the opening_moves list using opening_status='opp_simulation':
    # play_engine will force the engine to play these but won't penalize the
    # user for deviating.
    # We need to fill ALL plies (both colors) — user plies as None.
    if engine_script:
        max_ply = max(s["ply"] for s in engine_script)
        opening_moves: list[dict] = []
        script_by_ply = {s["ply"]: s for s in engine_script}
        for ply in range(1, max_ply + 1):
            is_opp = (ply % 2 == 1 and opp_color == "white") or (ply % 2 == 0 and opp_color == "black")
            if is_opp:
                s = script_by_ply.get(ply)
                if s and s["uci"]:
                    opening_moves.append({
                        "uci": s["uci"], "san": s["san"], "color": opp_color,
                    })
                else:
                    break  # script ended
            else:
                # User ply placeholder — required so indices line up with board plies.
                opening_moves.append({"uci": None, "san": None, "color": payload.my_color})
    else:
        opening_moves = []

    me_row = (await session.execute(
        select(Player).where(Player.is_me.is_(True))
    )).scalar_one_or_none()

    sess = await start_session(
        session,
        starting_fen="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        user_color=payload.my_color,
        skill_level=skill,
        sf_elo=sf_elo,
        depth=12,
        title=f"Simulation vs {username}",
        source="scout_simulation",
        source_ref={"opponent_username": username, "opp_rating": rating},
        max_undos=payload.max_undos,
        player_id=me_row.id if me_row else None,
        simulation_moves=opening_moves,
    )

    return {
        "session_id": sess.id,
        "opponent": username,
        "opp_rating": rating,
        "sf_elo": sf_elo,
        "skill_level": skill,
        "my_color": payload.my_color,
        "engine_script": engine_script,
        "script_plies": len([m for m in opening_moves if m.get("uci")]),
    }


@router.delete("/scout/{username}", summary="Delete all snapshots for an opponent")
async def delete_scout(
    username: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    from app.models import ScoutSnapshot
    from sqlalchemy import delete as sa_delete

    res = await session.execute(
        sa_delete(ScoutSnapshot).where(ScoutSnapshot.opponent_username == username.lower())
    )
    await session.commit()
    return {"deleted": res.rowcount or 0}
