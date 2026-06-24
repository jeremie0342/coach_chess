"use client";

import { useCallback, useRef, useState } from "react";
import { streamPost } from "@/lib/stream";

export function useStreamingExplain() {
  const [text, setText] = useState("");
  const [isStreaming, setStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const ac = useRef<AbortController | null>(null);

  const stop = useCallback(() => {
    ac.current?.abort();
    setStreaming(false);
  }, []);

  const start = useCallback(async (gameId: number, ply: number) => {
    stop();
    setText("");
    setError(null);
    setStreaming(true);
    ac.current = new AbortController();
    await streamPost(
      `/coach/games/${gameId}/explain_move/stream`,
      { ply },
      {
        signal: ac.current.signal,
        onChunk: (chunk) => setText((prev) => prev + chunk),
        onDone: () => setStreaming(false),
        onError: (e) => {
          setStreaming(false);
          if ((e as Error)?.name !== "AbortError") {
            setError(String(e));
          }
        },
      },
    );
  }, [stop]);

  const reset = useCallback(() => {
    stop();
    setText("");
    setError(null);
  }, [stop]);

  return { text, isStreaming, error, start, stop, reset };
}
