"""Extra scout intel beyond opening profile + weakness list.

This is the data that turns a scout report into actionable prep:
  - opponent profile (rating, recent form, time-control split, color winrate)
  - phase quality (where they crack: opening / middlegame / endgame)
  - cross-reference with MY repertoire (what do they play against my main lines)
  - deterministic, rule-based battle plan (LLM-free, instantaneous)
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Game, Move, MoveAnalysis, OpeningProgress, Player
from app.models.analysis import MoveQuality
from app.models.game import GameResult
from app.models.opening_progress import OpeningProgressStatus
from app.services import opening_trainer as ot


# ---------------------------------------------------------------------------
# Opponent profile
# ---------------------------------------------------------------------------

@dataclass
class TimeClassStats:
    time_class: str
    games: int
    wins: int
    losses: int
    draws: int

    @property
    def winrate(self) -> float:
        return (self.wins + 0.5 * self.draws) / max(self.games, 1)


@dataclass
class ColorStats:
    color: str  # "white" | "black"
    games: int
    wins: int
    losses: int
    draws: int

    @property
    def winrate(self) -> float:
        return (self.wins + 0.5 * self.draws) / max(self.games, 1)


@dataclass
class OpponentProfile:
    games_total: int
    wins: int
    losses: int
    draws: int
    last_10: list[str] = field(default_factory=list)  # "W"/"L"/"D"
    current_rating: int | None = None
    peak_rating: int | None = None
    by_time_class: list[TimeClassStats] = field(default_factory=list)
    by_color: list[ColorStats] = field(default_factory=list)


def _outcome_for(player_id: int, white_id: int, black_id: int, result: GameResult) -> str:
    if result == GameResult.DRAW:
        return "D"
    won_as_white = white_id == player_id and result == GameResult.WHITE_WIN
    won_as_black = black_id == player_id and result == GameResult.BLACK_WIN
    return "W" if (won_as_white or won_as_black) else "L"


async def compute_opponent_profile(
    session: AsyncSession, player: Player
) -> OpponentProfile:
    games = list((await session.execute(
        select(Game)
        .where(or_(Game.white_player_id == player.id, Game.black_player_id == player.id))
        .order_by(Game.played_at.desc().nullslast())
    )).scalars())

    profile = OpponentProfile(games_total=len(games), wins=0, losses=0, draws=0)
    by_tc: dict[str, list[Game]] = {}
    by_color: dict[str, list[Game]] = {"white": [], "black": []}
    ratings: list[int] = []

    for g in games:
        outcome = _outcome_for(player.id, g.white_player_id, g.black_player_id, g.result)
        if outcome == "W":
            profile.wins += 1
        elif outcome == "L":
            profile.losses += 1
        else:
            profile.draws += 1

        tc = (g.time_class or "unknown")
        by_tc.setdefault(tc, []).append(g)

        if g.white_player_id == player.id:
            by_color["white"].append(g)
            if g.white_rating is not None:
                ratings.append(g.white_rating)
        else:
            by_color["black"].append(g)
            if g.black_rating is not None:
                ratings.append(g.black_rating)

    profile.last_10 = [
        _outcome_for(player.id, g.white_player_id, g.black_player_id, g.result)
        for g in games[:10]
    ]
    if ratings:
        # ratings[0] is the most-recent game's rating.
        profile.current_rating = ratings[0]
        profile.peak_rating = max(ratings)

    for tc, gs in by_tc.items():
        w = sum(1 for g in gs if _outcome_for(player.id, g.white_player_id, g.black_player_id, g.result) == "W")
        l = sum(1 for g in gs if _outcome_for(player.id, g.white_player_id, g.black_player_id, g.result) == "L")
        d = len(gs) - w - l
        profile.by_time_class.append(TimeClassStats(time_class=tc, games=len(gs), wins=w, losses=l, draws=d))
    profile.by_time_class.sort(key=lambda t: t.games, reverse=True)

    for color, gs in by_color.items():
        w = sum(1 for g in gs if _outcome_for(player.id, g.white_player_id, g.black_player_id, g.result) == "W")
        l = sum(1 for g in gs if _outcome_for(player.id, g.white_player_id, g.black_player_id, g.result) == "L")
        d = len(gs) - w - l
        profile.by_color.append(ColorStats(color=color, games=len(gs), wins=w, losses=l, draws=d))

    return profile


# ---------------------------------------------------------------------------
# Phase quality
# ---------------------------------------------------------------------------

OPENING_MAX_PLY = 20
MIDDLEGAME_MAX_PLY = 60


def _phase_of(ply: int) -> str:
    if ply <= OPENING_MAX_PLY:
        return "opening"
    if ply <= MIDDLEGAME_MAX_PLY:
        return "middlegame"
    return "endgame"


@dataclass
class PhaseQualityStats:
    phase: str
    moves: int
    blunders: int
    mistakes: int
    inaccuracies: int

    @property
    def blunder_rate(self) -> float:
        return self.blunders / max(self.moves, 1)


async def compute_phase_quality(
    session: AsyncSession, player: Player
) -> list[PhaseQualityStats]:
    """How often the opponent makes blunders/mistakes/inaccuracies per phase.

    Counts only THE OPPONENT'S moves (not their opponents'). Requires analysed
    games — moves without a MoveAnalysis row are skipped.
    """
    games_q = select(Game.id, Game.white_player_id).where(
        or_(Game.white_player_id == player.id, Game.black_player_id == player.id)
    )
    games = {g.id: g.white_player_id for g in (await session.execute(games_q)).all()}
    if not games:
        return []

    rows = (await session.execute(
        select(Move.ply, Move.is_white, Move.game_id, MoveAnalysis.quality)
        .join(MoveAnalysis, MoveAnalysis.move_id == Move.id)
        .where(Move.game_id.in_(list(games.keys())))
    )).all()

    buckets = {
        "opening": PhaseQualityStats("opening", 0, 0, 0, 0),
        "middlegame": PhaseQualityStats("middlegame", 0, 0, 0, 0),
        "endgame": PhaseQualityStats("endgame", 0, 0, 0, 0),
    }
    for ply, is_white, game_id, quality in rows:
        # Was this move played BY the opponent?
        if (games[game_id] == player.id) != bool(is_white):
            continue
        phase = _phase_of(ply)
        b = buckets[phase]
        b.moves += 1
        if quality == MoveQuality.BLUNDER:
            b.blunders += 1
        elif quality == MoveQuality.MISTAKE:
            b.mistakes += 1
        elif quality == MoveQuality.INACCURACY:
            b.inaccuracies += 1

    return [buckets[p] for p in ("opening", "middlegame", "endgame")]


# ---------------------------------------------------------------------------
# Cross-reference with MY repertoire
# ---------------------------------------------------------------------------

@dataclass
class RepertoireBranch:
    my_color: str          # I play this opening as white/black
    line_san: list[str]    # the SAN moves leading to the divergence
    last_ply: int          # ply right after my last book move
    opponent_responses: list[dict]  # [{san, uci, games, winrate}]


async def compute_vs_my_repertoire(
    session: AsyncSession, me: Player, opponent: Player, top_branches: int = 8,
) -> list[RepertoireBranch]:
    """For each of MY main lines, what does the opponent typically play in response?

    Strategy:
      - For my games (is_me=True) take the most-played opening sequences as
        white and as black, up to ply 6.
      - For each such sequence, search the opponent's games where the same
        first N plies match, and aggregate the opponent's NEXT move with
        outcomes.
    """
    out: list[RepertoireBranch] = []

    for my_color in ("white", "black"):
        # 1. Find my most-played sequence of opening plies (up to 6) as this color
        my_color_filter = (
            Game.white_player_id == me.id if my_color == "white"
            else Game.black_player_id == me.id
        )

        # Try sequences at decreasing depth (6 -> 4 -> 2) until we find one
        # frequent enough to cross-reference.
        for depth in (6, 4, 2):
            seq_rows = (await session.execute(
                select(
                    Move.uci, Move.san, Move.ply, Move.game_id
                )
                .join(Game, Game.id == Move.game_id)
                .where(my_color_filter)
                .where(Move.ply <= depth)
                .order_by(Move.game_id, Move.ply)
            )).all()
            if not seq_rows:
                continue

            # Build per-game ply→uci dict
            by_game: dict[int, list[tuple[int, str, str]]] = {}
            for uci, san, ply, gid in seq_rows:
                by_game.setdefault(gid, []).append((ply, uci, san))

            # Reduce to (uci-tuple, san-tuple) keys
            counts: dict[tuple, dict] = {}
            for gid, plies in by_game.items():
                if len(plies) < depth:
                    continue
                plies.sort()
                ucis = tuple(p[1] for p in plies)
                sans = tuple(p[2] for p in plies)
                k = ucis
                if k not in counts:
                    counts[k] = {"sans": sans, "games": 0}
                counts[k]["games"] += 1

            if not counts:
                continue

            # Pick the top sequences (need at least 2 occurrences in MY games)
            top_seqs = sorted(counts.items(), key=lambda kv: kv[1]["games"], reverse=True)
            top_seqs = [s for s in top_seqs if s[1]["games"] >= 2][:3]
            if not top_seqs:
                continue

            for ucis, meta in top_seqs:
                # 2. Find opponent games matching this exact UCI prefix
                # The opponent plays the OPPOSITE color to me here.
                opp_color_filter = (
                    Game.black_player_id == opponent.id if my_color == "white"
                    else Game.white_player_id == opponent.id
                )

                # Get all opponent games that match the prefix
                next_ply = len(ucis) + 1

                # Build a subquery that filters games matching every ply
                opp_games_q = select(Game.id).where(opp_color_filter)
                opp_games_ids = [r[0] for r in (await session.execute(opp_games_q)).all()]
                if not opp_games_ids:
                    continue

                matching_game_ids: list[int] = []
                # Crude but correct: pull all early moves of opponent games and filter in Python.
                # (Cleaner SQL is tricky to write portably; ply<=6 keeps the set small.)
                opp_move_rows = (await session.execute(
                    select(Move.game_id, Move.ply, Move.uci)
                    .where(Move.game_id.in_(opp_games_ids))
                    .where(Move.ply <= len(ucis))
                )).all()
                opp_by_game: dict[int, dict[int, str]] = {}
                for gid, ply, uci in opp_move_rows:
                    opp_by_game.setdefault(gid, {})[ply] = uci

                for gid, plies_map in opp_by_game.items():
                    if all(plies_map.get(i + 1) == u for i, u in enumerate(ucis)):
                        matching_game_ids.append(gid)

                if not matching_game_ids:
                    continue

                # 3. Aggregate opponent's NEXT move + outcome
                resp_rows = (await session.execute(
                    select(
                        Move.uci, Move.san,
                        func.count(Game.id).label("n"),
                        func.sum(case(
                            (and_(Game.white_player_id == opponent.id, Game.result == GameResult.WHITE_WIN), 1),
                            (and_(Game.black_player_id == opponent.id, Game.result == GameResult.BLACK_WIN), 1),
                            else_=0,
                        )).label("wins"),
                        func.sum(case((Game.result == GameResult.DRAW, 1), else_=0)).label("draws"),
                    )
                    .join(Game, Game.id == Move.game_id)
                    .where(Move.game_id.in_(matching_game_ids))
                    .where(Move.ply == next_ply)
                    .group_by(Move.uci, Move.san)
                    .order_by(func.count(Game.id).desc())
                    .limit(5)
                )).all()

                if not resp_rows:
                    continue

                responses = [
                    {
                        "uci": r.uci,
                        "san": r.san,
                        "games": int(r.n),
                        "winrate": round(((r.wins or 0) + 0.5 * (r.draws or 0)) / max(int(r.n), 1), 3),
                    }
                    for r in resp_rows
                ]

                out.append(RepertoireBranch(
                    my_color=my_color,
                    line_san=list(meta["sans"]),
                    last_ply=len(ucis),
                    opponent_responses=responses,
                ))
                if len(out) >= top_branches:
                    return out
            break  # done at this depth; don't try smaller depths

    return out


# ---------------------------------------------------------------------------
# Vs openings I'm currently learning
# ---------------------------------------------------------------------------

@dataclass
class LearningProbeStep:
    ply: int
    expected_san: str
    expected_uci: str
    actual_responses: list[dict]  # [{san, uci, games, winrate, is_theory}]
    games_reaching: int           # how many opp games reached this position


@dataclass
class LearningOpeningProbe:
    opening_key: str
    name: str
    base_name: str
    branch_label: str             # "Mainline" or the branch label
    user_color: str               # I play this color
    eco: str
    summary: str
    full_line_san: list[str]
    # Step-by-step where the opponent had to respond. Includes only opponent
    # plies (the ones we're scouting). Truncated as soon as no opponent game
    # reaches the position.
    steps: list[LearningProbeStep]
    games_in_opening: int         # opp games that reached at least ply 2 of this line


async def _opp_games_with_color(
    session: AsyncSession, opponent_id: int, opp_color: str,
) -> list[int]:
    color_filter = (
        Game.black_player_id == opponent_id if opp_color == "black"
        else Game.white_player_id == opponent_id
    )
    return [r[0] for r in (await session.execute(
        select(Game.id).where(color_filter)
    )).all()]


async def _aggregate_response_at_ply(
    session: AsyncSession, opponent_id: int, candidate_game_ids: list[int], ply: int,
) -> list[dict]:
    """Return opp's actual move distribution at `ply` for the given games."""
    if not candidate_game_ids:
        return []
    rows = (await session.execute(
        select(
            Move.uci, Move.san,
            func.count(Game.id).label("n"),
            func.sum(case(
                (and_(Game.white_player_id == opponent_id, Game.result == GameResult.WHITE_WIN), 1),
                (and_(Game.black_player_id == opponent_id, Game.result == GameResult.BLACK_WIN), 1),
                else_=0,
            )).label("wins"),
            func.sum(case((Game.result == GameResult.DRAW, 1), else_=0)).label("draws"),
        )
        .join(Game, Game.id == Move.game_id)
        .where(Move.game_id.in_(candidate_game_ids))
        .where(Move.ply == ply)
        .group_by(Move.uci, Move.san)
        .order_by(func.count(Game.id).desc())
        .limit(5)
    )).all()
    return [
        {
            "uci": r.uci,
            "san": r.san,
            "games": int(r.n),
            "winrate": round(((r.wins or 0) + 0.5 * (r.draws or 0)) / max(int(r.n), 1), 3),
        }
        for r in rows
    ]


