"""Trainer service: pick the next repertoire card to drill and grade answers."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import chess
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import RepertoireNode
from app.models.repertoire import RepertoireColor
from app.services.trainer.srs import SRState, grade as sm2_grade


@dataclass
class NextCard:
    node: RepertoireNode
    is_new: bool  # True if no SR history yet
    due_now: bool


def _state_from_node(n: RepertoireNode) -> SRState:
    return SRState(
        ease=n.sr_ease,
        interval_days=n.sr_interval_days,
        repetitions=n.sr_repetitions,
        due_at=n.sr_due_at,
        last_reviewed_at=n.sr_last_reviewed_at,
    )


async def pick_next_due(
    session: AsyncSession,
    color: RepertoireColor | None = None,
    min_games_at_node: int | None = None,
) -> NextCard | None:
    """Return the most-overdue card, preferring popular positions in the user's data."""
    now = datetime.now(timezone.utc)
    q = select(RepertoireNode).where(RepertoireNode.is_my_move.is_(True))
    if color is not None:
        q = q.where(RepertoireNode.color == color)

    # First: cards already in review and due
    due_q = q.where(
        RepertoireNode.sr_due_at.is_not(None),
        RepertoireNode.sr_due_at <= now,
    ).order_by(RepertoireNode.sr_due_at.asc()).limit(1)
    due_card = (await session.execute(due_q)).scalar_one_or_none()
    if due_card:
        return NextCard(node=due_card, is_new=False, due_now=True)

    # Otherwise: introduce a NEW card. Prefer the ones encountered often
    # in the user's games — labels are like "d4 (167× / 60%) +2 alt".
    new_q = q.where(
        or_(RepertoireNode.sr_due_at.is_(None), RepertoireNode.sr_repetitions == 0)
    )
    # Cheap proxy for "popular": longer labels usually mean more games / alts.
    # We just order by label length DESC to surface the high-traffic positions.
    from sqlalchemy import func
    new_q = new_q.order_by(func.length(RepertoireNode.label).desc()).limit(1)
    new_card = (await session.execute(new_q)).scalar_one_or_none()
    if new_card:
        return NextCard(node=new_card, is_new=True, due_now=False)
    return None


@dataclass
class GradedAnswer:
    node_id: int
    expected_san: str | None
    expected_uci: str | None
    user_uci: str | None
    correct: bool
    grade: int
    new_interval_days: int
    new_due_at: datetime
    alternates: str | None
    expected_source: str = "user"        # "gm" | "user"
    expected_score: float | None = None   # GM winrate from user's side
    your_usual_uci: str | None = None
    your_usual_san: str | None = None
    plays_usual: bool = False
    is_best_your_usual: bool = False


def _best_move_for_node(node: RepertoireNode, board: chess.Board) -> tuple[str | None, str | None, str, float | None]:
    """Return (best_uci, best_san, source, score_pct).

    Priority: GM main line (most played) > user habit. Falls back gracefully.
    score_pct is from the user's side perspective (e.g. white winrate for white).
    """
    if node.gm_moves:
        for entry in node.gm_moves:
            uci = entry.get("uci")
            if not uci:
                continue
            try:
                mv = chess.Move.from_uci(uci)
                if mv not in board.legal_moves:
                    continue
                san = entry.get("san") or board.san(mv)
                sw = entry.get("score_white")
                is_white = str(node.color).endswith("white")
                score = sw if is_white else (1 - sw) if isinstance(sw, (int, float)) else None
                return uci, san, "gm", score
            except (ValueError, chess.InvalidMoveError):
                continue
    return node.move_uci, node.move_san, "user", None


