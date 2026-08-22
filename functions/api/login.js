import { createSessionCookie, verifyPassword } from "../_lib/auth.js";

function reply(data, status=200, extra={}) {
  return new Response(JSON.stringify(data), { status, headers: { "Content-Type":"application/json; charset=utf-8", "Cache-Control":"no-store", ...extra } });
}

export async function onRequestPost(context) {
  const { request, env } = context;
  if (!env.SATMA_USERS_JSON || !env.SATMA_SESSION_SECRET) return reply({ error:"Configuración de autenticación incompleta." }, 500);

  let body;
  try { body = await request.json(); } catch (_) { return reply({ error:"Solicitud inválida." }, 400); }
  const username = String(body?.username || "").trim();
  const password = String(body?.password || "");
  if (!username || !password || username.length > 64 || password.length > 256) return reply({ error:"Usuario o contraseña incorrectos." }, 401);

  let users;
  try { users = JSON.parse(env.SATMA_USERS_JSON); } catch (_) { return reply({ error:"Configuración de usuarios inválida." }, 500); }
  const record = users[username];
  const ok = await verifyPassword(password, record);
  // Pequeña demora uniforme para reducir intentos automatizados rápidos.
  await new Promise(r => setTimeout(r, 350));
  if (!ok) return reply({ error:"Usuario o contraseña incorrectos." }, 401);

  const cookie = await createSessionCookie(username, env.SATMA_SESSION_SECRET);
  return reply({ ok:true, user:username }, 200, { "Set-Cookie": cookie });
}
