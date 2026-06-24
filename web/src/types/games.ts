export type GameRow = {
  id: number;
  url: string | null;
  played_at: string | null;
  color: "white" | "black";
  result: "win" | "loss" | "draw" | "unknown";
  my_rating: number | null;
  opp_rating: number | null;
  opp_username: string | null;
  opening: string | null;
  eco: string | null;
  time_class: string | null;
  ply_count: number;
  analysis_status: string;
  my_out_of_book_ply: number | null;
};

export type GamesListResponse = { total: number; items: GameRow[] };

export type MoveRow = {
  ply: number;
  san: string;
  uci: string;
  fen_before: string;
  fen_after: string;
  side: "white" | "black";
  eval_cp: number | null;
  eval_mate: number | null;
  eval_cp_before: number | null;
  eval_mate_before: number | null;
  best_uci: string | null;
  best_san: string | null;
  cp_loss: number | null;
  quality: string | null;
  tags: string[] | null;
  pv: string[] | null;
};

export type GameDetail = {
  id: number;
  url: string | null;
  pgn: string;
  initial_fen: string | null;
  played_at: string | null;
  color: "white" | "black";
  result: "win" | "loss" | "draw" | "unknown";
  my_rating: number | null;
  opp_rating: number | null;
  opp_username: string | null;
  opening: string | null;
  eco: string | null;
  time_class: string | null;
  ply_count: number;
  analysis_status: string;
  my_out_of_book_ply: number | null;
  moves: MoveRow[];
};

export type GameReview = {
  summary: string;
  highlights: { ply: number; san: string; comment: string; quality?: string }[];
  themes: string[];
  next_steps: string[];
};
