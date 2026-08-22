import { verifySession } from "./_lib/auth.js";

const PUBLIC_PATHS = new Set(["/login.html", "/api/login", "/favicon.ico", "/robots.txt"]);

export async function onRequest(context) {
  const { request, env, next } = context;
  const url = new URL(request.url);
  const path = url.pathname;

  if (PUBLIC_PATHS.has(path)) return next();

  const session = await verifySession(request, env.SATMA_SESSION_SECRET);
  if (!session) {
    if (path.startsWith("/api/")) {
      return new Response(JSON.stringify({ error: "Sesión no válida o vencida." }), {
        status: 401,
        headers: { "Content-Type":"application/json; charset=utf-8", "Cache-Control":"no-store" }
      });
    }
    return Response.redirect(new URL("/login.html", url), 302);
  }

  context.data.satmaUser = session.username;
  const response = await next();
  const headers = new Headers(response.headers);
  headers.set("Cache-Control", "private, no-store, no-cache, must-revalidate, max-age=0");
  headers.set("X-Content-Type-Options", "nosniff");
  headers.set("X-Frame-Options", "DENY");
  headers.set("Referrer-Policy", "no-referrer");
  headers.set("Permissions-Policy", "camera=(), microphone=(), geolocation=()");
  return new Response(response.body, { status: response.status, statusText: response.statusText, headers });
}
