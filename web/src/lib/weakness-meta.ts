/**
 * Human-readable explanations for each weakness category emitted by the
 * backend detectors. Keeps explanations short but actionable. Each entry
 * exposes a "fix" with a deep-link to the page that actually helps.
 */

export type WeaknessMeta = {
  /** Human label in French */
  label: string;
  /** One-sentence definition */
  what: string;
  /** Why it costs you ELO */
  why: string;
  /** Concrete action to improve, with a deep link */
  fix: { label: string; href: string };
};

const PUZZLES_BY_THEME = (theme: string) =>
  `/puzzles?theme=${encodeURIComponent(theme)}&rating=464&rating_window=300`;

const FALLBACK: WeaknessMeta = {
  label: "Pattern à corriger",
  what: "Pattern récurrent détecté dans tes parties.",
  why: "Représente une perte régulière de centipawns ou de parties.",
  fix: { label: "Faire des puzzles", href: "/puzzles" },
};

const META: Record<string, WeaknessMeta> = {
  hanging_piece: {
    label: "Pièce en prise",
    what: "Tu laisses une pièce sans défense, ton adversaire la capture gratuitement.",
    why:
      "C'est la cause #1 des défaites < 1200 ELO. Une seule pièce en prise = " +
      "matériel perdu sans compensation, partie quasi perdue.",
    fix: { label: "Drill 'hanging piece'", href: PUZZLES_BY_THEME("hangingPiece") },
  },
  missed_tactic: {
    label: "Tactique ratée",
    what: "Stockfish voyait un coup gagnant que tu n'as pas joué.",
    why:
      "Chaque tactique ratée = coup gagnant laissé sur la table. Plus tu " +
      "rates de petites tactiques, plus tu joues passif sans le voir.",
    fix: { label: "Drill tactiques mixtes", href: "/puzzles?rating=464&rating_window=300" },
  },
  // --- Forks ---
  allowed_fork: {
    label: "Fourchette autorisée",
    what: "Ton adversaire a joué une fourchette (1 pièce qui attaque 2 cibles) que tu n'as pas anticipée.",
    why:
      "Une fourchette de cavalier ou de dame = matériel perdu d'office. " +
      "Souvent évitable d'un coup de prophylaxie.",
    fix: { label: "Drill anti-fork", href: PUZZLES_BY_THEME("fork") },
  },
  missed_fork: {
    label: "Fourchette manquée",
    what: "Tu avais l'opportunité de fourcher et tu ne l'as pas vue.",
    why: "Gagner matériel gratuitement en un coup — la base.",
    fix: { label: "Drill fork", href: PUZZLES_BY_THEME("fork") },
  },
  // --- Pins ---
  allowed_pin: {
    label: "Clouage autorisé",
    what: "Adversaire cloue une de tes pièces, tu ne peux plus la bouger sans perdre la pièce de derrière.",
    why: "Une pièce clouée est paralysée — souvent en route vers la perte de matériel.",
    fix: { label: "Drill anti-pin", href: PUZZLES_BY_THEME("pin") },
  },
  missed_pin: {
    label: "Clouage manqué",
    what: "Tu pouvais clouer une pièce adverse et tu ne l'as pas joué.",
    why: "Le pin paralyse une pièce, prépare une attaque, gagne du temps.",
    fix: { label: "Drill pin", href: PUZZLES_BY_THEME("pin") },
  },
  // --- Skewers ---
  allowed_skewer: {
    label: "Enfilade autorisée",
    what: "Adversaire enfile deux de tes pièces sur la même ligne — la 1ère doit bouger et la 2ème tombe.",
    why: "Comme un pin inversé : la pièce devant est plus précieuse et fuit, laissant la pièce de derrière.",
    fix: { label: "Drill anti-enfilade", href: PUZZLES_BY_THEME("skewer") },
  },
  missed_skewer: {
    label: "Enfilade manquée",
    what: "Tu pouvais enfiler deux pièces adverses, tu ne l'as pas vu.",
    why: "Gain de matériel net, similaire à un fork mais sur une ligne.",
    fix: { label: "Drill skewer", href: PUZZLES_BY_THEME("skewer") },
  },
  // --- Discovered attacks ---
  allowed_discovered_attack: {
    label: "Attaque à la découverte subie",
    what: "Adversaire déplace une pièce qui démasque l'attaque d'une autre — double menace.",
    why: "Souvent gagne une pièce, parfois la dame ou le roi en échec double.",
    fix: { label: "Drill anti-découverte", href: PUZZLES_BY_THEME("discoveredAttack") },
  },
  missed_discovered_attack: {
    label: "Attaque à la découverte manquée",
    what: "Tu avais le bon coup à découverte et tu ne l'as pas joué.",
    why: "Tactique très visuelle quand on la cherche — facile à drill.",
    fix: { label: "Drill découverte", href: PUZZLES_BY_THEME("discoveredAttack") },
  },
  // --- Trapped piece ---
  trapped_piece: {
    label: "Pièce piégée",
    what: "Une de tes pièces s'est aventurée et ne peut plus reculer sans perdre matériel.",
    why:
      "Souvent un fou ou un cavalier mal placé en début de partie. Le " +
      "coût est la pièce entière.",
    fix: { label: "Drill 'trapped piece'", href: PUZZLES_BY_THEME("trappedPiece") },
  },
  // --- Mate misses ---
  missed_mate_in_1: {
    label: "Mat en 1 manqué",
    what: "Tu avais un mat en 1 coup et tu as joué autre chose.",
    why: "Ça arrive même aux GMs en blitz — mais en partie longue c'est inexcusable.",
    fix: { label: "Drill mate-in-1", href: PUZZLES_BY_THEME("mateIn1") },
  },
  missed_mate_in_2: {
    label: "Mat en 2 manqué",
    what: "Un mat forcé en 2 coups était possible.",
    why: "Le calcul de 2 demi-coups est le minimum vital.",
    fix: { label: "Drill mate-in-2", href: PUZZLES_BY_THEME("mateIn2") },
  },
  missed_mate_in_3: {
    label: "Mat en 3 manqué",
    what: "Tu avais une séquence forcée de mat en 3 coups.",
    why: "Le calcul forcé en 3 = compétence clé à 1000+. À drill activement.",
    fix: { label: "Drill mate-in-3", href: PUZZLES_BY_THEME("mateIn3") },
  },
  missed_back_rank_mate: {
    label: "Mat du couloir manqué",
    what: "Le mat sur la dernière rangée était disponible.",
    why: "Pattern le plus simple et le plus fréquent. Doit être automatique.",
    fix: { label: "Drill back-rank", href: PUZZLES_BY_THEME("backRankMate") },
  },
  // --- Phase blunders ---
  blunder_in_opening: {
    label: "Gaffes en ouverture",
    what: "Tu perds beaucoup de centipawns dans les 10-15 premiers coups.",
    why:
      "Sortie de théorie trop tôt ou principes oubliés (centre / développement / sécurité du roi). " +
      "Tu démarres déjà perdant avant le milieu de partie.",
    fix: { label: "Voir mes top-lines", href: "/repertoire-lines" },
  },
  blunder_in_middlegame: {
    label: "Gaffes en milieu de partie",
    what: "Les pires erreurs sont dans la phase de calcul + plans (plis 15-40).",
    why:
      "Le milieu de partie demande des plans concrets et du calcul. Sans repère, on joue " +
      "des coups d'attente et l'adversaire gagne du tempo.",
    fix: { label: "Puzzles middlegame", href: "/puzzles?theme=middlegame" },
  },
  blunder_in_endgame: {
    label: "Gaffes en finale",
    what: "Tu perds des coups en finale alors que la position était techniquement gagnante / nulle.",
    why:
      "Les finales sont les positions les plus calcul-able mais aussi les " +
      "moins révisées. C'est là qu'on perd des parties 'gagnées'.",
    fix: { label: "Drill finales", href: "/puzzles?theme=endgame" },
  },
  early_loss: {
    label: "Défaites précoces",
    what: "Tu perds avant le coup ~20, souvent suite à 1-2 gaffes graves.",
    why:
      "C'est le signe d'un manque de répertoire ou de calcul de base (un piège, " +
      "une miniature). Très rentable à corriger : 20 coups au lieu de 60 = 3× plus d'apprentissage par heure.",
    fix: { label: "Voir mes ouvertures", href: "/repertoire-lines" },
  },
  // --- Strategic ---
  poor_with_iqp: {
    label: "Difficile avec pion d isolé",
    what: "Quand tu as un pion isolé sur dame, ton winrate chute.",
    why:
      "Le pion isolé est dynamique mais demande un plan précis (case e5, " +
      "pression sur d4/d5). Sans plan, il devient une faiblesse permanente.",
    fix: { label: "Étudier le IQP", href: "/repertoire-lines" },
  },
  poor_against_passed_pawn: {
    label: "Faible contre pion passé",
    what: "Quand l'adversaire a un pion passé, tu perds plus souvent que la moyenne.",
    why: "Un pion passé non bloqué = promotion potentielle. Doit être bloqué par une pièce mineure ou éliminé.",
    fix: { label: "Drill finales avec pion passé", href: "/puzzles?theme=endgame" },
  },
  pawn_structure: {
    label: "Structure de pions fragile",
    what: "Tu crées régulièrement des pions faibles (doublés, isolés, arriérés).",
    why: "La structure dicte le plan. Des pions faibles = cibles permanentes pour ton adversaire.",
    fix: { label: "Analyser mes parties", href: "/games" },
  },
  // --- Time / clock ---
  time_trouble: {
    label: "Zeitnot (manque de temps)",
    what: "Tu perds beaucoup de parties quand il te reste < 30s au compteur.",
    why:
      "En zeitnot la qualité des coups s'effondre. Mieux gérer le temps " +
      "(plus de temps en début, moins de coups parfaits) = winrate immédiat.",
    fix: { label: "Jouer en 15+10", href: "/play" },
  },
  // --- Openings ---
  low_winrate_opening: {
    label: "Ouverture peu performante",
    what: "Tu joues souvent une ouverture où ton winrate est <40%.",
    why:
      "Pas la peine d'insister : soit étudie sérieusement, soit change. " +
      "Une mauvaise ouverture sape toute la session.",
    fix: { label: "Top-lines + GM data", href: "/repertoire-lines" },
  },
  weak_against_first_move: {
    label: "Faible contre un coup d'ouverture",
    what: "Contre un coup spécifique des blancs (ex. 1.d4), ton winrate est très bas.",
    why: "Indique qu'il manque une vraie réponse préparée dans ton répertoire noir.",
    fix: { label: "Construire la réponse", href: "/repertoire-lines" },
  },
  color_imbalance: {
    label: "Déséquilibre par couleur",
    what: "Ton winrate avec une couleur est nettement plus bas que l'autre.",
    why: "Identifie quelle moitié de ton répertoire mérite ton attention prioritaire.",
    fix: { label: "Drill cette couleur", href: "/repertoire" },
  },
  // --- Generic catch-all ---
  tactical_theme: {
    label: "Motif tactique récurrent",
    what: "Un motif tactique précis revient trop souvent dans tes erreurs.",
    why: "Mémoriser un motif = supprimer toute une famille d'erreurs.",
    fix: { label: "Drill le motif", href: "/puzzles" },
  },
};

export function weaknessMeta(category: string, details?: Record<string, unknown> | null): WeaknessMeta {
  // Direct hit
  if (META[category]) return META[category];

  // tactical_theme with a known theme in details — dispatch
  if (category === "tactical_theme" && details?.theme && typeof details.theme === "string") {
    const t = details.theme as string;
    return META[t] ?? META.tactical_theme;
  }

  // Mate variations
  if (/^missed_mate_in_(\d+)/.test(category)) {
    const n = category.match(/(\d+)/)![0];
    return META[`missed_mate_in_${n}`] ?? META.missed_mate_in_2;
  }

  return FALLBACK;
}

export function phaseLabelFr(phase: string | null): string {
  if (!phase) return "Toutes phases";
  return {
    opening: "Ouverture",
    middlegame: "Milieu de partie",
    endgame: "Finale",
  }[phase] ?? phase;
}
