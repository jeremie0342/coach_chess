export type OpeningListItem = {
  key: string;
  name: string;
  base_name?: string;
  eco: string | null;
  user_color: "white" | "black";
  summary: string;
  plies: number;
  variant_count?: number;
};

export type OpeningGroup = {
  base_name: string;
  eco: string | null;
  user_color: "white" | "black";
  summary: string;
  variants: { key: string; name: string; eco: string | null; plies: number }[];
};

export type OpeningGroupsResponse = { groups: OpeningGroup[] };

export type OpeningInfo = {
  key: string;
  name: string;
  base_name?: string;
  eco: string | null;
  user_color: "white" | "black";
  summary: string;
  plan: string[];
  /** Label of the variant chosen for this session (mainline OR a branch). */
  variant_label?: string;
};

export type OpeningStart = {
  id: number;
  opening: OpeningInfo;
  current_fen: string;
  expected_user_uci: string | null;
  expected_user_san: string | null;
  coach_hint: string | null;
  ply: number;
  total_plies: number;
};

export type OpeningMoveResp = {
  status: "ok" | "completed" | "illegal" | "wrong_book";
  correct: boolean | null;
  current_fen: string;
  your_san?: string;
  opponent_uci?: string | null;
  opponent_san?: string | null;
  expected_user_uci?: string | null;
  expected_user_san?: string | null;
  coach_hint?: string | null;
  ply?: number;
  total_plies?: number;
  message?: string;
};
