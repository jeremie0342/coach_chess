"""Build the user's empirical opening repertoire from their played games.

For each color, we walk every game and collect:
    (position_fen, my_move_uci) -> {games, wins, losses, draws}

We then persist this as a tree of RepertoireNode rows where each node holds:
    - The FEN reached (after the previous opponent move, with us to play)
    - My most-played continuation (move_uci/san)
    - SR scheduling fields (used by the trainer in step 6)

We limit depth to MAX_PLY_DEPTH plies — there's no point treating move 40
as "opening repertoire".
"""
from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone

import chess
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Game, Move, Player, RepertoireNode
from app.models.game import GameResult
from app.models.repertoire import RepertoireColor

logger = logging.getLogger(__name__)


MAX_PLY_DEPTH = 24   # repertoire ends ~12 moves deep
MIN_NODE_GAMES = 1   # keep all encountered positions


@dataclass
class NodeStats:
    fen: str
    parent_fen: str | None
    color: RepertoireColor
    is_my_move: bool
    # For each candidate move played from this position:
    move_counts: dict[str, dict] = field(default_factory=dict)
    games: int = 0

    def record(self, move_uci: str, move_san: str, my_result: str) -> None:
        m = self.move_counts.setdefault(
            move_uci,
            {"uci": move_uci, "san": move_san, "n": 0, "wins": 0, "losses": 0, "draws": 0},
        )
        m["n"] += 1
        m[{"win": "wins", "loss": "losses", "draw": "draws"}[my_result]] += 1
        self.games += 1


def _my_result(game: Game, player_id: int) -> str:
    if game.result == GameResult.DRAW:
        return "draw"
    if (
        (game.white_player_id == player_id and game.result == GameResult.WHITE_WIN)
        or (game.black_player_id == player_id and game.result == GameResult.BLACK_WIN)
    ):
        return "win"
    return "loss"


async def build_repertoire(
    session: AsyncSession,
    player: Player,
    max_depth: int = MAX_PLY_DEPTH,
) -> dict:
    """Rebuild the repertoire tree from scratch for the given player.

    Idempotent: deletes existing RepertoireNode rows for this player's color
    branches and re-inserts.
    """
    # Stats key: (color, fen) -> NodeStats
    stats: dict[tuple[RepertoireColor, str], NodeStats] = {}

    # Pull all games where player is white or black
    games_q = (
        select(Game)
        .where(
            (Game.white_player_id == player.id) | (Game.black_player_id == player.id)
        )
    )
    games = list((await session.execute(games_q)).scalars())

    for game in games:
        my_color = (
            RepertoireColor.WHITE
            if game.white_player_id == player.id
            else RepertoireColor.BLACK
        )
        my_is_white = my_color == RepertoireColor.WHITE
        my_result_str = _my_result(game, player.id)

        # Pull moves in order
        moves_q = (
            select(Move).where(Move.game_id == game.id).order_by(Move.ply)
        )
        moves = list((await session.execute(moves_q)).scalars())

        for m in moves:
            if m.ply > max_depth:
                break
            # Only record positions where it's MY turn to play
            if m.is_white != my_is_white:
                continue
            key = (my_color, m.fen_before)
            node = stats.get(key)
            if node is None:
                node = NodeStats(
                    fen=m.fen_before,
                    parent_fen=None,
                    color=my_color,
                    is_my_move=True,
                )
                stats[key] = node
            node.record(m.uci, m.san, my_result_str)

    # Now upsert: simple strategy — wipe & re-create for these colors
    await session.execute(
        delete(RepertoireNode).where(RepertoireNode.color.in_([RepertoireColor.WHITE, RepertoireColor.BLACK]))
    )

    now = datetime.now(timezone.utc)
    inserted = 0
    for (color, fen), st in stats.items():
        # Most-played continuation from this position
        if not st.move_counts:
            continue
        best = max(st.move_counts.values(), key=lambda d: d["n"])
        wr = (best["wins"] + 0.5 * best["draws"]) / max(best["n"], 1)
        label_bits = [f"{best['san']} ({best['n']}× / {wr:.0%})"]
        if len(st.move_counts) > 1:
            label_bits.append(f"+{len(st.move_counts) - 1} alt")
        node = RepertoireNode(
            color=color,
            fen=fen,
            move_uci=best["uci"],
            move_san=best["san"],
            is_my_move=True,
            is_main_line=True,
            label=" ".join(label_bits),
            notes=_render_alts(st.move_counts),
            sr_due_at=now,
        )
        session.add(node)
        inserted += 1

    await session.commit()
    logger.info("Repertoire rebuilt for %s: %d nodes", player.chesscom_username, inserted)
    return {
        "player": player.chesscom_username,
        "nodes_inserted": inserted,
        "positions_seen": len(stats),
    }


def _render_alts(move_counts: dict[str, dict]) -> str:
    items = sorted(move_counts.values(), key=lambda d: -d["n"])
    lines = []
    for m in items:
        wr = (m["wins"] + 0.5 * m["draws"]) / max(m["n"], 1)
        lines.append(
            f"{m['san']:>6}  n={m['n']:>3}  W/L/D={m['wins']}/{m['losses']}/{m['draws']}  wr={wr:.0%}"
        )
    return "\n".join(lines)
