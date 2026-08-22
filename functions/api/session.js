export async function onRequestGet(context) {
  return new Response(JSON.stringify({ ok:true, user:context.data.satmaUser || "Usuario" }), { status:200, headers:{ "Content-Type":"application/json; charset=utf-8", "Cache-Control":"no-store" } });
}
