"""Game listing + detail endpoints for the web frontend.

The Unity client used /coach/me/dashboard for recent games only. The Next.js
frontend needs a proper paginated list of all imported games, plus a detail
endpoint that exposes the full move list with Stockfish analysis (eval, quality,
tags) so the Game Review screen can render an eval graph and click-to-ply.
"""
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models import Game, Move, MoveAnalysis, Opening, Player
from app.models.game import GameResult

router = APIRouter(prefix="/games", tags=["games"])


class GameRow(BaseModel):
    id: int
    url: str | None
    played_at: datetime | None
    color: Literal["white", "black"]
    result: Literal["win", "loss", "draw", "unknown"]
    my_rating: int | None
    opp_rating: int | None
    opp_username: str | None
    opening: str | None
    eco: str | None
    time_class: str | None
    ply_count: int
    analysis_status: str
    my_out_of_book_ply: int | None


class GamesListResponse(BaseModel):
    total: int
    items: list[GameRow]


class MoveRow(BaseModel):
    ply: int
    san: str
    uci: str
    fen_before: str
    fen_after: str
    side: Literal["white", "black"]
    eval_cp: int | None = None
    eval_mate: int | None = None
    eval_cp_before: int | None = None
    eval_mate_before: int | None = None
    best_uci: str | None = None
    best_san: str | None = None
    cp_loss: int | None = None
    quality: str | None = None
    tags: list[str] | None = None
    # Stockfish principal variation starting from the position BEFORE this move:
    # the sequence the engine would have played starting with best_uci. UCI list.
    pv: list[str] | None = None


class GameDetail(BaseModel):
    id: int
    url: str | None
    pgn: str
    initial_fen: str | None
    played_at: datetime | None
    color: Literal["white", "black"]
    result: Literal["win", "loss", "draw", "unknown"]
    my_rating: int | None
    opp_rating: int | None
    opp_username: str | None
    opening: str | None
    eco: str | None
    time_class: str | None
    ply_count: int
    analysis_status: str
    my_out_of_book_ply: int | None
    moves: list[MoveRow] = Field(default_factory=list)


def _result_label(g: Game, is_white: bool) -> str:
    if g.result == GameResult.DRAW:
        return "draw"
    if (is_white and g.result == GameResult.WHITE_WIN) or (
        not is_white and g.result == GameResult.BLACK_WIN
    ):
        return "win"
    if g.result == GameResult.UNKNOWN:
        return "unknown"
    return "loss"


async def _me(session: AsyncSession) -> Player:
    me = (await session.execute(select(Player).where(Player.is_me.is_(True)))).scalar_one_or_none()
    if not me:
        raise HTTPException(404, "current player not imported")
    return me


