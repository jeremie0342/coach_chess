const BASE = "/api/proxy";

export class ApiError extends Error {
  constructor(public status: number, public body: unknown) {
    super(`API ${status}`);
  }
}

export async function api<T = unknown>(
  path: string,
  init: RequestInit & { json?: unknown; query?: Record<string, string | number | boolean | undefined> } = {}
): Promise<T> {
  const { json, query, headers, ...rest } = init;

  let url = `${BASE}${path.startsWith("/") ? path : `/${path}`}`;
  if (query) {
    const params = new URLSearchParams();
    for (const [k, v] of Object.entries(query)) {
      if (v !== undefined && v !== null) params.set(k, String(v));
    }
    const qs = params.toString();
    if (qs) url += `?${qs}`;
  }

  const finalHeaders = new Headers(headers);
  if (json !== undefined) {
    finalHeaders.set("Content-Type", "application/json");
    rest.body = JSON.stringify(json);
    rest.method = rest.method ?? "POST";
  }

  const res = await fetch(url, { ...rest, headers: finalHeaders });
  const text = await res.text();
  const data = text ? safeJson(text) : null;
  if (!res.ok) throw new ApiError(res.status, data ?? text);
  return data as T;
}

function safeJson(s: string): unknown {
  try {
    return JSON.parse(s);
  } catch {
    return s;
  }
}
