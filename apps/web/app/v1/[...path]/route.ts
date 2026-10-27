// Same-origin proxy to the API. The browser only talks to this app, so the session cookie is
// first-party and the PDF viewer needs no CORS. Bodies stream both ways, so SSE works.
import type { NextRequest } from "next/server";

export const dynamic = "force-dynamic";

const API_URL = (process.env.API_URL ?? "http://localhost:8000").replace(/\/$/, "");
const FORWARD_REQUEST = ["cookie", "content-type", "last-event-id", "accept", "user-agent"];
const DROP_RESPONSE = new Set(["content-encoding", "content-length", "transfer-encoding", "connection"]);

async function proxy(request: NextRequest): Promise<Response> {
  const url = new URL(request.url);
  const target = `${API_URL}${url.pathname}${url.search}`;
  const headers = new Headers();
  for (const name of FORWARD_REQUEST) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  const forwardedFor = request.headers.get("x-forwarded-for");
  if (forwardedFor) headers.set("x-forwarded-for", forwardedFor);

  const hasBody = !["GET", "HEAD"].includes(request.method);
  let upstream: Response;
  try {
    upstream = await fetch(target, {
      method: request.method,
      headers,
      body: hasBody ? request.body : undefined,
      // Required by Node's fetch to stream a request body.
      ...(hasBody ? { duplex: "half" } : {}),
      cache: "no-store",
      redirect: "manual",
      signal: request.signal,
    } as RequestInit);
  } catch {
    return Response.json(
      { code: "upstream_unavailable", message: "The Green Ink service is not reachable. Try again shortly.", retryable: true },
      { status: 502 },
    );
  }
  const responseHeaders = new Headers();
  upstream.headers.forEach((value, name) => {
    if (!DROP_RESPONSE.has(name.toLowerCase()) && name.toLowerCase() !== "set-cookie") {
      responseHeaders.set(name, value);
    }
  });
  for (const cookie of upstream.headers.getSetCookie()) responseHeaders.append("set-cookie", cookie);
  if (responseHeaders.get("content-type")?.startsWith("text/event-stream")) {
    responseHeaders.set("cache-control", "no-cache, no-transform");
    responseHeaders.set("x-accel-buffering", "no");
  }
  return new Response(upstream.body, { status: upstream.status, headers: responseHeaders });
}

export const GET = proxy;
export const POST = proxy;