async def grade_answer(
    session: AsyncSession,
    node: RepertoireNode,
    user_input: str,
    time_ms: int | None = None,
) -> GradedAnswer:
    """Grade the user's answer against the OBJECTIVELY BEST move when known.

    Reference move = GM main line if the node was annotated via Lichess masters,
    otherwise = user's habitual move (best available signal). The user's habit
    is always reported back so the UI can show:
      - "you played the best move (it's also your habit)" — perfect
      - "you played the best move (you usually play X — keep upgrading)"
      - "your habit ≠ best move: the best here is Y"
    """
    board = chess.Board(node.fen)
    best_uci, best_san, best_source, best_score = _best_move_for_node(node, board)

    your_usual_uci = node.move_uci
    your_usual_san = node.move_san
    is_best_your_usual = bool(best_uci and your_usual_uci and best_uci == your_usual_uci)

    user_input = (user_input or "").strip()
    user_move: chess.Move | None = None
    try:
        user_move = board.parse_san(user_input)
    except (ValueError, chess.InvalidMoveError):
        try:
            user_move = chess.Move.from_uci(user_input)
            if user_move not in board.legal_moves:
                user_move = None
        except (ValueError, chess.InvalidMoveError):
            user_move = None

    user_uci = user_move.uci() if user_move else None
    correct = bool(user_move) and best_uci is not None and (user_uci == best_uci)
    plays_usual = bool(user_move) and (user_uci == your_usual_uci)

    # SM-2 quality:
    #  - perfect match on best move (and quick): 5
    #  - best move (slower): 4
    #  - habit but not best: 1 (we WANT you to learn the upgrade)
    #  - known alternate (played at least once but neither best nor habit): 2
    #  - empty / unknown: 0
    if correct:
        q = 5 if (time_ms is not None and time_ms < 4000) else 4
    elif plays_usual:
        q = 1
    elif user_move and _is_known_alternate(node, user_uci or ""):
        q = 2
    else:
        q = 0 if user_move is None else 1

    state = _state_from_node(node)
    result = sm2_grade(state, q)

    node.sr_ease = result.new.ease
    node.sr_interval_days = result.new.interval_days
    node.sr_repetitions = result.new.repetitions
    node.sr_due_at = result.new.due_at
    node.sr_last_reviewed_at = result.new.last_reviewed_at
    await session.commit()

    return GradedAnswer(
        node_id=node.id,
        expected_san=best_san or "",
        expected_uci=best_uci or "",
        user_uci=user_uci,
        correct=correct,
        grade=q,
        new_interval_days=result.new.interval_days,
        new_due_at=result.new.due_at,
        alternates=node.notes,
        expected_source=best_source,
        expected_score=best_score,
        your_usual_uci=your_usual_uci,
        your_usual_san=your_usual_san,
        plays_usual=plays_usual,
        is_best_your_usual=is_best_your_usual,
    )


def _is_known_alternate(node: RepertoireNode, uci: str) -> bool:
    """Cheap check against the human-readable notes field built at repertoire time."""
    # Notes is a table of SAN moves, not UCI — but we can also accept it as a fallback.
    if not node.notes:
        return False
    board = chess.Board(node.fen)
    try:
        san = board.san(chess.Move.from_uci(uci))
    except (ValueError, chess.InvalidMoveError):
        return False
    return san in node.notes


@dataclass
class TrainerStats:
    total_nodes: int
    new_nodes: int
    learning_nodes: int
    due_today: int
    next_due_at: datetime | None


async def compute_stats(
    session: AsyncSession, color: RepertoireColor | None = None
) -> TrainerStats:
    from sqlalchemy import func

    now = datetime.now(timezone.utc)
    base = select(RepertoireNode).where(RepertoireNode.is_my_move.is_(True))
    if color is not None:
        base = base.where(RepertoireNode.color == color)

    total = (await session.execute(
        select(func.count()).select_from(base.subquery())
    )).scalar_one()
    new = (await session.execute(
        select(func.count()).select_from(
            base.where(RepertoireNode.sr_repetitions == 0).subquery()
        )
    )).scalar_one()
    learning = (await session.execute(
        select(func.count()).select_from(
            base.where(RepertoireNode.sr_repetitions > 0).subquery()
        )
    )).scalar_one()
    due_today = (await session.execute(
        select(func.count()).select_from(
            base.where(RepertoireNode.sr_due_at.is_not(None), RepertoireNode.sr_due_at <= now).subquery()
        )
    )).scalar_one()
    next_due = (await session.execute(
        select(func.min(RepertoireNode.sr_due_at))
        .where(RepertoireNode.is_my_move.is_(True))
        .where(RepertoireNode.sr_due_at.is_not(None))
    )).scalar()
    return TrainerStats(
        total_nodes=total,
        new_nodes=new,
        learning_nodes=learning,
        due_today=due_today,
        next_due_at=next_due,
    )
