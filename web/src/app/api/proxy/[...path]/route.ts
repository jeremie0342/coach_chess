import { NextRequest, NextResponse } from "next/server";

const BASE = process.env.COACH_API_BASE ?? "http://127.0.0.1:8000";
const KEY = process.env.COACH_API_KEY ?? "";

export const dynamic = "force-dynamic";

async function forward(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  const { path } = await ctx.params;
  const search = req.nextUrl.search ?? "";
  const url = `${BASE}/api/v1/${path.join("/")}${search}`;

  const headers = new Headers(req.headers);
  headers.set("X-API-Key", KEY);
  headers.delete("host");
  headers.delete("content-length");

  const init: RequestInit = {
    method: req.method,
    headers,
    cache: "no-store",
  };
  if (!["GET", "HEAD"].includes(req.method)) {
    init.body = await req.arrayBuffer();
  }

  let upstream: Response;
  try {
    upstream = await fetch(url, init);
  } catch (e) {
    return NextResponse.json(
      { error: "backend_unreachable", detail: String(e), url },
      { status: 502 }
    );
  }

  const respHeaders = new Headers(upstream.headers);
  respHeaders.delete("content-encoding");
  respHeaders.delete("content-length");
  respHeaders.delete("transfer-encoding");

  return new NextResponse(upstream.body, {
    status: upstream.status,
    headers: respHeaders,
  });
}

export {
  forward as GET,
  forward as POST,
  forward as PUT,
  forward as PATCH,
  forward as DELETE,
};