async def compute_vs_learning_openings(
    session: AsyncSession, me: Player, opponent: Player,
) -> list[LearningOpeningProbe]:
    """For each opening the user is actively learning, probe how the opponent
    actually responds against it in their played games.

    For every line (mainline + each registered branch) we walk move by move
    and, at every opponent ply, report the opponent's actual move distribution
    among their games that reached that position.
    """
    active = list((await session.execute(
        select(OpeningProgress)
        .where(OpeningProgress.player_id == me.id)
        .where(OpeningProgress.status == OpeningProgressStatus.ACTIVE)
    )).scalars())
    if not active:
        return []

    probes: list[LearningOpeningProbe] = []

    for prog in active:
        op = ot.get_opening(prog.opening_key)
        if op is None:
            continue
        opp_color = "black" if op.user_color == "white" else "white"
        # Preload candidate opp games (those where opp plays the opposite color)
        candidate_games = await _opp_games_with_color(session, opponent.id, opp_color)
        if not candidate_games:
            # Still emit the probe with 0 games so the user knows we tried
            for branch_label, moves in _enumerate_lines(op):
                probes.append(LearningOpeningProbe(
                    opening_key=op.key,
                    name=op.name,
                    base_name=op.base_name,
                    branch_label=branch_label,
                    user_color=op.user_color,
                    eco=op.eco,
                    summary=op.summary,
                    full_line_san=[m.san for m in moves],
                    steps=[],
                    games_in_opening=0,
                ))
            continue

        # Pull early moves of all candidate games once.
        # We need ply <= len(longest_line) for the deepest line we'll walk.
        max_line_len = max(
            (len(moves) for _, moves in _enumerate_lines(op)),
            default=0,
        )
        opp_move_rows = (await session.execute(
            select(Move.game_id, Move.ply, Move.uci)
            .where(Move.game_id.in_(candidate_games))
            .where(Move.ply <= max_line_len)
        )).all()
        opp_by_game: dict[int, dict[int, str]] = {}
        for gid, ply, uci in opp_move_rows:
            opp_by_game.setdefault(gid, {})[ply] = uci

        for branch_label, moves in _enumerate_lines(op):
            steps: list[LearningProbeStep] = []
            # Walk through the line. For each opponent ply, query distribution
            # restricted to games that match the prefix so far.
            prefix_ucis: list[str] = []
            games_at_root = 0
            for i, m in enumerate(moves):
                ply = i + 1
                if m.color == op.user_color:
                    # My (book) move — just record in prefix and continue.
                    prefix_ucis.append(m.uci)
                    continue
                # Opponent's expected move at this ply.
                matching = [
                    gid for gid, mv in opp_by_game.items()
                    if all(mv.get(j + 1) == u for j, u in enumerate(prefix_ucis))
                ]
                if i == 1:
                    games_at_root = len(matching)
                if not matching:
                    break
                dist = await _aggregate_response_at_ply(
                    session, opponent.id, matching, ply,
                )
                # Mark whether each response matches theory
                expected_uci = m.uci
                for d in dist:
                    d["is_theory"] = d["uci"] == expected_uci
                steps.append(LearningProbeStep(
                    ply=ply,
                    expected_san=m.san,
                    expected_uci=expected_uci,
                    actual_responses=dist,
                    games_reaching=len(matching),
                ))
                prefix_ucis.append(m.uci)

            probes.append(LearningOpeningProbe(
                opening_key=op.key,
                name=op.name,
                base_name=op.base_name,
                branch_label=branch_label,
                user_color=op.user_color,
                eco=op.eco,
                summary=op.summary,
                full_line_san=[m.san for m in moves],
                steps=steps,
                games_in_opening=games_at_root,
            ))

    # Sort: probes with actual data first; within that, by games_in_opening desc.
    probes.sort(key=lambda p: (-p.games_in_opening, p.opening_key, p.branch_label))
    return probes


