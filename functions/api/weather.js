// Cloudflare Pages Function: /api/weather
// Configure WEATHER_API_KEY as a Cloudflare Pages secret/environment variable.
// The secret is never returned to the browser.

const WEATHER_BASE = "https://api.weather.com/v2/pws";

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
      "Pragma": "no-cache",
      "X-Content-Type-Options": "nosniff",
      "Referrer-Policy": "no-referrer"
    }
  });
}

export async function onRequestGet(context) {
  const { request, env } = context;
  const url = new URL(request.url);

  const apiKey = env.WEATHER_API_KEY;
  if (!apiKey) {
    return json({ error: "WEATHER_API_KEY no está configurada en Cloudflare." }, 500);
  }

  const kind = (url.searchParams.get("kind") || "").toLowerCase();
  const stationId = (url.searchParams.get("stationId") || "").trim().toUpperCase();
  const date = (url.searchParams.get("date") || "").trim();

  if (!/^[A-Z0-9_-]{3,32}$/.test(stationId)) {
    return json({ error: "stationId inválido." }, 400);
  }

  let upstream;
  if (kind === "current") {
    upstream = new URL(`${WEATHER_BASE}/observations/current`);
  } else if (kind === "history") {
    if (!/^\d{8}$/.test(date)) return json({ error: "date debe tener formato YYYYMMDD." }, 400);
    upstream = new URL(`${WEATHER_BASE}/history/all`);
    upstream.searchParams.set("date", date);
  } else {
    return json({ error: "kind debe ser current o history." }, 400);
  }

  upstream.searchParams.set("stationId", stationId);
  upstream.searchParams.set("format", "json");
  upstream.searchParams.set("units", "m");
  upstream.searchParams.set("numericPrecision", "decimal");
  upstream.searchParams.set("apiKey", apiKey);

  try {
    const r = await fetch(upstream.toString(), {
      headers: { "Accept": "application/json" },
      cf: { cacheTtl: 0, cacheEverything: false }
    });

    const body = await r.text();

    if (!r.ok) {
      console.error("Weather upstream", r.status, stationId, kind);
      return json({ error: "No se pudo consultar la estación.", status: r.status }, r.status);
    }

    return new Response(body, {
      status: 200,
      headers: {
        "Content-Type": "application/json; charset=utf-8",
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        "Pragma": "no-cache",
        "X-Content-Type-Options": "nosniff"
      }
    });
  } catch (err) {
    console.error("Weather proxy error", err);
    return json({ error: "Error de comunicación con Weather.com." }, 502);
  }
}
