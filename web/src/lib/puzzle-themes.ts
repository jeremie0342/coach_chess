/**
 * French labels + short hints for Lichess puzzle themes. The hint is purposely
 * generic — it nudges the user toward the right *family* of moves without
 * revealing the solution.
 */

export type ThemeMeta = {
  label: string;
  hint: string;
  /** Priority among multiple themes (higher = more specific) */
  priority: number;
};

const META: Record<string, ThemeMeta> = {
  // --- Tactical motifs ---
  fork: {
    label: "Fourchette",
    hint: "Cherche un coup où une pièce attaque deux cibles d'un coup — souvent un cavalier ou un pion.",
    priority: 80,
  },
  pin: {
    label: "Clouage",
    hint: "Une pièce adverse est sur la même ligne qu'une pièce plus précieuse. Cloue-la pour la paralyser.",
    priority: 80,
  },
  skewer: {
    label: "Enfilade",
    hint: "Force une pièce précieuse à fuir, et capture celle qui était derrière.",
    priority: 80,
  },
  discoveredAttack: {
    label: "Attaque à la découverte",
    hint: "Bouge une pièce pour démasquer l'attaque d'une autre derrière elle.",
    priority: 85,
  },
  doubleCheck: {
    label: "Échec double",
    hint: "Un seul coup pour deux échecs : le roi DOIT bouger. Cherche un mouvement à découverte qui donne aussi échec.",
    priority: 90,
  },
  hangingPiece: {
    label: "Pièce en prise",
    hint: "Une pièce adverse n'est pas défendue. Trouve-la et prends-la.",
    priority: 75,
  },
  trappedPiece: {
    label: "Pièce piégée",
    hint: "Cherche une pièce adverse qui ne peut plus fuir si tu joues le bon coup.",
    priority: 75,
  },
  attraction: {
    label: "Attraction",
    hint: "Attire une pièce adverse sur une case fatale (sacrifice puis tactique).",
    priority: 70,
  },
  deflection: {
    label: "Déflexion",
    hint: "Détourne une pièce qui défend une autre cible.",
    priority: 70,
  },
  decoy: {
    label: "Leurre",
    hint: "Force une pièce adverse à abandonner sa case.",
    priority: 70,
  },
  // --- Mates ---
  mate: {
    label: "Mat",
    hint: "Il y a un mat forcé. Vise le roi adverse.",
    priority: 50,
  },
  mateIn1: { label: "Mat en 1", hint: "Mat en un seul coup. Vise toutes les cases d'attaque du roi.", priority: 100 },
  mateIn2: { label: "Mat en 2", hint: "Mat forcé en 2 coups. Le 1er coup limite les fuites du roi, le 2ème mate.", priority: 100 },
  mateIn3: { label: "Mat en 3", hint: "Mat forcé en 3 coups. Calcul plus profond — souvent un sacrifice initial.", priority: 100 },
  mateIn4: { label: "Mat en 4", hint: "Mat en 4. Visualise jusqu'au bout de la séquence.", priority: 100 },
  mateIn5: { label: "Mat en 5", hint: "Mat profond. Réservé aux puzzles avancés.", priority: 100 },
  smotheredMate: { label: "Mat étouffé", hint: "Le cavalier mate un roi piégé par ses propres pièces.", priority: 95 },
  backRankMate: { label: "Mat du couloir", hint: "Le roi est bloqué par ses propres pions sur la dernière rangée.", priority: 95 },
  arabianMate: { label: "Mat arabe", hint: "Tour + cavalier mat. Pattern typique sur le bord.", priority: 90 },
  // --- Phases ---
  opening: { label: "Ouverture", hint: "Puzzle en phase d'ouverture (premiers coups).", priority: 20 },
  middlegame: { label: "Milieu de partie", hint: "Position de milieu de partie — calcul + plan.", priority: 20 },
  endgame: { label: "Finale", hint: "Finale. Pense roi actif, opposition, règle du carré.", priority: 40 },
  // --- Endgame types ---
  pawnEndgame: { label: "Finale de pions", hint: "Roi actif + opposition. La promotion est la clé.", priority: 60 },
  rookEndgame: { label: "Finale de tours", hint: "Active ta tour, prends la 7e rangée, gêne le roi adverse.", priority: 60 },
  queenEndgame: { label: "Finale de dames", hint: "Mat ou perpétuel. Garde le roi en sécurité.", priority: 60 },
  bishopEndgame: { label: "Finale de fous", hint: "Fous de couleurs opposées = nul fréquent. Même couleur = pression.", priority: 60 },
  knightEndgame: { label: "Finale de cavaliers", hint: "Centralise ton cavalier. Les pions de chaque aile sont délicats.", priority: 60 },
  rookVsBishop: { label: "Tour contre fou", hint: "Avantage matériel léger : conduis vers une finale gagnante.", priority: 55 },
  // --- Length ---
  short: { label: "Court", hint: "Séquence rapide (2-3 coups).", priority: 10 },
  long: { label: "Long", hint: "Séquence longue — calcul approfondi nécessaire.", priority: 10 },
  veryLong: { label: "Très long", hint: "5+ coups. Patience et précision.", priority: 10 },
  oneMove: { label: "Un coup", hint: "Un seul coup à trouver.", priority: 10 },
  // --- Difficulty ---
  crushing: { label: "Écrasant", hint: "Gain matériel ou positionnel massif.", priority: 30 },
  advantage: { label: "Avantage", hint: "Trouve le coup qui consolide ton avantage.", priority: 30 },
  equality: { label: "Égalité", hint: "Tu dois trouver le seul coup qui maintient l'égalité.", priority: 30 },
  // --- Other ---
  sacrifice: { label: "Sacrifice", hint: "Donne du matériel pour une tactique gagnante.", priority: 65 },
  zugzwang: { label: "Zugzwang", hint: "L'adversaire ne peut pas bouger sans empirer sa position.", priority: 70 },
  master: { label: "Niveau maître", hint: "Position issue d'une partie de maître.", priority: 5 },
  masterVsMaster: { label: "Maître vs maître", hint: "Tirée d'une partie GM vs GM.", priority: 5 },
  superGM: { label: "Super-GM", hint: "Position de très haut niveau.", priority: 5 },
};

const FALLBACK: ThemeMeta = {
  label: "Tactique",
  hint: "Cherche le meilleur coup objectif. Cible : matériel, mat ou avantage positionnel décisif.",
  priority: 0,
};

export function themeMeta(theme: string): ThemeMeta {
  return META[theme] ?? { ...FALLBACK, label: theme };
}

export function pickPrimaryTheme(themes: string[] | null | undefined): ThemeMeta {
  if (!themes || themes.length === 0) return FALLBACK;
  let best = FALLBACK;
  for (const t of themes) {
    const m = themeMeta(t);
    if (m.priority > best.priority) best = m;
  }
  return best;
}

export function localizedThemes(themes: string[] | null | undefined): string[] {
  if (!themes) return [];
  return themes.map((t) => themeMeta(t).label);
}
