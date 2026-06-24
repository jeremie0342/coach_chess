export type RepertoireNode = {
  id: number;
  color: string;
  fen: string;
  label: string | null;
  notes: string | null;
  plan: string | null;
  traps: { name?: string; line?: string; comment?: string }[] | null;
  gm_total_games: number | null;
  gm_my_move_score: number | null;
  gm_my_move_share: number | null;
  gm_moves: { san?: string; uci?: string; games?: number; score_white?: number }[] | null;
  opening_name: string | null;
  eco: string | null;
  sr_repetitions: number;
  sr_interval_days: number;
  sr_ease: number;
};

export type NextCardResponse =
  | { has_card: false }
  | { has_card: true; is_new: boolean; due_now: boolean; node: RepertoireNode };

export type TrainerAnswer = {
  node_id: number;
  correct: boolean;
  grade: number;
  expected_san: string;
  expected_uci: string;
  expected_source: "gm" | "user";
  expected_score: number | null;
  user_uci: string | null;
  alternates: string | null;
  your_usual_san: string | null;
  your_usual_uci: string | null;
  plays_usual: boolean;
  is_best_your_usual: boolean;
  new_interval_days: number;
  new_due_at: string;
};

export type TrainerStats = {
  total_nodes: number;
  new_nodes: number;
  learning_nodes: number;
  due_today: number;
  next_due_at: string | null;
};
