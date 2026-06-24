export type PlayerHeader = {
  chesscom_username: string;
  games_total: number;
  games_last_30d: number;
  current_rating_rapid: number | null;
  winrate_white: number | null;
  winrate_black: number | null;
};

export type WeaknessSummary = {
  category: string;
  phase: string | null;
  severity: number;
  occurrences: number;
  details: Record<string, unknown> | null;
  sample_game_ids: number[];
};

export type TrainingLoad = {
  repertoire_due: number;
  repertoire_new_available: number;
  exercises_due: number;
  exercises_new_available: number;
};

export type RecentGame = {
  id: number;
  url: string | null;
  played_at: string | null;
  color: "white" | "black";
  result: "win" | "loss" | "draw";
  my_rating: number | null;
  opening: string | null;
  eco: string | null;
  my_out_of_book_ply: number | null;
};

export type DashboardResponse = {
  player: PlayerHeader;
  weaknesses: WeaknessSummary[];
  training: TrainingLoad;
  recent_games: RecentGame[];
};
