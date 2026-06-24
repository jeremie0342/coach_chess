export type StreamHandlers = {
  onChunk: (chunk: string) => void;
  onDone?: () => void;
  onError?: (e: unknown) => void;
  signal?: AbortSignal;
};

export async function streamPost(
  path: string,
  query: Record<string, string | number> | undefined,
  handlers: StreamHandlers,
): Promise<void> {
  const url = new URL(`/api/proxy${path.startsWith("/") ? path : `/${path}`}`, window.location.origin);
  if (query) {
    for (const [k, v] of Object.entries(query)) url.searchParams.set(k, String(v));
  }
  try {
    const res = await fetch(url.toString(), { method: "POST", signal: handlers.signal });
    if (!res.ok || !res.body) {
      throw new Error(`HTTP ${res.status}`);
    }
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      const text = decoder.decode(value, { stream: true });
      if (text) handlers.onChunk(text);
    }
    handlers.onDone?.();
  } catch (e) {
    handlers.onError?.(e);
  }
}
