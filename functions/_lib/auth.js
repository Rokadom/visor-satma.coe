const COOKIE_NAME = "satma_session";
const SESSION_SECONDS = 8 * 60 * 60;
const PBKDF2_DEFAULT_ITERATIONS = 150000;

const enc = new TextEncoder();

function b64url(bytes) {
  let bin = "";
  for (const b of bytes) bin += String.fromCharCode(b);
  return btoa(bin).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

function fromB64url(s) {
  s = s.replace(/-/g, "+").replace(/_/g, "/");
  while (s.length % 4) s += "=";
  const bin = atob(s);
  return Uint8Array.from(bin, c => c.charCodeAt(0));
}

function constantTimeEqual(a, b) {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a[i] ^ b[i];
  return diff === 0;
}

function getCookie(request, name) {
  const raw = request.headers.get("Cookie") || "";
  for (const part of raw.split(";")) {
    const i = part.indexOf("=");
    if (i < 0) continue;
    if (part.slice(0, i).trim() === name) return part.slice(i + 1).trim();
  }
  return null;
}

async function hmac(secret, text) {
  const key = await crypto.subtle.importKey("raw", enc.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign", "verify"]);
  return new Uint8Array(await crypto.subtle.sign("HMAC", key, enc.encode(text)));
}

export async function createSessionCookie(username, secret) {
  if (!secret) throw new Error("SATMA_SESSION_SECRET no configurado");
  const payload = b64url(enc.encode(JSON.stringify({ u: username, exp: Math.floor(Date.now()/1000) + SESSION_SECONDS })));
  const sig = b64url(await hmac(secret, payload));
  return `${COOKIE_NAME}=${payload}.${sig}; Path=/; Max-Age=${SESSION_SECONDS}; HttpOnly; Secure; SameSite=Strict`;
}

export function clearSessionCookie() {
  return `${COOKIE_NAME}=; Path=/; Max-Age=0; HttpOnly; Secure; SameSite=Strict`;
}

export async function verifySession(request, secret) {
  if (!secret) return null;
  const token = getCookie(request, COOKIE_NAME);
  if (!token) return null;
  const [payload, sig] = token.split(".");
  if (!payload || !sig) return null;
  try {
    const expected = await hmac(secret, payload);
    const received = fromB64url(sig);
    if (!constantTimeEqual(expected, received)) return null;
    const data = JSON.parse(new TextDecoder().decode(fromB64url(payload)));
    if (!data.u || !data.exp || data.exp < Math.floor(Date.now()/1000)) return null;
    return { username: String(data.u), exp: data.exp };
  } catch (_) { return null; }
}

export async function verifyPassword(password, record) {
  if (!record || !record.salt || !record.hash) return false;
  const iterations = Number(record.iterations || PBKDF2_DEFAULT_ITERATIONS);
  if (!Number.isFinite(iterations) || iterations < 50000 || iterations > 1000000) return false;
  try {
    const baseKey = await crypto.subtle.importKey("raw", enc.encode(password), "PBKDF2", false, ["deriveBits"]);
    const bits = new Uint8Array(await crypto.subtle.deriveBits({ name:"PBKDF2", hash:"SHA-256", salt: fromB64url(record.salt), iterations }, baseKey, 256));
    return constantTimeEqual(bits, fromB64url(record.hash));
  } catch (_) { return false; }
}
