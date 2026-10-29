// GeM relay: forwards one HTTPS request to *.gem.gov.in from Mumbai (Vercel region bom1).
// GeM refuses connections from non-Indian IPs; Green Ink's backend runs outside India.
// Locked down: shared secret, HTTPS to gem.gov.in hosts only, no other destinations.
import { timingSafeEqual } from "node:crypto";

const ALLOWED_HOST = /^(?:[a-z0-9-]+\.)*gem\.gov\.in$/i;
const FORWARD = ["cookie", "content-type", "user-agent", "x-requested-with", "referer", "accept"];

function authorised(sent) {
  const key = process.env.RELAY_KEY ?? "";
  if (!key || typeof sent !== "string") return false;
  const a = Buffer.from(sent);
  const b = Buffer.from(key);
  return a.length === b.length && timingSafeEqual(a, b);
}

async function readBody(req) {
  const chunks = [];
  for await (const chunk of req) chunks.push(chunk);
  return Buffer.concat(chunks);
}

export default async function handler(req, res) {
  if (!authorised(req.headers["x-relay-key"])) {
    res.statusCode = 401;
    return res.end("unauthorised");
  }
  let target;
  try {
    target = new URL(String(req.headers["x-target-url"] ?? ""));
  } catch {
    res.statusCode = 400;
    return res.end("bad target");
  }
  if (target.protocol !== "https:" || !ALLOWED_HOST.test(target.hostname)) {
    res.statusCode = 403;
    return res.end("target not allowed");
  }

  const headers = {};
  for (const name of FORWARD) if (req.headers[name]) headers[name] = req.headers[name];
  const body = ["GET", "HEAD"].includes(req.method) ? undefined : await readBody(req);

  let upstream;
  try {
    upstream = await fetch(target, { method: req.method, headers, body, redirect: "manual" });
  } catch (error) {
    res.statusCode = 502;
    return res.end(`upstream error: ${error?.cause?.code ?? error?.message ?? "unknown"}`);
  }
  res.statusCode = upstream.status;
  for (const name of ["content-type", "location", "content-disposition"]) {
    const value = upstream.headers.get(name);
    if (value) res.setHeader(name, value);
  }
  const cookies = upstream.headers.getSetCookie();
  if (cookies.length) res.setHeader("set-cookie", cookies);
  res.end(Buffer.from(await upstream.arrayBuffer()));
}