@router.get("", response_model=GamesListResponse, summary="Paginated list of games (mine, scouted, or any)")
async def list_games(
    session: Annotated[AsyncSession, Depends(get_session)],
    color: Literal["white", "black"] | None = None,
    result: Literal["win", "loss", "draw"] | None = None,
    time_class: str | None = None,
    eco: str | None = None,
    analysis_status: str | None = None,
    scope: Annotated[Literal["mine", "opponents", "all"], Query(description="mine = my games (default), opponents = imported scout games, all = everything in DB")] = "mine",
    opponent: Annotated[str | None, Query(description="Filter by opponent chess.com username (substring match)")] = None,
    opening: Annotated[str | None, Query(description="Search in opening name (substring match, case-insensitive)")] = None,
    q: Annotated[str | None, Query(description="Free-text search across opponent username + opening name + ECO + game ID")] = None,
    game_id: Annotated[int | None, Query(description="Jump to a specific game ID")] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> GamesListResponse:
    me = await _me(session)

    where = []
    # Scope controls which games we look at
    if scope == "mine":
        where.append(or_(Game.white_player_id == me.id, Game.black_player_id == me.id))
    elif scope == "opponents":
        where.append(Game.white_player_id != me.id)
        where.append(Game.black_player_id != me.id)
    # "all" → no scope filter

    # Direct ID jump
    if game_id is not None:
        where.append(Game.id == game_id)

    if color == "white" and scope == "mine":
        where.append(Game.white_player_id == me.id)
    elif color == "black" and scope == "mine":
        where.append(Game.black_player_id == me.id)
    if time_class:
        where.append(Game.time_class == time_class)
    if eco:
        where.append(Game.eco.ilike(f"{eco}%"))
    if analysis_status:
        where.append(Game.analysis_status == analysis_status)
    if opening:
        where.append(Game.opening_name.ilike(f"%{opening}%"))

    # Opponent filter (or free-text q) — join Player on the opposite side
    if opponent or q:
        sub = select(Player.id).where(
            Player.chesscom_username.ilike(f"%{(opponent or q).lower()}%")
        )
        opp_ids_q = (await session.execute(sub)).scalars().all()
        if opp_ids_q:
            ids = list(opp_ids_q)
            text_filter = or_(
                Game.white_player_id.in_(ids),
                Game.black_player_id.in_(ids),
            )
            if q:
                # Also try matching opening / eco / numeric ID
                extra = [
                    Game.opening_name.ilike(f"%{q}%"),
                    Game.eco.ilike(f"%{q}%"),
                ]
                if q.isdigit():
                    extra.append(Game.id == int(q))
                where.append(or_(text_filter, *extra))
            else:
                where.append(text_filter)
        elif q:
            # No opponent matched — still try opening / eco / id
            extra = [
                Game.opening_name.ilike(f"%{q}%"),
                Game.eco.ilike(f"%{q}%"),
            ]
            if q.isdigit():
                extra.append(Game.id == int(q))
            where.append(or_(*extra))
        else:
            # Opponent string provided but no match → empty result
            where.append(Game.id == -1)

    if result and scope == "mine":
        if result == "draw":
            where.append(Game.result == GameResult.DRAW)
        elif result == "win":
            where.append(or_(
                (Game.white_player_id == me.id) & (Game.result == GameResult.WHITE_WIN),
                (Game.black_player_id == me.id) & (Game.result == GameResult.BLACK_WIN),
            ))
        else:
            where.append(or_(
                (Game.white_player_id == me.id) & (Game.result == GameResult.BLACK_WIN),
                (Game.black_player_id == me.id) & (Game.result == GameResult.WHITE_WIN),
            ))

    total = (await session.execute(select(func.count(Game.id)).where(*where))).scalar_one()

    sql_q = (
        select(Game, Opening.name.label("op_name"))
        .outerjoin(Opening, Opening.id == Game.deepest_opening_id)
        .where(*where)
        .order_by(Game.played_at.desc().nulls_last())
        .limit(limit)
        .offset(offset)
    )
    rows = (await session.execute(sql_q)).all()

    items: list[GameRow] = []
    for g, op_name in rows:
        # For non-mine games, treat white as "me" for serialization symmetry
        user_played = g.white_player_id == me.id or g.black_player_id == me.id
        perspective_id = me.id if user_played else g.white_player_id
        is_white = g.white_player_id == perspective_id
        opp_id = g.black_player_id if is_white else g.white_player_id
        opp = (await session.execute(select(Player).where(Player.id == opp_id))).scalar_one_or_none()
        items.append(GameRow(
            id=g.id,
            url=g.url,
            played_at=g.played_at,
            color="white" if is_white else "black",
            result=_result_label(g, is_white),  # type: ignore
            my_rating=g.white_rating if is_white else g.black_rating,
            opp_rating=g.black_rating if is_white else g.white_rating,
            opp_username=opp.chesscom_username if opp else None,
            opening=op_name or g.opening_name,
            eco=g.eco,
            time_class=str(g.time_class) if g.time_class else None,
            ply_count=g.ply_count,
            analysis_status=g.analysis_status,
            my_out_of_book_ply=g.my_out_of_book_ply,
        ))
    return GamesListResponse(total=total, items=items)


@router.get(
    "/me/critical_positions",
    summary="Critical positions from my recent lost games — moments where I blundered",
)
async def critical_positions(
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=50)] = 12,
    min_cp_loss: Annotated[int, Query(ge=50)] = 150,
) -> dict:
    """Worst moments from my recent lost games so I can practice them.

    Each item gives the FEN the user faced before the blunder, the blunder
    move, the best move, and the game context — so the frontend can launch a
    Play vs Stockfish session from that exact position.
    """
    me = await _me(session)
    from sqlalchemy import desc
    from app.models import Move, MoveAnalysis
    from app.models.analysis import MoveQuality
    from app.models.game import GameResult

    # Only count user moves (his own blunders, not the opponent's).
    my_is_white_case = case(
        (Game.white_player_id == me.id, Move.is_white.is_(True)),
        else_=Move.is_white.is_(False),
    )
    is_loss = or_(
        (Game.white_player_id == me.id) & (Game.result == GameResult.BLACK_WIN),
        (Game.black_player_id == me.id) & (Game.result == GameResult.WHITE_WIN),
    )

    rows = list((await session.execute(
        select(
            Move.id, Move.game_id, Move.ply, Move.san, Move.uci,
            Move.fen_before, Move.fen_after,
            MoveAnalysis.best_move_san, MoveAnalysis.best_move_uci,
            MoveAnalysis.cp_loss, MoveAnalysis.quality, MoveAnalysis.pv,
            Game.played_at, Game.opening_name, Game.eco,
        )
        .join(MoveAnalysis, MoveAnalysis.move_id == Move.id)
        .join(Game, Game.id == Move.game_id)
        .where(or_(Game.white_player_id == me.id, Game.black_player_id == me.id))
        .where(is_loss)
        .where(my_is_white_case)
        .where(MoveAnalysis.quality.in_([MoveQuality.BLUNDER, MoveQuality.MISTAKE]))
        .where(MoveAnalysis.cp_loss >= min_cp_loss)
        .order_by(desc(Game.played_at), desc(MoveAnalysis.cp_loss))
        .limit(limit)
    )).all())

    items = []
    for r in rows:
        items.append({
            "move_id": r[0],
            "game_id": r[1],
            "ply": r[2],
            "played_san": r[3],
            "played_uci": r[4],
            "fen_before": r[5],
            "fen_after": r[6],
            "best_san": r[7],
            "best_uci": r[8],
            "cp_loss": r[9],
            "quality": str(r[10]) if r[10] else None,
            "pv": r[11],
            "played_at": r[12].isoformat() if r[12] else None,
            "opening": r[13],
            "eco": r[14],
        })

    return {"player": me.chesscom_username, "count": len(items), "items": items}


