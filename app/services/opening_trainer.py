"""Curated openings library for the opening trainer.

Refactor (2026-06):
  - Each opening is now a flat sequence of moves with explicit color.
  - Openings where the user plays Black are first-class (the engine plays
    White's opening move automatically before the user's first move).
  - Multiple variants per base opening (e.g. Sicilian Najdorf has English
    Attack + Bg5 line) are exposed as distinct entries so the UI can group
    them under the same base name.

Backwards compatibility:
  - We still expose a synthesized `line: list[TrainerNode]` (pairs of
    user_move + opponent_reply) so the existing API contract works without
    changes to the frontend. For Black openings the auto-played opening
    move shifts the pairing.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Literal


# --- Public dataclasses --------------------------------------------------

@dataclass
class TrainerMove:
    uci: str
    san: str
    color: Literal["white", "black"]
    explanation: str | None = None  # typically set on user moves


@dataclass
class TrainerNode:
    """Legacy API contract: a (user_move, opponent_reply) pair."""
    user_move: str | None
    user_san: str | None
    user_explanation: str | None
    opponent_reply: str | None
    opponent_san: str | None


@dataclass
class TrainerBranch:
    """A divergent continuation that swaps in at a specific opponent move.

    The user plays the same move as the mainline up to (and including) move
    index `fork_after_move`. At that point the opponent plays `opp_move`
    instead of the mainline opponent move, and the line continues with
    `continuation` (alternating user and opponent moves).

    `fork_after_move` is 0-indexed against the flat `moves` array. It must
    point to a USER move (the move the user just played) — the branch then
    diverges at the next slot which is an opponent move.
    """
    label: str
    fork_after_move: int
    opp_move: TrainerMove                      # alternative opponent reply
    continuation: list[TrainerMove]            # moves after opp_move


@dataclass
class TrainerOpening:
    key: str
    name: str
    base_name: str
    eco: str
    user_color: Literal["white", "black"]
    starting_fen: str
    summary: str
    plan: list[str]
    moves: list[TrainerMove]
    # Optional alternative continuations. The session may randomly pick one of
    # these instead of the mainline, so the user learns to adapt.
    branches: list[TrainerBranch] = field(default_factory=list)
    # Synthesised after construction for the legacy API.
    line: list[TrainerNode] = field(default_factory=list)
    # Opening moves the engine should auto-play before the user is on move
    # (typically white's first move when user_color == "black"). The session
    # applies these to the board at start, advancing the position.
    prelude: list[TrainerMove] = field(default_factory=list)


def materialize_branch(op: TrainerOpening, branch: TrainerBranch) -> list[TrainerMove]:
    """Return the flat move sequence when the given branch is taken."""
    head = op.moves[: branch.fork_after_move + 1]
    return list(head) + [branch.opp_move] + list(branch.continuation)


_INIT_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


# --- Helpers -------------------------------------------------------------

def _m(uci: str, san: str, color: Literal["white", "black"], expl: str | None = None) -> TrainerMove:
    return TrainerMove(uci=uci, san=san, color=color, explanation=expl)


def _finalize(op: TrainerOpening) -> TrainerOpening:
    """Compute `prelude` + `line` from the flat `moves` sequence."""
    # Find first index where it's the user's turn.
    first_user_idx = next(
        (i for i, m in enumerate(op.moves) if m.color == op.user_color),
        len(op.moves),
    )
    op.prelude = list(op.moves[:first_user_idx])

    # Pair (user_move, opponent_reply) starting at first_user_idx
    pairs: list[TrainerNode] = []
    i = first_user_idx
    while i < len(op.moves):
        user_mv = op.moves[i]
        opp_mv: TrainerMove | None = None
        if i + 1 < len(op.moves) and op.moves[i + 1].color != op.user_color:
            opp_mv = op.moves[i + 1]
        pairs.append(TrainerNode(
            user_move=user_mv.uci,
            user_san=user_mv.san,
            user_explanation=user_mv.explanation,
            opponent_reply=opp_mv.uci if opp_mv else None,
            opponent_san=opp_mv.san if opp_mv else None,
        ))
        i += 2 if opp_mv else 1
    op.line = pairs
    return op


# --- Library entries -----------------------------------------------------

def _opening(
    key: str, name: str, base: str, eco: str, color: Literal["white", "black"],
    summary: str, plan: list[str], moves: list[TrainerMove],
    branches: list[TrainerBranch] | None = None,
) -> TrainerOpening:
    return _finalize(TrainerOpening(
        key=key, name=name, base_name=base, eco=eco, user_color=color,
        starting_fen=_INIT_FEN, summary=summary, plan=plan, moves=moves,
        branches=branches or [],
    ))


LIBRARY: dict[str, TrainerOpening] = {}


def _add(op: TrainerOpening) -> None:
    LIBRARY[op.key] = op


# ===== WHITE openings ====================================================

# --- London System (existing) ---
_add(_opening(
    key="london_system",
    name="London System - Ligne principale",
    base="London System",
    eco="D02",
    color="white",
    summary=(
        "Un systeme solide pour les blancs base sur d4 + Bf4. Tu sors le fou "
        "avant de bloquer le pion e, tu construis une pyramide Bd3 / e3 / "
        "c3 / Nbd2 et tu cherches le break e3-e4 ou un kingside attack."
    ),
    plan=[
        "Le fou de cases noires SORT TOUJOURS sur f4 avant e3.",
        "Pyramide e3, c3, Bd3, Nbd2 derriere le fou.",
        "Roque court systematique, puis Ne5 + f4 si possible.",
    ],
    moves=[
        _m("d2d4", "d4", "white", "Centre solide, le pion ne sera pas attaque."),
        _m("d7d5", "d5", "black"),
        _m("c1f4", "Bf4", "white", "Le fou sort AVANT e3 — geste signature du London."),
        _m("g8f6", "Nf6", "black"),
        _m("e2e3", "e3", "white", "Maintenant on ferme la diagonale du fou."),
        _m("e7e6", "e6", "black"),
        _m("g1f3", "Nf3", "white", "Developpement, soutient e5 et controle e5."),
        _m("f8d6", "Bd6", "black"),
        _m("f1d3", "Bd3", "white", "Pyramide en place : d4-e3-Bd3."),
        _m("e8g8", "O-O", "black"),
        _m("e1g1", "O-O", "white", "Roque court : roi en securite, on prepare l'aile-roi."),
    ],
))

# --- Italian Game ---
_add(_opening(
    key="italian_game",
    name="Italian Game (Giuoco Piano)",
    base="Italian Game",
    eco="C50",
    color="white",
    summary=(
        "Ouverture classique pour developper rapidement : cavalier f3, fou "
        "c4 contre le pion f7, on cherche un milieu de partie ouvert."
    ),
    plan=[
        "Centre e4 + cavalier f3 immediat.",
        "Fou c4 vise le point faible f7.",
        "Roque court rapide, puis c3 + d4 pour ouvrir le centre.",
    ],
    moves=[
        _m("e2e4", "e4", "white", "Centre classique."),
        _m("e7e5", "e5", "black"),
        _m("g1f3", "Nf3", "white", "Attaque le pion e5."),
        _m("b8c6", "Nc6", "black"),
        _m("f1c4", "Bc4", "white", "Fou italien : pression sur f7."),
        _m("f8c5", "Bc5", "black"),
        _m("c2c3", "c3", "white", "Prepare d4 pour ouvrir le centre."),
        _m("g8f6", "Nf6", "black"),
        _m("d2d4", "d4", "white", "Casse le centre, lutte ouverte."),
    ],
))

# --- Queen's Gambit ---
_add(_opening(
    key="queens_gambit",
    name="Queen's Gambit - Ligne principale",
    base="Queen's Gambit",
    eco="D06",
    color="white",
    summary=(
        "Sacrifice apparent du pion c4 pour ouvrir la diagonale et obtenir "
        "un fort centre. Si les noirs prennent (QGA) on regagne le pion ; "
        "s'ils ne prennent pas (QGD), on a une majorite centrale."
    ),
    plan=[
        "d4 puis c4 immediat — le pion c4 est rarement perdu.",
        "Si dxc4 : on joue e4/e3 et reprend en force.",
        "Si refuse (e6/c6) : centre fort, on developpe normalement.",
    ],
    moves=[
        _m("d2d4", "d4", "white"),
        _m("d7d5", "d5", "black"),
        _m("c2c4", "c4", "white", "Le gambit dame : on offre c4 pour ouvrir."),
        _m("e7e6", "e6", "black"),
        _m("b1c3", "Nc3", "white", "Pression sur d5."),
        _m("g8f6", "Nf6", "black"),
        _m("c1g5", "Bg5", "white", "Fixe le cavalier et prepare e3."),
        _m("f8e7", "Be7", "black"),
        _m("e2e3", "e3", "white"),
        _m("e8g8", "O-O", "black"),
        _m("g1f3", "Nf3", "white", "Developpement complet de la cavalerie."),
    ],
))

# --- King's Gambit Accepted (white, recommended by the coach) ---
_add(_opening(
    key="kings_gambit_accepted",
    name="King's Gambit - Accepted (Kieseritzky)",
    base="King's Gambit",
    eco="C30",
    color="white",
    summary=(
        "Ouverture hyper-attaquante. On sacrifie le pion f4 pour ouvrir la "
        "colonne f et lancer un assaut sur le roi noir. La ligne Kieseritzky "
        "(Nf3-Ne5) maintient l'initiative."
    ),
    plan=[
        "Sacrifice de pion f4 puis h4 pour ouvrir les colonnes f et h.",
        "Cavalier en Ne5 (Kieseritzky) — central, vise f7, garde l'initiative.",
        "Bc4 pour la pression sur f7 et le développement rapide.",
        "GRAND ROQUE (O-O-O) — le côté roi est déjà ouvert : on roque "
        "long pour mettre le roi à l'abri et utiliser la colonne h ouverte "
        "comme rampe d'attaque contre le roi noir.",
        "Une fois roqué long, Rdg1 ou Rh1 + Qh5 = attaque écrasante.",
    ],
    moves=[
        _m("e2e4", "e4", "white"),
        _m("e7e5", "e5", "black"),
        _m("f2f4", "f4", "white", "Le Gambit du Roi : attire e5 hors de sa case."),
        _m("e5f4", "exf4", "black"),
        _m("g1f3", "Nf3", "white", "Empeche Dh4+. Developpement avant tout."),
        _m("g7g5", "g5", "black"),
        _m("h2h4", "h4", "white", "Casse la chaine de pions noirs sur l'aile-roi."),
        _m("g5g4", "g4", "black"),
        _m("f3e5", "Ne5", "white", "Kieseritzky : cavalier central, vise f7."),
        _m("g8f6", "Nf6", "black"),
        _m("f1c4", "Bc4", "white", "Pression sur f7, prepare le sac de matiere."),
        _m("d7d6", "d6", "black", "Le pion attaque Ne5, force le cavalier a bouger."),
        _m("e5g4", "Nxg4", "white", "Le cavalier capture g4 — recule + grappille un pion."),
        _m("f6e4", "Nxe4", "black", "Reprend le pion central, ouvre la colonne e."),
        _m("d2d3", "d3", "white",
           "Pousse le pion pour DEUX raisons : attaque Ne4, ET libere le fou c1 "
           "(la diagonale c1-h6 se debloque pour reprendre f4 au coup suivant)."),
        _m("e4f6", "Nf6", "black",
           "Le cavalier recule pour ne pas se faire prendre."),
        _m("c1f4", "Bxf4", "white",
           "Le fou developpe ET reprend le pion f4. La case c1 est libre."),
        _m("f8g7", "Bg7", "black",
           "Fianchetto noir — fou actif sur la grande diagonale."),
        _m("b1c3", "Nc3", "white",
           "Cavalier developpe. La case b1 est libre."),
        _m("e8g8", "O-O", "black", "Roi noir en securite."),
        _m("d1d2", "Qd2", "white",
           "Dame developpee — la case d1 est libre. Tout est pret pour le grand roque."),
        _m("b8c6", "Nc6", "black",
           "Developpement classique."),
        _m("e1c1", "O-O-O", "white",
           "GRAND ROQUE ! Le cote roi est ouvert (plus de f2, h2) — on met "
           "le roi a l'abri a l'aile dame et on transforme la colonne h ouverte "
           "en rampe d'attaque. Geste signature du King's Gambit."),
    ],
    branches=[
        # Branch 1: Greco Defense — 4...gxh4 instead of 4...g4
        TrainerBranch(
            label="Greco Defense (4...gxh4)",
            fork_after_move=6,   # after white's h4 (index 6 in moves[])
            opp_move=_m("g5h4", "gxh4", "black",
                        "Les noirs prennent en h4 plutot que d'avancer g4."),
            continuation=[
                _m("f3h4", "Nxh4", "white",
                   "On reprend avec le CAVALIER (pas la tour !) pour garder "
                   "le droit de roquer. Le cavalier en h4 sautera plus tard."),
                _m("g8f6", "Nf6", "black",
                   "Developpement classique, attaque le pion e4."),
                _m("b1c3", "Nc3", "white",
                   "Developpement et soutient e4 — toujours defendre avant d'attaquer."),
                _m("d7d6", "d6", "black",
                   "Structure solide, prepare ...e5 ou ...Bg7."),
                _m("d2d4", "d4", "white",
                   "Centre maximum + libere la diagonale c1-h6 pour le fou."),
                _m("f8g7", "Bg7", "black",
                   "Fianchetto. Le fou regarde la longue diagonale."),
                _m("c1e3", "Be3", "white",
                   "Developpement du fou — la case c1 est libre."),
                _m("e8g8", "O-O", "black",
                   "Roi noir en securite."),
                _m("d1d2", "Qd2", "white",
                   "Dame developpee — la case d1 est libre. Tout est pret pour O-O-O."),
                _m("b8c6", "Nc6", "black",
                   "Cavalier developpe."),
                _m("e1c1", "O-O-O", "white",
                   "GRAND ROQUE — meme plan strategique que la mainline : "
                   "roi a l'aile dame, tour sur la colonne h ouverte pour l'attaque."),
            ],
        ),
        # Branch 2: Becker Defense — 3...h6 (rare but possible)
        TrainerBranch(
            label="Becker Defense (3...h6)",
            fork_after_move=4,   # after white's Nf3 (index 4)
            opp_move=_m("h7h6", "h6", "black",
                        "Defense prophylactique — empeche Ng5."),
            continuation=[
                _m("d2d4", "d4", "white", "Centre maximum, prepare Bxf4."),
                _m("g7g5", "g5", "black", "Defense classique du pion f4."),
                _m("h2h4", "h4", "white", "Casse la chaine de pions, comme mainline."),
                _m("f8g7", "Bg7", "black",
                   "Fianchetto noir — defend la diagonale a1-h8."),
                _m("h4g5", "hxg5", "white",
                   "Ouvre la colonne h pour la tour h1 — exactement le plan King's Gambit."),
                _m("h6g5", "hxg5", "black"),
                _m("h1h8", "Rxh8", "white",
                   "Echange de tours sur la colonne h ouverte — simplifie + maintient l'initiative."),
            ],
        ),
    ],
))

# --- King's Gambit Declined ---
_add(_opening(
    key="kings_gambit_declined",
    name="King's Gambit - Declined (Classical)",
    base="King's Gambit",
    eco="C30",
    color="white",
    summary=(
        "Quand les noirs refusent le gambit avec ...Bc5, on developpe "
        "naturellement et on garde l'initiative grace au centre."
    ),
    plan=[
        "Si ...Bc5 (refuse le gambit) : developper normalement.",
        "Nf3, Nc3, d3 — solide, sans sacrifier.",
        "Plus tard fxe5 ou f5, selon les besoins.",
    ],
    moves=[
        _m("e2e4", "e4", "white"),
        _m("e7e5", "e5", "black"),
        _m("f2f4", "f4", "white"),
        _m("f8c5", "Bc5", "black"),
        _m("g1f3", "Nf3", "white", "Refuse-Gambit : pas de tactique, on developpe."),
        _m("d7d6", "d6", "black"),
        _m("b1c3", "Nc3", "white"),
        _m("g8f6", "Nf6", "black"),
        _m("f1c4", "Bc4", "white", "Encore le fou sur la diagonale a2-f7."),
        _m("b8c6", "Nc6", "black"),
        _m("d2d3", "d3", "white", "Centre stable, on prepare 0-0 et le break d4."),
    ],
))


# ===== BLACK openings ====================================================

# --- French Defense (existing, refactored) ---
_add(_opening(
    key="french_defense",
    name="French Defense - Classical",
    base="French Defense",
    eco="C00",
    color="black",
    summary=(
        "Defense francaise : e6 puis d5 pour contester le centre sans "
        "s'ouvrir trop vite. Structure de pions caracteristique, "
        "contre-attaque sur l'aile dame."
    ),
    plan=[
        "e6 puis d5 systematique.",
        "Le fou c8 est notre piece probleme : on cherche a le degager.",
        "Contre-attaque sur l'aile dame avec c5.",
        "Patience : la French se joue lentement.",
    ],
    moves=[
        _m("e2e4", "e4", "white"),
        _m("e7e6", "e6", "black", "Premier coup signature de la French."),
        _m("d2d4", "d4", "white"),
        _m("d7d5", "d5", "black", "Contestation centrale immediate."),
        _m("b1c3", "Nc3", "white"),
        _m("g8f6", "Nf6", "black", "Developpement, attaque le pion e4."),
        _m("c1g5", "Bg5", "white"),
        _m("f8e7", "Be7", "black", "Defense du cavalier et prepare le roque."),
        _m("e4e5", "e5", "white"),
        _m("f6d7", "Nfd7", "black", "Recule le cavalier pour rester actif."),
        _m("g5e7", "Bxe7", "white"),
        _m("d8e7", "Qxe7", "black", "Reprise dame, position solide."),
    ],
))

# --- King's Indian Defense (Mar del Plata) ---
_add(_opening(
    key="kid_mar_del_plata",
    name="King's Indian Defense - Mar del Plata (Classical)",
    base="King's Indian Defense",
    eco="E97",
    color="black",
    summary=(
        "Defense hyper-attaquante contre 1.d4. On laisse les blancs prendre "
        "le centre puis on contre-attaque sur l'aile-roi avec f5-g5-h5 "
        "pendant que les blancs jouent sur l'aile-dame."
    ),
    plan=[
        "Fianchetto rapide : Nf6, g6, Bg7, 0-0.",
        "...d6 puis ...e5 — on accepte un centre ferme.",
        "Apres ...Nc6 / Ne7, on lance f5 ! pour l'attaque sur l'aile roi.",
        "Tu joues sur l'aile roi, l'adversaire sur l'aile dame : course de vitesse.",
    ],
    moves=[
        _m("d2d4", "d4", "white"),
        _m("g8f6", "Nf6", "black", "Cavalier indien, controle e4 et d5."),
        _m("c2c4", "c4", "white"),
        _m("g7g6", "g6", "black", "Prepare le fianchetto, marque signature de la KID."),
        _m("b1c3", "Nc3", "white"),
        _m("f8g7", "Bg7", "black", "Fianchetto. Le fou sera le pivot strategique."),
        _m("e2e4", "e4", "white"),
        _m("d7d6", "d6", "black", "On retient e5 pour bientot."),
        _m("g1f3", "Nf3", "white"),
        _m("e8g8", "O-O", "black", "Roi en securite avant les hostilites."),
        _m("f1e2", "Be2", "white"),
        _m("e7e5", "e5", "black", "Defi central : on fixe le centre."),
        _m("e1g1", "O-O", "white"),
        _m("b8c6", "Nc6", "black", "Vise d4, prepare la transformation centrale."),
        _m("d4d5", "d5", "white"),
        _m("c6e7", "Ne7", "black", "Cavalier se replie pour soutenir l'attaque ...f5."),
    ],
    branches=[
        # Branch 1: Four Pawns Attack — White plays f4 at move 5
        TrainerBranch(
            label="Four Pawns Attack (5.f4)",
            fork_after_move=7,   # after black's ...d6
            opp_move=_m("f2f4", "f4", "white",
                        "Attaque des Quatre Pions — agressivite maximale. "
                        "Blanc veut etouffer la KID par la masse de pions."),
            continuation=[
                _m("e8g8", "O-O", "black",
                   "Roque rapide AVANT les hostilites — ne pas trainer."),
                _m("g1f3", "Nf3", "white"),
                _m("c7c5", "c5", "black",
                   "Coup-cle anti-Four-Pawns : on defie d4 immediatement."),
                _m("d4d5", "d5", "white", "Blanc bloque le centre."),
                _m("e7e6", "e6", "black",
                   "On ouvre la diagonale pour ...exd5 et l'echange central."),
                _m("f1e2", "Be2", "white"),
                _m("e6d5", "exd5", "black", "Ouvre la position."),
                _m("c4d5", "cxd5", "white"),
                _m("b8d7", "Nbd7", "black",
                   "Manoeuvre standard : Nb-d7-c5 ou Nb6 pour la pression."),
            ],
        ),
        # Branch 2: Exchange Variation — White trades at move 7
        TrainerBranch(
            label="Exchange Variation (7.dxe5)",
            fork_after_move=11,  # after black's ...e5
            opp_move=_m("d4e5", "dxe5", "white",
                        "Variante d'echange : blanc simplifie en finale "
                        "esperant un petit avantage. Mais c'est tout a fait jouable pour nous."),
            continuation=[
                _m("d6e5", "dxe5", "black",
                   "On reprend. La structure s'est simplifiee — c'est plus calme."),
                _m("d1d8", "Qxd8", "white",
                   "Echange de dames force — empeche le roque adverse aussi."),
                _m("f8d8", "Rfxd8", "black",
                   "On reprend avec la tour-roi (la tour-dame est bloquee par Nb8/Bc8). "
                   "Endgame equilibre, on garde l'activite des pieces."),
                _m("c1g5", "Bg5", "white",
                   "Cherche a creer des faiblesses avec le pin sur Nf6."),
                _m("b8d7", "Nbd7", "black",
                   "Developpement du cavalier vers d7 — degage b8 pour la tour."),
                _m("e1g1", "O-O", "white",
                   "Blanc roque court (O-O-O impossible : la colonne d est tenue par Rd8). "
                   "Position equilibree, endgame egal."),
                _m("c7c6", "c6", "black",
                   "Solidifie le centre, prepare ...Bf5 ou ...Nb6."),
            ],
        ),
        # Branch 3: Averbakh — White plays Bg5 to pin the knight at move 6
        TrainerBranch(
            label="Averbakh (6.Bg5)",
            fork_after_move=9,   # after black's ...O-O
            opp_move=_m("c1g5", "Bg5", "white",
                        "L'Averbakh : pin sur Nf6 avant le developpement du cavalier."),
            continuation=[
                _m("c7c5", "c5", "black",
                   "Defi central immediat — typique anti-Averbakh."),
                _m("d4d5", "d5", "white"),
                _m("e7e6", "e6", "black", "On ouvre la diagonale."),
                _m("f1e2", "Be2", "white",
                   "Developpement du fou (Nf3 deja joue), prepare le roque."),
                _m("e6d5", "exd5", "black"),
                _m("c4d5", "cxd5", "white"),
                _m("h7h6", "h6", "black",
                   "On chasse le fou — il devra prendre Nf6 ou reculer."),
                _m("g5f6", "Bxf6", "white",
                   "Le fou capture le cavalier — on perd le fianchetto mais on garde une bonne structure."),
                _m("g7f6", "Bxf6", "black", "Reprise avec le fou."),
            ],
        ),
    ],
))

# --- King's Indian Defense - Saemisch ---
_add(_opening(
    key="kid_saemisch",
    name="King's Indian Defense - Saemisch",
    base="King's Indian Defense",
    eco="E80",
    color="black",
    summary=(
        "Contre le Saemisch (f3), on accepte une structure plus statique et "
        "on cherche un break dynamique avec ...c5 ou ...b5."
    ),
    plan=[
        "Quand blanc joue f3, il prepare Be3, Qd2, 0-0-0 (attaque a l'aile dame).",
        "Notre plan : ...c5 ou ...b5 pour ouvrir l'aile-dame.",
        "Patience — la KID Saemisch est strategique avant d'etre tactique.",
    ],
    moves=[
        _m("d2d4", "d4", "white"),
        _m("g8f6", "Nf6", "black"),
        _m("c2c4", "c4", "white"),
        _m("g7g6", "g6", "black"),
        _m("b1c3", "Nc3", "white"),
        _m("f8g7", "Bg7", "black"),
        _m("e2e4", "e4", "white"),
        _m("d7d6", "d6", "black"),
        _m("f2f3", "f3", "white", "Saemisch : pion f3 soutient e4, prepare Be3."),
        _m("e8g8", "O-O", "black", "Roque rapide avant l'orage."),
        _m("c1e3", "Be3", "white"),
        _m("e7e5", "e5", "black", "Defi central — la KID joue toujours ...e5."),
    ],
))

# --- Sicilian Najdorf - English Attack ---
_add(_opening(
    key="sicilian_najdorf_english",
    name="Sicilian Najdorf - English Attack",
    base="Sicilian Najdorf",
    eco="B90",
    color="black",
    summary=(
        "La Najdorf : le sommet de la theorie sicilienne. On joue ...a6 "
        "pour preparer ...e5 ou ...b5. Contre l'English Attack (Be3, f3, "
        "Qd2, 0-0-0), on contre-attaque vivement sur l'aile-dame."
    ),
    plan=[
        "1...c5 sicilien, 2...d6 + 5...a6 (case-cle pour b5 et empeche Nb5).",
        "Apres ...e5, le cavalier blanc recule en b3.",
        "Vise b5 + Bb7 pour la pression diagonale.",
        "L'English Attack est theorique mais le plan est clair : course aux rois opposes.",
    ],
    moves=[
        _m("e2e4", "e4", "white"),
        _m("c7c5", "c5", "black", "Sicilienne : on attaque asymetriquement."),
        _m("g1f3", "Nf3", "white"),
        _m("d7d6", "d6", "black", "On soutient e5 et c5, structure typique."),
        _m("d2d4", "d4", "white"),
        _m("c5d4", "cxd4", "black"),
        _m("f3d4", "Nxd4", "white"),
        _m("g8f6", "Nf6", "black", "Attaque e4, force Nc3."),
        _m("b1c3", "Nc3", "white"),
        _m("a7a6", "a6", "black", "Le coup signature de la Najdorf : prepare b5, empeche Nb5/Bb5."),
        _m("c1e3", "Be3", "white", "English Attack — fou pour la pression."),
        _m("e7e5", "e5", "black", "Coup-cle de la Najdorf, gagne d4."),
        _m("d4b3", "Nb3", "white"),
        _m("c8e6", "Be6", "black", "Developpement, vise c4 et d5."),
        _m("f2f3", "f3", "white"),
        _m("h7h5", "h5", "black", "Empeche g4 et entame l'attaque sur l'aile roi."),
    ],
    branches=[
        # Branch 1: Fischer-Sozin — White plays Bc4 instead of Be3
        TrainerBranch(
            label="Fischer-Sozin (6.Bc4)",
            fork_after_move=9,   # after black's ...a6
            opp_move=_m("f1c4", "Bc4", "white",
                        "Fou italien — Fischer aimait cette attaque sur f7. "
                        "Vise une rapide explosion sur l'aile roi."),
            continuation=[
                _m("e7e6", "e6", "black",
                   "Anti-Sozin standard : on ferme la diagonale a2-g8, "
                   "solidifie f7, prepare ...b5."),
                _m("c4b3", "Bb3", "white",
                   "Le fou recule pour eviter ...Nxc4 et garder la pression."),
                _m("b7b5", "b5", "black",
                   "Expansion classique de la Najdorf sur l'aile dame."),
                _m("e1g1", "O-O", "white"),
                _m("c8b7", "Bb7", "black",
                   "Fianchetto — long diagonal, pression sur e4."),
                _m("f1e1", "Re1", "white", "Tour active, prepare e4-e5."),
                _m("b8d7", "Nbd7", "black",
                   "Manoeuvre vers ...Nc5 ou ...Ne5, double-pression centrale."),
            ],
        ),
        # Branch 2: Classical / Opocensky — White plays Be2
        TrainerBranch(
            label="Classical / Opocensky (6.Be2)",
            fork_after_move=9,
            opp_move=_m("f1e2", "Be2", "white",
                        "Classique : developpement tranquille avant le grand jeu. "
                        "Position equilibree, jeu strategique."),
            continuation=[
                _m("e7e5", "e5", "black",
                   "Notre coup-cle reste valable : on prend l'initiative au centre."),
                _m("d4b3", "Nb3", "white", "Cavalier recule comme dans English Attack."),
                _m("f8e7", "Be7", "black",
                   "Developpement classique, prepare le roque."),
                _m("e1g1", "O-O", "white"),
                _m("e8g8", "O-O", "black"),
                _m("c1e3", "Be3", "white"),
                _m("b8d7", "Nbd7", "black",
                   "Manoeuvre vers ...Nf8-Ng6 (typique Najdorf classique)."),
                _m("a2a4", "a4", "white",
                   "Blanc bloque ...b5. On doit adapter notre plan."),
                _m("b7b6", "b6", "black",
                   "On bascule sur ...Bb7 et le contre-jeu via la diagonale."),
            ],
        ),
        # Branch 3: Adams Attack — Modern English Attack with 6.h3
        TrainerBranch(
            label="Adams Attack (6.h3)",
            fork_after_move=9,
            opp_move=_m("h2h3", "h3", "white",
                        "Variante moderne : blanc prepare g4 plus tard sans coup tactique premature."),
            continuation=[
                _m("e7e5", "e5", "black", "On joue toujours notre Najdorf — central et solide."),
                _m("d4b3", "Nb3", "white"),
                _m("c8e6", "Be6", "black", "Developpement standard."),
                _m("g2g4", "g4", "white",
                   "Blanc declare ses intentions agressives sur l'aile roi."),
                _m("d6d5", "d5", "black",
                   "Riposte centrale ! Coup typique quand blanc ouvre l'aile roi."),
                _m("e4d5", "exd5", "white"),
                _m("f6d5", "Nxd5", "black",
                   "Reprend avec le cavalier — actif au centre."),
                _m("b3d4", "Nbd4", "white"),
            ],
        ),
    ],
))

# --- Sicilian Najdorf - Bg5 line ---
_add(_opening(
    key="sicilian_najdorf_bg5",
    name="Sicilian Najdorf - 6.Bg5 (Main Line)",
    base="Sicilian Najdorf",
    eco="B96",
    color="black",
    summary=(
        "La ligne classique 6.Bg5 contre la Najdorf — la plus theorique "
        "des sicilien. Reponse principale : 6...e6 puis 7...Be7."
    ),
    plan=[
        "Apres 6.Bg5, ne PAS prendre, repondre 6...e6.",
        "Be7 puis 0-0 — roi en securite avant tout.",
        "...Qa5 ou ...b5 selon ce que blanc fait.",
    ],
    moves=[
        _m("e2e4", "e4", "white"),
        _m("c7c5", "c5", "black"),
        _m("g1f3", "Nf3", "white"),
        _m("d7d6", "d6", "black"),
        _m("d2d4", "d4", "white"),
        _m("c5d4", "cxd4", "black"),
        _m("f3d4", "Nxd4", "white"),
        _m("g8f6", "Nf6", "black"),
        _m("b1c3", "Nc3", "white"),
        _m("a7a6", "a6", "black", "Najdorf base."),
        _m("c1g5", "Bg5", "white", "Ligne principale anti-Najdorf."),
        _m("e7e6", "e6", "black", "Reponse universelle a Bg5."),
        _m("f2f4", "f4", "white"),
        _m("f8e7", "Be7", "black", "Be7 plutot que Be7 : casse le pin."),
        _m("d1f3", "Qf3", "white"),
        _m("d8c7", "Qc7", "black", "Pression sur c-line, prepare ...Nbd7."),
    ],
))

# --- Modern Benoni ---
_add(_opening(
    key="modern_benoni_classical",
    name="Modern Benoni - Classical",
    base="Modern Benoni",
    eco="A60",
    color="black",
    summary=(
        "Defense agressive contre 1.d4 : on accepte une majorite blanche au "
        "centre en echange d'une majorite a l'aile-dame et de cases noires "
        "tres fortes."
    ),
    plan=[
        "1...Nf6, 2...c5 — defi immediat.",
        "Apres 3.d5 e6, on echange 4...exd5 5.cxd5 d6.",
        "Fianchetto ...g6 + Bg7 pour exploiter la grande diagonale.",
        "Plan a long terme : ...b5 ! pour casser le centre blanc.",
    ],
    moves=[
        _m("d2d4", "d4", "white"),
        _m("g8f6", "Nf6", "black"),
        _m("c2c4", "c4", "white"),
        _m("c7c5", "c5", "black", "Coup-cle du Benoni — on defie le centre."),
        _m("d4d5", "d5", "white"),
        _m("e7e6", "e6", "black", "On force l'echange central, sinon le pion d5 etouffe tout."),
        _m("b1c3", "Nc3", "white"),
        _m("e6d5", "exd5", "black"),
        _m("c4d5", "cxd5", "white"),
        _m("d7d6", "d6", "black", "Structure Benoni : pion d6 contre d5."),
        _m("e2e4", "e4", "white"),
        _m("g7g6", "g6", "black", "Prepare le fianchetto, fou tres fort sur g7."),
        _m("g1f3", "Nf3", "white"),
        _m("f8g7", "Bg7", "black"),
        _m("f1e2", "Be2", "white"),
        _m("e8g8", "O-O", "black", "Roi en securite, on prepare ...a6 + ...b5."),
    ],
))


# ===== WHITE — Anti-Sicilians & e4-specials ==============================

# --- Smith-Morra Gambit (vs Sicilian) ---
_add(_opening(
    key="smith_morra_gambit",
    name="Smith-Morra Gambit",
    base="Smith-Morra Gambit",
    eco="B21",
    color="white",
    summary=(
        "Anti-Sicilien tres agressif : on sacrifie un pion pour un developpement "
        "fulgurant et l'ouverture des colonnes c et d. Arme devastatrice "
        "jusqu'a 2000 ELO car peu connue cote noir."
    ),
    plan=[
        "Sacrifice du pion d4, on accepte de perdre un pion.",
        "Cavalier sur c3 + fou sur c4 : pression sur f7 et la colonne c.",
        "Roque court rapide, tours sur c1 et d1 — toutes les pieces actives.",
        "Plan typique : Qe2, Rd1, Nb5/Nd5 — coups tactiques.",
    ],
    moves=[
        _m("e2e4", "e4", "white"),
        _m("c7c5", "c5", "black"),
        _m("d2d4", "d4", "white", "On joue le gambit immediatement."),
        _m("c5d4", "cxd4", "black", "Noir accepte (le refuser via ...d3 est aussi possible)."),
        _m("c2c3", "c3", "white", "Le coeur du Smith-Morra : on offre encore le pion c3."),
        _m("d4c3", "dxc3", "black", "Noir accepte le pion."),
        _m("b1c3", "Nxc3", "white", "Developpement avec gain de tempo, colonne c semi-ouverte."),
        _m("b8c6", "Nc6", "black"),
        _m("g1f3", "Nf3", "white", "Developpement naturel."),
        _m("d7d6", "d6", "black"),
        _m("f1c4", "Bc4", "white", "Fou italien — vise f7, classique."),
        _m("e7e6", "e6", "black", "Defense solide, mais on garde l'initiative."),
        _m("e1g1", "O-O", "white", "Roi en securite, on prepare les tours."),
        _m("g8f6", "Nf6", "black"),
        _m("d1e2", "Qe2", "white",
           "Dame sur e2 — libere la case d1 pour la tour, prepare Rd1."),
        _m("f8e7", "Be7", "black"),
        _m("f1d1", "Rd1", "white",
           "Tour sur la colonne d ouverte — pression directe sur d6."),
    ],
))

# --- Grand Prix Attack (Closed Sicilian variant) ---
_add(_opening(
    key="grand_prix_attack",
    name="Grand Prix Attack",
    base="Grand Prix Attack",
    eco="B23",
    color="white",
    summary=(
        "Anti-Sicilien avec f4 : on prepare une attaque directe sur le roi noir "
        "avec f5 et Qe1-h4. Ideal contre les sicilien avec ...Nc6 ou ...g6."
    ),
    plan=[
        "2.Nc3 + 3.f4 : on annonce immediatement l'attaque sur l'aile roi.",
        "Bb5 pour echanger ou enerver le Nc6 noir.",
        "Roque court puis f5 quand possible, suivi de Qe1-h4.",
        "Plan a long terme : Rf3-h3 (lift de tour) pour l'attaque mat.",
    ],
    moves=[
        _m("e2e4", "e4", "white"),
        _m("c7c5", "c5", "black"),
        _m("b1c3", "Nc3", "white", "Pas de Sicilienne ouverte — on garde le pion d2."),
        _m("b8c6", "Nc6", "black"),
        _m("f2f4", "f4", "white", "Coeur du Grand Prix : annonce l'attaque sur l'aile roi."),
        _m("g7g6", "g6", "black", "Setup fianchetto classique."),
        _m("g1f3", "Nf3", "white"),
        _m("f8g7", "Bg7", "black"),
        _m("f1c4", "Bc4", "white",
           "Fou italien — vise f7 et soutient le futur f5."),
        _m("e7e6", "e6", "black", "Solidifie f7 et prepare ...Nge7."),
        _m("e1g1", "O-O", "white",
           "Roque rapide avant l'attaque sur l'aile roi."),
        _m("g8e7", "Nge7", "black",
           "Cavalier defensif — protege f5/g6, libere f6 pour la dame."),
        _m("d2d3", "d3", "white",
           "Structure typique : on garde e4 et prepare Qe1-h4."),
        _m("e8g8", "O-O", "black"),
        _m("d1e1", "Qe1", "white",
           "Manoeuvre signature : la dame va en h4 via e1."),
        _m("d7d6", "d6", "black"),
        _m("e1h4", "Qh4", "white",
           "Dame en h4 — pression directe sur l'aile roi, prepare f5."),
    ],
))

# --- French Defense - Advance Variation (white side) ---
_add(_opening(
    key="french_advance_white",
    name="French - Advance Variation (Blancs)",
    base="French Advance",
    eco="C02",
    color="white",
    summary=(
        "Reponse simple et agressive a 1...e6 : on pousse 3.e5 pour bloquer "
        "le centre et obtenir un avantage d'espace. Plan classique : attaque "
        "sur l'aile-roi pendant que noir cherche le contre-jeu via ...c5."
    ),
    plan=[
        "3.e5 ferme le centre — noir doit jouer ...c5 pour le contester.",
        "c3 + Nf3 pour soutenir d4.",
        "Bd3 (ou Be2) + O-O, puis l'attaque vient via h4-h5 ou Nh3-Nf4.",
        "Cle strategique : ne PAS prendre cxd4 trop vite, garder le pion e5 fort.",
    ],
    moves=[
        _m("e2e4", "e4", "white"),
        _m("e7e6", "e6", "black"),
        _m("d2d4", "d4", "white"),
        _m("d7d5", "d5", "black"),
        _m("e4e5", "e5", "white", "Variante d'avance — on ferme le centre."),
        _m("c7c5", "c5", "black", "Reponse standard : noir attaque la chaine de pions."),
        _m("c2c3", "c3", "white", "Soutient d4 pour garder la chaine intacte."),
        _m("b8c6", "Nc6", "black"),
        _m("g1f3", "Nf3", "white", "Developpement, soutient e5 et d4."),
        _m("d8b6", "Qb6", "black", "Coup-cle noir : pression sur b2 et d4."),
        _m("a2a3", "a3", "white",
           "Prepare b4 pour gagner de l'espace a l'aile dame et empecher ...Nb4."),
        _m("g8h6", "Nh6", "black",
           "Cavalier exterieur — viendra sur f5 pour la pression sur d4."),
        _m("b2b4", "b4", "white", "Espace a l'aile dame, le fou c1 reste a developer."),
        _m("c5d4", "cxd4", "black"),
        _m("c3d4", "cxd4", "white",
           "On reprend avec le pion — structure isolanide eventuellement, mais centre fort."),
        _m("h6f5", "Nf5", "black"),
        _m("f1d3", "Bd3", "white",
           "Developpement du fou-roi, prepare le roque et menace Bxf5."),
    ],
))

# --- Caro-Kann - Advance Variation ---
_add(_opening(
    key="caro_kann_advance_white",
    name="Caro-Kann - Advance (Blancs)",
    base="Caro-Kann Advance",
    eco="B12",
    color="white",
    summary=(
        "Meme idee que l'Avance Francaise contre 1...c6 : on pousse 3.e5 pour "
        "fermer le centre et exploiter le fou c8 noir (souvent piece-probleme)."
    ),
    plan=[
        "3.e5 ferme — but : exploiter le fou c8 qui aura du mal a sortir.",
        "Le fou noir va souvent sortir en f5 — on l'attaque avec h4-h5 ou Nh4.",
        "Developpement Nf3, Bd3, O-O, puis attaque sur l'aile roi.",
        "Plan typique : c3 + Nbd2 — meme structure que l'Avance Francaise.",
    ],
    moves=[
        _m("e2e4", "e4", "white"),
        _m("c7c6", "c6", "black"),
        _m("d2d4", "d4", "white"),
        _m("d7d5", "d5", "black"),
        _m("e4e5", "e5", "white", "Variante d'avance — bloque le fou c8 noir."),
        _m("c8f5", "Bf5", "black", "Le fou sort AVANT d'etre enferme — coup standard."),
        _m("g1f3", "Nf3", "white",
           "Developpement, prepare Bd3 ou h4 pour attaquer Bf5."),
        _m("e7e6", "e6", "black"),
        _m("f1e2", "Be2", "white",
           "Fou modeste — prepare le roque et h4 pour gagner du temps sur Bf5."),
        _m("c6c5", "c5", "black", "Contre-jeu noir typique sur le centre."),
        _m("c1e3", "Be3", "white", "Soutient d4, developpe le fou de cases noires."),
        _m("d8b6", "Qb6", "black"),
        _m("b1c3", "Nc3", "white",
           "Developpement, prepare a3-b4 si necessaire, controle d5."),
        _m("c5d4", "cxd4", "black"),
        _m("f3d4", "Nxd4", "white",
           "On reprend avec le cavalier — case d4 devient une excellente avant-poste."),
    ],
))

# --- Evans Gambit (vs 1...e5) ---
_add(_opening(
    key="evans_gambit",
    name="Evans Gambit",
    base="Evans Gambit",
    eco="C51",
    color="white",
    summary=(
        "Variante super-agressive de l'Italienne : on sacrifie le pion b4 pour "
        "gagner deux tempi sur le fou noir et construire un centre ecrasant. "
        "Arme legendaire de Morphy."
    ),
    plan=[
        "Apres la position italienne, on joue 4.b4 — sacrifice de pion.",
        "Si ...Bxb4 : on joue c3 + d4, centre maximum.",
        "Roque rapide et attaque directe sur le roi noir avec e5 ou Ba3.",
        "Theme : ouverture des diagonales, sacrifices tactiques.",
    ],
    moves=[
        _m("e2e4", "e4", "white"),
        _m("e7e5", "e5", "black"),
        _m("g1f3", "Nf3", "white"),
        _m("b8c6", "Nc6", "black"),
        _m("f1c4", "Bc4", "white"),
        _m("f8c5", "Bc5", "black"),
        _m("b2b4", "b4", "white",
           "GAMBIT EVANS : on offre le pion b4 pour gagner du temps sur Bc5."),
        _m("c5b4", "Bxb4", "black", "Acceptation classique."),
        _m("c2c3", "c3", "white", "Attaque le fou noir, force-le a reculer."),
        _m("b4a5", "Ba5", "black",
           "Le fou recule sur a5 — defense la plus solide."),
        _m("d2d4", "d4", "white",
           "Centre maximum, on ouvre la position en notre faveur."),
        _m("e5d4", "exd4", "black"),
        _m("e1g1", "O-O", "white",
           "Roi en securite, prepare les tactiques sur l'aile roi."),
        _m("g8e7", "Nge7", "black", "Defense moderne (Lasker)."),
        _m("c3d4", "cxd4", "white",
           "On reprend, centre 100% blanc."),
        _m("a5b6", "Bb6", "black", "Le fou se replace sur la diagonale a7-g1."),
        _m("b1c3", "Nc3", "white", "Developpement complet, dame mobilisable."),
    ],
))

# --- Scandinavian Defense (white response) ---
_add(_opening(
    key="scandinavian_white",
    name="Scandinavian Defense - 3.Nc3 (Blancs)",
    base="Scandinavian (White)",
    eco="B01",
    color="white",
    summary=(
        "Contre 1...d5, on prend simplement 2.exd5 et on developpe avec gain "
        "de tempo en attaquant la dame noire avec Nc3."
    ),
    plan=[
        "2.exd5 — on accepte le pion offert.",
        "Apres 2...Qxd5 3.Nc3 : gain de tempo sur la dame.",
        "Developpement naturel : Nf3, d4, Bc4 ou Bd3.",
        "Roque court, jeu central et solide. Blanc a un petit avantage stable.",
    ],
    moves=[
        _m("e2e4", "e4", "white"),
        _m("d7d5", "d5", "black"),
        _m("e4d5", "exd5", "white", "On prend le pion offert."),
        _m("d8d5", "Qxd5", "black", "Reprise dame — la plus jouee."),
        _m("b1c3", "Nc3", "white", "Attaque la dame avec gain de tempo."),
        _m("d5a5", "Qa5", "black", "Retraite typique (Qd6 et Qd8 aussi possibles)."),
        _m("d2d4", "d4", "white", "Centre fort, ouvre Bc1."),
        _m("g8f6", "Nf6", "black"),
        _m("g1f3", "Nf3", "white", "Developpement, soutient e5."),
        _m("c7c6", "c6", "black", "Solidifie la dame contre Nd5 ou Nb5."),
        _m("f1c4", "Bc4", "white", "Fou actif, vise f7."),
        _m("c8f5", "Bf5", "black", "Developpement du fou-probleme."),
        _m("e1g1", "O-O", "white", "Roi en securite, on a un petit plus stable."),
        _m("e7e6", "e6", "black"),
        _m("f1e1", "Re1", "white",
           "Tour active sur la colonne e semi-ouverte."),
    ],
))


# ===== BLACK — Anti-Sicilians (as Black, completing Najdorf) =============

# --- Anti-Alapin (vs 2.c3 with ...d5) ---
_add(_opening(
    key="sicilian_anti_alapin",
    name="Sicilian Anti-Alapin (2...d5)",
    base="Anti-Alapin",
    eco="B22",
    color="black",
    summary=(
        "Contre l'Alapin (2.c3), la reponse-cle est 2...d5 : on conteste "
        "immediatement le centre et on neutralise l'idee blanche de jouer "
        "d4 sans contre-jeu noir."
    ),
    plan=[
        "2...d5 immediatement — c'est LA reponse a l'Alapin.",
        "Apres 3.exd5 Qxd5 : la dame n'est pas chassee facilement car c4 est bloque par c3.",
        "Developpement classique : Nf6, Nc6, Bg4 ou Bf5, e6.",
        "Plan : structure saine, jeu equilibre — l'Alapin n'a aucune morsure.",
    ],
    moves=[
        _m("e2e4", "e4", "white"),
        _m("c7c5", "c5", "black", "Sicilienne."),
        _m("c2c3", "c3", "white", "Alapin — anti-sicilien tranquille."),
        _m("d7d5", "d5", "black",
           "COUP-CLE : defi central immediat. Sans cela l'Alapin marche bien."),
        _m("e4d5", "exd5", "white"),
        _m("d8d5", "Qxd5", "black",
           "La dame est ici stable car c4 est bloque par c3 — pas de Nc3 attaquant !"),
        _m("d2d4", "d4", "white"),
        _m("g8f6", "Nf6", "black", "Developpement, controle e4."),
        _m("g1f3", "Nf3", "white"),
        _m("c8g4", "Bg4", "black",
           "Pin sur Nf3 — gene le developpement blanc."),
        _m("f1e2", "Be2", "white"),
        _m("e7e6", "e6", "black", "Solidifie d5 et prepare Bd6 ou Be7."),
        _m("b1a3", "Na3", "white", "Cavalier exterieur (la c3 est pour le pion)."),
        _m("b8c6", "Nc6", "black", "Developpement complet."),
        _m("e1g1", "O-O", "white"),
        _m("c5d4", "cxd4", "black",
           "On simplifie au bon moment, structure equilibree."),
    ],
))

# --- Anti-Rossolimo/Moscou (vs 3.Bb5 / 3.Bb5+) ---
_add(_opening(
    key="sicilian_anti_moscow",
    name="Sicilian Anti-Moscow (3...Bd7)",
    base="Anti-Moscow",
    eco="B51",
    color="black",
    summary=(
        "Contre 3.Bb5+ (Moscou) apres 2...d6, on joue 3...Bd7 — echange "
        "simple, structure saine. La variante Rossolimo (apres 2...Nc6) se "
        "traite de facon similaire."
    ),
    plan=[
        "Apres 1.e4 c5 2.Nf3 d6 3.Bb5+, on bloque avec ...Bd7.",
        "Echange Bxd7 Qxd7 : structure de pions intacte, dame active.",
        "Developpement classique : Nf6, Nc6, e6, Be7, O-O.",
        "Plan : pas de Sicilienne ouverte, jeu strategique tranquille mais sain.",
    ],
    moves=[
        _m("e2e4", "e4", "white"),
        _m("c7c5", "c5", "black"),
        _m("g1f3", "Nf3", "white"),
        _m("d7d6", "d6", "black", "On garde le setup Najdorf-compatible."),
        _m("f1b5", "Bb5+", "white", "Moscou — evite la Sicilienne ouverte."),
        _m("c8d7", "Bd7", "black",
           "REPONSE-CLE : on bloque avec le fou-probleme. Structure intacte."),
        _m("b5d7", "Bxd7+", "white"),
        _m("d8d7", "Qxd7", "black",
           "Reprise dame — active, libere la case d8 pour la tour."),
        _m("c2c4", "c4", "white",
           "Setup Maroczy bind — controle de la case d5."),
        _m("g8f6", "Nf6", "black"),
        _m("b1c3", "Nc3", "white"),
        _m("b8c6", "Nc6", "black", "Developpement classique."),
        _m("d2d4", "d4", "white"),
        _m("c5d4", "cxd4", "black"),
        _m("f3d4", "Nxd4", "white"),
        _m("g7g6", "g6", "black",
           "Fianchetto-Dragon comme structure — fou actif sur la grande diagonale."),
        _m("c1e3", "Be3", "white",
           "Le fou-roi a deja ete echange — on developpe l'autre fou pour soutenir Nd4."),
        _m("f8g7", "Bg7", "black", "Developpement complet."),
    ],
))

# --- Anti-Smith-Morra (as Black) ---
_add(_opening(
    key="sicilian_anti_smith_morra",
    name="Sicilian vs Smith-Morra (Siberian)",
    base="Anti-Smith-Morra",
    eco="B21",
    color="black",
    summary=(
        "Setup robuste contre le Smith-Morra : on prend les pions et on "
        "joue le Scheveningen 'Siberian' — Nge7 + a6 + e6 pour absorber "
        "la pression et garder le pion supplementaire."
    ),
    plan=[
        "On accepte le gambit : 2...cxd4 3...dxc3 4...Nxc3 — on prend les pions.",
        "Setup-cle : ...a6 (empeche Nb5), ...e6 (solide), ...Nge7 (defend f5).",
        "Le cavalier en e7 protege Bg6/f5 et libere f6 pour la dame.",
        "Plan : roque, ...d6, ...Bd7 — defendre patiemment puis convertir le pion.",
    ],
    moves=[
        _m("e2e4", "e4", "white"),
        _m("c7c5", "c5", "black"),
        _m("d2d4", "d4", "white", "Smith-Morra — on accepte."),
        _m("c5d4", "cxd4", "black"),
        _m("c2c3", "c3", "white"),
        _m("d4c3", "dxc3", "black", "On accepte le second pion."),
        _m("b1c3", "Nxc3", "white"),
        _m("b8c6", "Nc6", "black", "Developpement, controle d4."),
        _m("g1f3", "Nf3", "white"),
        _m("e7e6", "e6", "black", "Solidifie f5 + d5, structure saine."),
        _m("f1c4", "Bc4", "white", "Fou italien."),
        _m("a7a6", "a6", "black",
           "Coup-cle : empeche Nb5 et prepare ...b5 pour chasser Bc4."),
        _m("e1g1", "O-O", "white"),
        _m("g8e7", "Nge7", "black",
           "Manoeuvre Siberian — le cavalier va en g6, libere f6 pour la dame, defend f5."),
        _m("c4b3", "Bb3", "white"),
        _m("e7g6", "Ng6", "black",
           "Cavalier en g6 — defense ferme, prepare ...Be7 et le roque."),
        _m("f1e1", "Re1", "white"),
        _m("f8e7", "Be7", "black", "Developpement, prepare le roque."),
    ],
))


# ===== BLACK — Anti-d4 systems (completing King's Indian) ================

# --- KID vs London System ---
_add(_opening(
    key="kid_vs_london",
    name="KID Setup vs London System",
    base="KID vs London",
    eco="A48",
    color="black",
    summary=(
        "Contre le Londonien (Bf4 sans c4), on garde le setup King's Indian "
        "mais avec un timing different : pousser ...c5 tot pour attaquer d4 "
        "avant que blanc ne consolide."
    ),
    plan=[
        "Setup KID standard : ...Nf6, ...g6, ...Bg7, ...d6, O-O.",
        "Coup-cle : ...c5 ! immediatement — attaque d4 sans c4 pour le soutenir.",
        "Si dxc5, recapture avec ...Qa5+ puis ...Qxc5 (gain de tempo).",
        "Plan : controle de e5 (l'enjeu central) + ...Nh5 pour echanger Bf4.",
    ],
    moves=[
        _m("d2d4", "d4", "white"),
        _m("g8f6", "Nf6", "black"),
        _m("g1f3", "Nf3", "white", "Pas de c4 — signe d'un systeme."),
        _m("g7g6", "g6", "black", "On lance le fianchetto sans attendre."),
        _m("c1f4", "Bf4", "white", "Londonien confirme — le fou sort tot."),
        _m("f8g7", "Bg7", "black"),
        _m("e2e3", "e3", "white"),
        _m("e8g8", "O-O", "black", "Roi en securite avant les hostilites."),
        _m("h2h3", "h3", "white", "Prophylaxie standard, evite ...Bg4."),
        _m("d7d6", "d6", "black"),
        _m("f1e2", "Be2", "white"),
        _m("c7c5", "c5", "black",
           "COUP-CLE : on attaque d4 SANS que c4 ne le soutienne. Difference cruciale vs KID classique."),
        _m("c2c3", "c3", "white"),
        _m("c5d4", "cxd4", "black", "On simplifie au bon moment."),
        _m("c3d4", "cxd4", "white"),
        _m("d8b6", "Qb6", "black",
           "Pression sur b2 et d4 — coup signature anti-London."),
        _m("d1c2", "Qc2", "white"),
        _m("b8c6", "Nc6", "black", "Developpement complet, position equilibree."),
    ],
))

# --- Anti-Trompowsky ---
_add(_opening(
    key="anti_trompowsky",
    name="Anti-Trompowsky (2...e6)",
    base="Anti-Trompowsky",
    eco="A45",
    color="black",
    summary=(
        "Contre 2.Bg5 (Trompowsky), la reponse pratique est 2...e6 : on accepte "
        "un doublement de pion potentiel pour obtenir la paire de fous et un "
        "developpement rapide."
    ),
    plan=[
        "2...e6 evite les complications de 2...Ne4 (theorique).",
        "Apres 3.e4 h6 4.Bxf6 Qxf6 : on a la paire de fous, dame active.",
        "Plan : ...d6, ...g6, ...Bg7 — setup KID modifie.",
        "L'absence de c4 nous donne le temps de jouer ...c5 pour le contre-jeu central.",
    ],
    moves=[
        _m("d2d4", "d4", "white"),
        _m("g8f6", "Nf6", "black"),
        _m("c1g5", "Bg5", "white", "Trompowsky — pin sur le cavalier."),
        _m("e7e6", "e6", "black",
           "On prepare ...h6 et la prise eventuelle avec la dame."),
        _m("e2e4", "e4", "white", "Blanc joue le plan agressif."),
        _m("h7h6", "h6", "black", "On chasse le fou."),
        _m("g5f6", "Bxf6", "white"),
        _m("d8f6", "Qxf6", "black",
           "Reprise dame — paire de fous + dame active sur la diagonale."),
        _m("b1c3", "Nc3", "white"),
        _m("d7d6", "d6", "black", "Structure flexible, prepare ...g6."),
        _m("d1d2", "Qd2", "white"),
        _m("g7g6", "g6", "black",
           "Fianchetto KID-like — fou puissant sur la grande diagonale."),
        _m("e1c1", "O-O-O", "white", "Blanc roque long — course aux rois opposes."),
        _m("f8g7", "Bg7", "black"),
        _m("g1f3", "Nf3", "white"),
        _m("b8c6", "Nc6", "black",
           "Developpement complet, on prepare ...Bd7 et ...O-O-O ou ...a6 + ...b5."),
    ],
))

# --- Anti-Jobava London (Slav setup) ---
_add(_opening(
    key="anti_jobava_slav",
    name="Anti-Jobava (Slav setup)",
    base="Anti-Jobava",
    eco="D00",
    color="black",
    summary=(
        "Contre le Jobava London (2.Nc3 + 3.Bf4), le setup KID ne fonctionne "
        "PAS bien — on bascule sur un setup Slave avec ...d5 et ...c6 pour "
        "garantir une structure solide."
    ),
    plan=[
        "Coup-cle : 2...d5 ! (et pas ...g6) — refute le plan blanc.",
        "...c6 + ...Bf5 (ou Bg4) — developpement Slave classique.",
        "Le fou c8 sort AVANT ...e6, c'est le point cle.",
        "Plan : ...e6, ...Nbd7, ...Bd6 ou Be7, ...O-O — structure saine.",
    ],
    moves=[
        _m("d2d4", "d4", "white"),
        _m("g8f6", "Nf6", "black"),
        _m("b1c3", "Nc3", "white",
           "Jobava London signale (cavalier sur c3 sans c4)."),
        _m("d7d5", "d5", "black",
           "COUP-CLE : on quitte la KID. Le setup Jobava est inefficace contre ...d5."),
        _m("c1f4", "Bf4", "white", "Jobava confirme."),
        _m("c7c6", "c6", "black", "Slave — solidite maximale."),
        _m("e2e3", "e3", "white"),
        _m("c8f5", "Bf5", "black",
           "On sort le fou-probleme AVANT ...e6 — point cle du Slave."),
        _m("g1f3", "Nf3", "white"),
        _m("e7e6", "e6", "black", "Maintenant on ferme la diagonale."),
        _m("f1d3", "Bd3", "white", "Echange propose."),
        _m("f5d3", "Bxd3", "black",
           "On echange — pas de probleme de developpement pour nous."),
        _m("d1d3", "Qxd3", "white"),
        _m("f8d6", "Bd6", "black",
           "Fou actif, propose echange avec Bf4 — joue AVANT Nbd7 pour garder la colonne d ouverte pour la dame."),
        _m("f4d6", "Bxd6", "white"),
        _m("d8d6", "Qxd6", "black",
           "Reprise dame — bien placee, controle d-line."),
        _m("e1g1", "O-O", "white"),
        _m("b8d7", "Nbd7", "black",
           "Developpement final, position equilibree."),
    ],
))


# --- Public helpers ------------------------------------------------------

def _by_base(items: Iterable[TrainerOpening]) -> dict[str, list[TrainerOpening]]:
    groups: dict[str, list[TrainerOpening]] = {}
    for op in items:
        groups.setdefault(op.base_name, []).append(op)
    return groups


def list_openings() -> list[dict]:
    """Flat list (legacy + new grouping field)."""
    return [
        {
            "key": op.key,
            "name": op.name,
            "base_name": op.base_name,
            "eco": op.eco,
            "user_color": op.user_color,
            "summary": op.summary,
            "plies": len(op.moves),
            "variant_count": sum(1 for o in LIBRARY.values() if o.base_name == op.base_name),
        }
        for op in LIBRARY.values()
    ]


def list_openings_grouped() -> list[dict]:
    """Grouped by base_name for the UI."""
    groups = _by_base(LIBRARY.values())
    out = []
    for base_name, variants in groups.items():
        first = variants[0]
        out.append({
            "base_name": base_name,
            "eco": first.eco,
            "user_color": first.user_color,
            "summary": first.summary,
            "variants": [
                {
                    "key": v.key,
                    "name": v.name,
                    "eco": v.eco,
                    "plies": len(v.moves),
                }
                for v in variants
            ],
        })
    return out


def get_opening(key: str) -> TrainerOpening | None:
    return LIBRARY.get(key)
