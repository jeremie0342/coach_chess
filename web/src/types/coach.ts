export type RecommendedElo = {
  next_elo: number;
  last_elo: number | null;
  sessions_used: number;
  recent_score: number | null;
  win_streak: number;
  loss_streak: number;
  reason: string;
};

export type Personality = {
  player: string;
  moves_used: number;
  style: {
    aggression: number;
    tactical_eye: number;
    positional: number;
    endgame_skill: number;
    time_management: number;
  };
  dominant_trait: string;
  closest_gm: string;
  closest_gm_similarity: number;
  all_gm_matches: { gm: string; similarity: number }[];
  notes: string | null;
};

export type ContextualPatterns = {
  baseline_blunder_rate: number;
  total_moves: number;
  insights: {
    metric: string;
    bucket: string;
    blunder_rate: number;
    sample_moves: number;
    relative_to_baseline: number;
    comment: string;
  }[];
};

export type EloCalibration = {
  player: string;
  total_games: number;
  estimated_elo: number | null;
  confidence: string;
  reason: string;
  buckets: {
    sf_elo: number;
    games: number;
    wins: number;
    draws: number;
    losses: number;
    score: number;
  }[];
};

export type OpeningRecommendations = {
  recommendations: {
    name: string;
    eco: string | null;
    color: "white" | "black";
    role: string;
    fit_score: number;
    short_pitch: string;
    rationale: string;
  }[];
};
