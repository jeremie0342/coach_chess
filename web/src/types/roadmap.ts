export type RoadmapPhaseItem = {
  kind: string;
  title: string;
  target_count: number;
  minutes: number;
  rationale: string;
};

export type RoadmapPhase = {
  letter: "A" | "B" | "C" | "D" | "E";
  label: string;
  floor: number;
  ceiling: number;
  state: "done" | "current" | "upcoming";
  items: RoadmapPhaseItem[];
};

export type Roadmap = {
  goal_rating: number;
  current_rating: number | null;
  current_phase: string;
  rapid_30d_ago: number | null;
  rating_delta_30d: number | null;
  next_milestone: number;
  progress_in_phase: number | null;
  eta_days_to_next_milestone: number | null;
  phases: RoadmapPhase[];
  thresholds: { rating: number; next_phase: string }[];
};