@router.get(
    "/me/next_lab_target",
    summary="Oldest-imported unreviewed loss for the Lab",
)
async def next_lab_target(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    """Return the next game the user should analyze in the Lab.

    Priority: most recent loss (or draw) the user hasn't yet opened in the Lab.
    Falls back to the most recent loss if none unreviewed.
    """
    me = await _me(session)
    base = (
        select(Game.id, Game.played_at, Game.opening_name, Game.eco, Game.result)
        .where(or_(Game.white_player_id == me.id, Game.black_player_id == me.id))
        .where(Game.played_at.is_not(None))
        .order_by(Game.played_at.desc().nulls_last())
    )
    # Filter "loss for me"
    from app.models.game import GameResult
    is_loss = or_(
        (Game.white_player_id == me.id) & (Game.result == GameResult.BLACK_WIN),
        (Game.black_player_id == me.id) & (Game.result == GameResult.WHITE_WIN),
    )
    unreviewed = (await session.execute(
        base.where(is_loss).where(Game.lab_reviewed_at.is_(None)).limit(1)
    )).first()
    if unreviewed:
        gid, played_at, opening, eco, _result = unreviewed
        return {"has_target": True, "needs_review": True,
                "game_id": gid, "played_at": played_at, "opening": opening, "eco": eco}
    # Already all caught up — return latest loss as a soft suggestion
    fallback = (await session.execute(base.where(is_loss).limit(1))).first()
    if fallback:
        gid, played_at, opening, eco, _result = fallback
        return {"has_target": True, "needs_review": False,
                "game_id": gid, "played_at": played_at, "opening": opening, "eco": eco}
    return {"has_target": False}


@router.get("/{game_id}", response_model=GameDetail, summary="Full game with annotated moves")
async def game_detail(
    game_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    include_moves: bool = True,
) -> GameDetail:
    me = await _me(session)
    g = (await session.execute(select(Game).where(Game.id == game_id))).scalar_one_or_none()
    if not g:
        raise HTTPException(404, "game not found")
    # Determine the "perspective" player:
    #  - if is_me played this game → me
    #  - otherwise (scout games) → take the white player as perspective so
    #    fields like "my_rating" still serialize cleanly.
    user_played = g.white_player_id == me.id or g.black_player_id == me.id
    if user_played:
        perspective_id = me.id
        # First-touch lab review marker. Set only once and only on my own games.
        if g.lab_reviewed_at is None:
            from datetime import datetime, timezone
            g.lab_reviewed_at = datetime.now(timezone.utc)
            await session.commit()
    else:
        perspective_id = g.white_player_id

    is_white = g.white_player_id == perspective_id
    opp_id = g.black_player_id if is_white else g.white_player_id
    opp = (await session.execute(select(Player).where(Player.id == opp_id))).scalar_one_or_none()
    op_name = None
    if g.deepest_opening_id:
        op = (await session.execute(select(Opening).where(Opening.id == g.deepest_opening_id))).scalar_one_or_none()
        op_name = op.name if op else None

    moves: list[MoveRow] = []
    if include_moves:
        rows = (await session.execute(
            select(Move, MoveAnalysis)
            .outerjoin(MoveAnalysis, MoveAnalysis.move_id == Move.id)
            .where(Move.game_id == g.id)
            .order_by(Move.ply)
        )).all()
        for m, a in rows:
            moves.append(MoveRow(
                ply=m.ply,
                san=m.san,
                uci=m.uci,
                fen_before=m.fen_before,
                fen_after=m.fen_after,
                side="white" if m.ply % 2 == 1 else "black",
                # Prefer deep re-analysis (depth 28) when present, else regular (depth 20).
                eval_cp=(a.deep_eval_cp if (a and a.deep_eval_cp is not None) else (a.eval_cp if a else None)),
                eval_mate=(a.deep_eval_mate if (a and a.deep_eval_mate is not None) else (a.eval_mate if a else None)),
                eval_cp_before=getattr(a, "eval_cp_before", None) if a else None,
                eval_mate_before=getattr(a, "eval_mate_before", None) if a else None,
                best_uci=(a.deep_best_uci if (a and a.deep_best_uci) else (a.best_move_uci if a else None)),
                best_san=(a.deep_best_san if (a and a.deep_best_san) else (a.best_move_san if a else None)),
                cp_loss=getattr(a, "cp_loss", None) if a else None,
                quality=str(getattr(a, "quality", None)) if a and getattr(a, "quality", None) else None,
                tags=getattr(a, "tags", None) if a else None,
                pv=(a.deep_pv if (a and a.deep_pv) else (a.pv if a else None)),
            ))

    return GameDetail(
        id=g.id,
        url=g.url,
        pgn=g.pgn,
        initial_fen=g.initial_fen,
        played_at=g.played_at,
        color="white" if is_white else "black",
        result=_result_label(g, is_white),  # type: ignore
        my_rating=g.white_rating if is_white else g.black_rating,
        opp_rating=g.black_rating if is_white else g.white_rating,
        opp_username=opp.chesscom_username if opp else None,
        opening=op_name or g.opening_name,
        eco=g.eco,
        time_class=str(g.time_class) if g.time_class else None,
        ply_count=g.ply_count,
        analysis_status=g.analysis_status,
        my_out_of_book_ply=g.my_out_of_book_ply,
        moves=moves,
    )
