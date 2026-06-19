"""Exercise generator: builds puzzles from analyzed blunders + idempotent."""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models import Exercise
from app.models.analysis import MoveQuality
from app.models.exercise import ExerciseKind
from app.services.exercises.generator import generate_for_player
from tests.factories import attach_analysis, make_game, make_player


pytestmark = pytest.mark.db


_TACTICAL_PGN = "1. e4 e5 2. Bc4 Bc5 3. Qh5 Nc6 *"


async def test_generates_one_exercise_per_player_blunder(db_session) -> None:
    me = await make_player(db_session, "alice", is_me=True)
    opp = await make_player(db_session, "bob", is_me=False)
    game = await make_game(db_session, me, opp, pgn=_TACTICAL_PGN, external_id="g1")

    # Ply 5 = alice plays Qh5 (white move 3); fake a blunder analysis.
    moves = (await db_session.execute(
        select(__import__("app.models", fromlist=["Move"]).Move)
        .order_by("ply")
    )).scalars().all()
    blunder_move = next(m for m in moves if m.ply == 5)
    await attach_analysis(
        db_session, blunder_move,
        quality=MoveQuality.BLUNDER, cp_loss=400,
        best_move_uci="g1f3", best_move_san="Nf3",
        pv=["g1f3", "g8f6"],
    )
    await db_session.commit()

    stats = await generate_for_player(db_session, me)
    assert stats.inserted == 1
    assert stats.failed == 0

    ex_rows = list((await db_session.execute(select(Exercise))).scalars())
    assert len(ex_rows) == 1
    assert ex_rows[0].source_move_id == blunder_move.id
    assert ex_rows[0].solution_uci == ["g1f3", "g8f6"]


async def test_generator_is_idempotent(db_session) -> None:
    me = await make_player(db_session, "alice", is_me=True)
    opp = await make_player(db_session, "bob", is_me=False)
    game = await make_game(db_session, me, opp, pgn=_TACTICAL_PGN, external_id="g1")

    from app.models import Move
    move = (await db_session.execute(
        select(Move).where(Move.ply == 5)
    )).scalar_one()
    await attach_analysis(
        db_session, move, quality=MoveQuality.BLUNDER, cp_loss=400,
        best_move_uci="g1f3", best_move_san="Nf3", pv=["g1f3"],
    )
    await db_session.commit()

    s1 = await generate_for_player(db_session, me)
    s2 = await generate_for_player(db_session, me)
    assert s1.inserted == 1
    assert s2.inserted == 0
    assert s2.skipped_existing == 1


async def test_skips_opponent_blunders(db_session) -> None:
    me = await make_player(db_session, "alice", is_me=True)
    opp = await make_player(db_session, "bob", is_me=False)
    game = await make_game(db_session, me, opp, pgn=_TACTICAL_PGN, external_id="g1")

    from app.models import Move
    # Ply 4 = bob (black) plays Bc5 -> analyze as bob's blunder.
    bob_move = (await db_session.execute(
        select(Move).where(Move.ply == 4)
    )).scalar_one()
    await attach_analysis(
        db_session, bob_move, quality=MoveQuality.BLUNDER, cp_loss=400,
        best_move_uci="e7e6", best_move_san="e6", pv=["e7e6"],
    )
    await db_session.commit()

    stats = await generate_for_player(db_session, me)
    assert stats.inserted == 0     # only alice's blunders count


async def test_endgame_kind_assigned_when_ply_above_40(db_session) -> None:
    me = await make_player(db_session, "alice", is_me=True)
    opp = await make_player(db_session, "bob", is_me=False)
    # Build a 50-ply dummy PGN where ply 45 is a blunder
    long_pgn = (
        "1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 4. Ba4 Nf6 5. O-O Be7 "
        "6. Re1 b5 7. Bb3 d6 8. c3 O-O 9. h3 Nb8 10. d4 Nbd7 "
        "11. Nbd2 Bb7 12. Bc2 Re8 13. Nf1 Bf8 14. Ng3 g6 "
        "15. a4 c5 16. d5 c4 17. Bg5 h6 18. Be3 Nc5 "
        "19. Qd2 h5 20. Bg5 Be7 21. Nxh5 *"
    )
    game = await make_game(db_session, me, opp, pgn=long_pgn, external_id="g_long")

    from app.models import Move
    high_ply_move = (await db_session.execute(
        select(Move).where(Move.ply >= 41).order_by("ply").limit(1)
    )).scalar_one_or_none()
    if not high_ply_move:
        pytest.skip("PGN didn't reach ply 41")

    await attach_analysis(
        db_session, high_ply_move, quality=MoveQuality.BLUNDER, cp_loss=400,
        best_move_uci="e1g1", best_move_san="Kg1", pv=["e1g1"],
    )
    await db_session.commit()
    await generate_for_player(db_session, me)
    ex = (await db_session.execute(select(Exercise))).scalars().first()
    assert ex is not None
    assert ex.kind == ExerciseKind.ENDGAME
