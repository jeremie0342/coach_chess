export type PlayMove = {
  ply: number;
  is_user: boolean;
  san: string;
  uci: string;
  fen_after?: string;
  eval_cp?: number | null;
  eval_mate?: number | null;
};

export type PlaySession = {
  id: number;
  title: string | null;
  user_color: "white" | "black";
  starting_fen: string;
  current_fen: string;
  status: string;
  result_reason: string | null;
  ply: number;
  sf_skill_level: number | null;
  sf_elo: number | null;
  max_undos: number;
  undos_used: number;
  undos_remaining: number;
  source: string | null;
  source_ref: Record<string, unknown> | null;
  opening_key?: string | null;
  opening_branch_label?: string | null;
  opening_status?: "in_book" | "completed" | null;
  opening_ply_index?: number;
  opening_total_plies?: number;
  expected_opening_san?: string | null;
  expected_opening_uci?: string | null;
  moves: PlayMove[];
};

export type ConstrainedOpening = {
  key: string;
  name: string;
  base_name: string;
  eco: string;
  user_color: "white" | "black";
  summary: string;
  plies: number;
  branch_count: number;
  branches: string[];
};

export type UndoResponse = {
  accepted: boolean;
  error: string | null;
  current_fen: string;
  undos_used: number;
  undos_remaining: number;
  plies_popped: number;
  moves: { ply: number; is_user: boolean; san: string; uci: string }[];
};

export type MoveResponse = {
  accepted: boolean;
  error: string | null;
  user_uci: string | null;
  user_san: string | null;
  engine_uci: string | null;
  engine_san: string | null;
  current_fen: string;
  status: string;
  eval_cp: number | null;
  eval_mate: number | null;
  user_quality: string | null;
  user_cp_loss: number | null;
  best_user_san: string | null;
  best_user_uci: string | null;
  opening_status?: "in_book" | "completed" | null;
  opening_ply_index?: number;
  opening_total_plies?: number;
  undos_used?: number;
  undos_remaining?: number;
  result_reason?: string | null;
  moves: { ply: number; is_user: boolean; san: string; uci: string }[];
};

export type StartPlayIn = {
  fen: string;
  user_color: "white" | "black";
  skill_level: number;
  sf_elo?: number | null;
  depth?: number;
  title?: string | null;
  source?: string | null;
  source_ref?: Record<string, unknown> | null;
  max_undos?: number;
  opening_key?: string | null;
};
