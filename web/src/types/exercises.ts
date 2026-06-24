export type Exercise = {
  id: number;
  title: string;
  fen: string;                    // effective FEN (after trigger)
  raw_fen?: string;               // unchanged Lichess FEN (debug)
  user_color: "white" | "black";
  total_user_steps: number;
  side_to_move: "w" | "b";
  kind: string;
  difficulty: number | null;
  themes: string[] | null;
  source_game_id: number | null;
};

export type NextExerciseResponse =
  | { has_exercise: false }
  | { has_exercise: true; is_new: boolean; due_now: boolean; exercise: Exercise };

export type AnswerResponse = {
  exercise_id: number;
  correct: boolean;
  complete: boolean;
  grade: number;
  step: number;
  user_uci: string | null;
  expected_uci: string;
  expected_san: string;
  opponent_uci: string | null;
  opponent_san: string | null;
  fen_after_opponent: string | null;
  next_expected_uci: string | null;
  next_expected_san: string | null;
  new_interval_days: number;
  new_due_at: string;
};

export type ExerciseStats = {
  total: number;
  new: number;
  learning: number;
  due_today: number;
  next_due_at: string | null;
};