async def compute_opponent_engine_script(
    session: AsyncSession,
    opponent: Player,
    opp_color: str,
    max_plies: int = 12,
    min_frequency: int = 2,
) -> list[dict]:
    """Build a deterministic opening script for the opponent.

    At each opponent ply, picks their most-played move conditioned on the
    sequence of moves played so far. Stops when no position has been reached
    by at least `min_frequency` of their games, or after `max_plies`.

    Returns a list of {ply, uci, san, games, winrate} dicts that should be
    fed as forced engine moves to a play session.
    """
    color_filter = (
        Game.white_player_id == opponent.id if opp_color == "white"
        else Game.black_player_id == opponent.id
    )
    candidate_games = [r[0] for r in (await session.execute(
        select(Game.id).where(color_filter)
    )).all()]
    if not candidate_games:
        return []

    # Pull all early moves once
    rows = (await session.execute(
        select(Move.game_id, Move.ply, Move.uci, Move.san)
        .where(Move.game_id.in_(candidate_games))
        .where(Move.ply <= max_plies)
    )).all()
    by_game: dict[int, dict[int, tuple[str, str]]] = {}
    for gid, ply, uci, san in rows:
        by_game.setdefault(gid, {})[ply] = (uci, san)

    script: list[dict] = []
    matching_games = set(candidate_games)
    prefix_ucis: list[str] = []

    for target_ply in range(1, max_plies + 1):
        is_opp_ply = (
            (target_ply % 2 == 1 and opp_color == "white")
            or (target_ply % 2 == 0 and opp_color == "black")
        )
        if not is_opp_ply:
            # Skip: this ply belongs to the user, no script entry needed.
            # But we still need to NOT filter here because the user's actual
            # move will be applied at runtime — leaving matching_games as-is
            # would over-narrow. Instead, we keep `matching_games` constant
            # at the set of games that matched our prescribed opponent moves
            # so far; the runtime will simply look up the next opponent ply.
            # We append a placeholder so indexing stays simple downstream.
            script.append({"ply": target_ply, "uci": None, "san": None, "games": 0, "winrate": 0.0})
            prefix_ucis.append("")  # placeholder for user move at this ply
            continue

        # Restrict to games that match the prefix up to this point.
        # For user plies, we don't constrain (user-played moves vary); but for
        # opponent plies prior, we already filtered. So we keep matching_games
        # as the set that follows our scripted opponent moves so far.
        # Find the most-frequent opp move at target_ply within matching_games.
        counts: dict[tuple[str, str], dict] = {}
        for gid in matching_games:
            mv = by_game.get(gid, {}).get(target_ply)
            if mv is None:
                continue
            uci, san = mv
            k = (uci, san)
            d = counts.setdefault(k, {"uci": uci, "san": san, "games": 0, "wins": 0, "draws": 0})
            d["games"] += 1
            g = next((x for x in candidate_games if x == gid), None)

        if not counts:
            break

        # Pick top
        top = max(counts.values(), key=lambda v: v["games"])
        if top["games"] < min_frequency and len(script) > 0:
            # Not enough data to keep scripting; stop.
            break

        # Compute winrate for the chosen move (across matching games where opp
        # played this move at this ply).
        # Reload outcome via a query (cheap).
        chosen_uci = top["uci"]
        outcome_rows = (await session.execute(
            select(Game.result, Game.white_player_id, Game.black_player_id)
            .join(Move, Move.game_id == Game.id)
            .where(Move.game_id.in_(list(matching_games)))
            .where(Move.ply == target_ply)
            .where(Move.uci == chosen_uci)
        )).all()
        w = d_ = 0
        for res, wp, bp in outcome_rows:
            outcome = _outcome_for(opponent.id, wp, bp, res)
            if outcome == "W":
                w += 1
            elif outcome == "D":
                d_ += 1
        total = len(outcome_rows)
        winrate = round((w + 0.5 * d_) / max(total, 1), 3)

        script.append({
            "ply": target_ply,
            "uci": chosen_uci,
            "san": top["san"],
            "games": top["games"],
            "winrate": winrate,
        })
        # Narrow matching games to those that played this exact move at target_ply
        matching_games = {
            gid for gid in matching_games
            if by_game.get(gid, {}).get(target_ply, (None, None))[0] == chosen_uci
        }
        prefix_ucis.append(chosen_uci)

    return script


