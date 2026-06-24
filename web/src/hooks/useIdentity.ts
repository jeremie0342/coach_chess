"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

export type Identity = {
  chesscom_username: string;
  lichess_username: string | null;
  display_name: string;
};

const FALLBACK: Identity = {
  chesscom_username: "coach",
  lichess_username: null,
  display_name: "coach",
};

/** Reads the configured coach owner from the backend (.env-driven).
 *  Used to replace hardcoded usernames in the UI shell. */
export function useIdentity(): Identity {
  const q = useQuery<Identity>({
    queryKey: ["identity"],
    queryFn: () => api<Identity>("/identity"),
    staleTime: 5 * 60_000,
  });
  return q.data ?? FALLBACK;
}
