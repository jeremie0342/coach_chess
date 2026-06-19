"""LLM-backed move explainer.

For a given move in a game, we assemble a structured prompt out of objective
data (FEN, the move played, Stockfish's best move, eval delta, opening name)
and ask the LLM to produce a short, plan-focused explanation.

Cache key: (fen, played_uci, best_uci) so identical positions across users'
games reuse the same explanation.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import chess
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import PROJECT_ROOT
from app.models import Game, Move, MoveAnalysis, Opening
from app.services.llm.ollama import ChatMessage, OllamaClient

CACHE_DIR = PROJECT_ROOT / "data" / "coach_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class MoveContext:
    fen_before: str
    fen_after: str
    played_san: str
    played_uci: str
    best_san: str | None
    best_uci: str | None
    eval_cp_before: int | None
    eval_mate_before: int | None
    eval_cp_after: int | None
    eval_mate_after: int | None
    cp_loss: int | None
    quality: str | None
    opening_name: str | None
    eco: str | None
    pv_san: str | None
    side_to_move: str


SYSTEM_PROMPT = """Tu es un coach d'échecs francophone, pédagogue, qui s'adresse à un joueur amateur autour de 450 ELO sur Chess.com.

Pour chaque coup que je te soumets, tu dois :
- Expliquer en 2-4 phrases courtes le plan correct dans la position
- Si le joueur a fait une erreur, dire CLAIREMENT pourquoi son coup est moins bon
- Décrire l'idée stratégique derrière le meilleur coup (centre, développement, attaque du roi, structure de pions, etc.) — pas seulement les variantes
- Mentionner brièvement le contexte d'ouverture si pertinent

Reste concret et orienté plan. N'utilise pas de jargon trop fort. Pas de listes à puces — du texte fluide."""


def _format_eval(cp: int | None, mate: int | None) -> str:
    if mate is not None:
        return f"#{mate}"
    if cp is None:
        return "?"
    if abs(cp) >= 30000:
        return "+∞" if cp > 0 else "-∞"
    return f"{cp / 100:+.2f}"


def _cache_path(fen: str, played_uci: str, best_uci: str | None) -> Path:
    import hashlib
    key = f"{fen}|{played_uci}|{best_uci or ''}"
    h = hashlib.sha1(key.encode()).hexdigest()[:24]
    return CACHE_DIR / f"{h}.json"


def render_user_prompt(ctx: MoveContext) -> str:
    sb = chess.Board(ctx.fen_before).unicode(empty_square="·", invert_color=True)
    lines = [
        "Position (à toi de jouer):",
        sb,
        "",
        f"FEN: {ctx.fen_before}",
        f"Trait aux {ctx.side_to_move}",
    ]
    if ctx.opening_name:
        lines.append(f"Ouverture identifiée: {ctx.opening_name} ({ctx.eco or '-'})")
    lines += [
        "",
        f"Coup joué         : {ctx.played_san} ({ctx.played_uci})",
        f"Meilleur (Stockfish) : {ctx.best_san or '-'} ({ctx.best_uci or '-'})",
        f"Éval avant coup   : {_format_eval(ctx.eval_cp_before, ctx.eval_mate_before)}",
        f"Éval après coup   : {_format_eval(ctx.eval_cp_after, ctx.eval_mate_after)}",
        f"Perte (cp)        : {ctx.cp_loss if ctx.cp_loss is not None else '-'}",
        f"Classification    : {ctx.quality or '-'}",
    ]
    if ctx.pv_san:
        lines += ["", f"Variante principale recommandée: {ctx.pv_san}"]
    lines += [
        "",
        "Explique-moi brièvement (en français) ce qui se passe ici et quel est le plan correct.",
    ]
    return "\n".join(lines)


async def build_context_for_move(
    session: AsyncSession, game: Game, ply: int
) -> MoveContext | None:
    move = (await session.execute(
        select(Move).where(Move.game_id == game.id, Move.ply == ply)
    )).scalar_one_or_none()
    if not move:
        return None
    analysis = (await session.execute(
        select(MoveAnalysis).where(MoveAnalysis.move_id == move.id)
    )).scalar_one_or_none()

    opening_name = None
    eco = None
    if game.deepest_opening_id:
        op = (await session.execute(
            select(Opening).where(Opening.id == game.deepest_opening_id)
        )).scalar_one_or_none()
        if op:
            opening_name = op.name
            eco = op.eco

    pv_san: str | None = None
    if analysis and analysis.pv:
        try:
            board = chess.Board(move.fen_before)
            moves_uci = analysis.pv
            moves = [chess.Move.from_uci(u) for u in moves_uci[:8]]
            pv_san = board.variation_san(moves)
        except Exception:
            pv_san = None

    return MoveContext(
        fen_before=move.fen_before,
        fen_after=move.fen_after,
        played_san=move.san,
        played_uci=move.uci,
        best_san=analysis.best_move_san if analysis else None,
        best_uci=analysis.best_move_uci if analysis else None,
        eval_cp_before=analysis.eval_cp_before if analysis else None,
        eval_mate_before=analysis.eval_mate_before if analysis else None,
        eval_cp_after=analysis.eval_cp if analysis else None,
        eval_mate_after=analysis.eval_mate if analysis else None,
        cp_loss=analysis.cp_loss if analysis else None,
        quality=str(analysis.quality) if analysis and analysis.quality else None,
        opening_name=opening_name,
        eco=eco,
        pv_san=pv_san,
        side_to_move="Blancs" if move.is_white else "Noirs",
    )


async def explain_move(
    session: AsyncSession,
    game: Game,
    ply: int,
    *,
    use_cache: bool = True,
    temperature: float = 0.3,
) -> dict:
    ctx = await build_context_for_move(session, game, ply)
    if not ctx:
        return {"error": f"No move at ply {ply} for game {game.id}"}

    cache_file = _cache_path(ctx.fen_before, ctx.played_uci, ctx.best_uci)
    if use_cache and cache_file.exists():
        with cache_file.open("r", encoding="utf-8") as f:
            cached = json.load(f)
        cached["cache_hit"] = True
        return cached

    prompt = render_user_prompt(ctx)
    async with OllamaClient() as client:
        explanation = await client.chat(
            [
                ChatMessage(role="system", content=SYSTEM_PROMPT),
                ChatMessage(role="user", content=prompt),
            ],
            temperature=temperature,
        )

    result = {
        "game_id": game.id,
        "ply": ply,
        "side_to_move": ctx.side_to_move,
        "played": ctx.played_san,
        "best": ctx.best_san,
        "quality": ctx.quality,
        "cp_loss": ctx.cp_loss,
        "opening": ctx.opening_name,
        "explanation": explanation,
        "cache_hit": False,
    }
    with cache_file.open("w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    return result