def _enumerate_lines(op):
    """Yield (branch_label, list[TrainerMove]) for mainline + every branch."""
    yield ("Mainline", list(op.moves))
    for b in op.branches:
        yield (b.label, ot.materialize_branch(op, b))


# ---------------------------------------------------------------------------
# Deterministic battle plan
# ---------------------------------------------------------------------------

def generate_deterministic_plan(
    profile: OpponentProfile,
    phase_quality: list[PhaseQualityStats],
    opening_report,  # OpponentOpeningReport
    weaknesses: list[dict],
) -> str:
    """Build a rule-based battle plan from the structured data. No LLM needed."""
    lines: list[str] = []

    # --- 1. Style ---
    if profile.last_10:
        recent_form = "".join(profile.last_10)
        lines.append(f"[Forme] {recent_form} ({profile.last_10.count('W')}W/{profile.last_10.count('L')}L/{profile.last_10.count('D')}D sur les 10 dernières)")

    if profile.by_color:
        bc = {c.color: c for c in profile.by_color}
        white_wr = bc.get("white").winrate if "white" in bc else None
        black_wr = bc.get("black").winrate if "black" in bc else None
        if white_wr is not None and black_wr is not None:
            if white_wr - black_wr > 0.10:
                lines.append(f"[Couleur] Bien plus fort en BLANC ({white_wr:.0%}) qu'en NOIR ({black_wr:.0%}) — joue le donc en noir si possible.")
            elif black_wr - white_wr > 0.10:
                lines.append(f"[Couleur] Bien plus fort en NOIR ({black_wr:.0%}) qu'en BLANC ({white_wr:.0%}) — joue le en blanc si possible.")

    # --- 2. Phase to target ---
    if phase_quality:
        worst = max(phase_quality, key=lambda p: p.blunder_rate)
        if worst.moves >= 20 and worst.blunder_rate >= 0.04:
            phase_fr = {"opening": "l'ouverture", "middlegame": "le milieu de partie", "endgame": "la finale"}[worst.phase]
            lines.append(
                f"[Phase à viser] {phase_fr.upper()} — il blunder {worst.blunder_rate:.0%} de ses coups là ({worst.blunders} blunders / {worst.moves} coups)."
            )
            if worst.phase == "endgame":
                lines.append("-> Provoque les échanges tôt, simplifie vers une finale.")
            elif worst.phase == "middlegame":
                lines.append("-> Évite les simplifications. Garde la complexité.")
            elif worst.phase == "opening":
                lines.append("-> Joue une ouverture théorique solide, profite des écarts précoces.")

    # --- 3. Opening recommendation ---
    o = opening_report
    if o.first_move_as_white:
        top_white_move = o.first_move_as_white[0]
        if top_white_move.san == "e4":
            lines.append("[Blancs] Quand il est BLANC : joue le 1.e4. Choisis une défense fermée si tu veux le sortir de la théorie (Caro-Kann, French) — il sort en moyenne du livre au ply " + (f"{o.avg_out_of_book_ply:.0f}" if o.avg_out_of_book_ply else "?"))
        elif top_white_move.san == "d4":
            lines.append("[Blancs] Quand il est BLANC : il joue 1.d4. Prépare-toi à une KID ou Slav, structures à long terme.")
        else:
            lines.append(f"[Blancs] Quand il est BLANC : il joue {top_white_move.san} dans {top_white_move.games} parties (winrate {top_white_move.winrate:.0%}).")

    if o.response_to_e4:
        top_resp = o.response_to_e4[0]
        lines.append(f"[Noirs vs 1.e4] Il répond {top_resp.san} ({top_resp.games}x, wr {top_resp.winrate:.0%}).")
    if o.response_to_d4:
        top_resp = o.response_to_d4[0]
        lines.append(f"[Noirs vs 1.d4] Il répond {top_resp.san} ({top_resp.games}x, wr {top_resp.winrate:.0%}).")

    # --- 4. Top weakness ---
    if weaknesses:
        top_w = weaknesses[0]
        cat_fr = top_w["category"].replace("_", " ")
        phase = f" en {top_w['phase']}" if top_w.get("phase") else ""
        lines.append(f"[Faiblesse n°1] {cat_fr}{phase} (sévérité {top_w['severity']:.2f}, {top_w['occurrences']} occurrences) — c'est ton angle d'attaque.")

    if not lines:
        return "Pas assez de données pour générer un plan structuré (l'adversaire a moins de 10 parties analysées)."
    return "\n".join(lines)
