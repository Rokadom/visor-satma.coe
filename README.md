# SATMA — GitHub + Cloudflare Pages (seguro, 5 minutos)

Este paquete NO contiene usuarios, contraseñas, hashes de autenticación ni la API key de Weather.com en archivos públicos.

## Archivos
- `index.html`: visor SATMA. Las estaciones, radar y sismos se refrescan cada 5 minutos.
- `login.html`: formulario público de acceso; no contiene usuarios válidos.
- `functions/_middleware.js`: bloquea el visor y las API si no existe una sesión válida.
- `functions/api/login.js`: verifica usuario/contraseña del lado servidor.
- `functions/api/logout.js`: cierra la sesión.
- `functions/api/session.js`: devuelve solo el usuario de la sesión activa.
- `functions/api/weather.js`: consulta Weather.com usando `WEATHER_API_KEY` desde Cloudflare.
- `functions/_lib/auth.js`: PBKDF2 + cookie de sesión firmada HMAC.

## Secretos que debes crear en Cloudflare
En **Workers & Pages → tu proyecto → Settings → Variables and Secrets → Add**, crea como secretos cifrados:
1. `SATMA_USERS_JSON` — usa el valor generado en el archivo privado que se entrega por separado.
2. `SATMA_SESSION_SECRET` — usa el valor generado en el archivo privado que se entrega por separado.
3. `WEATHER_API_KEY` — coloca tu API key real de Weather.com.

Cloudflare recomienda almacenar API keys y otros valores sensibles como Secrets, que no pueden verse después de guardarlos y se exponen a las Functions mediante `context.env`.

## Publicación
Sube SOLO el contenido de esta carpeta/ZIP al repositorio GitHub conectado con Cloudflare Pages. No subas el archivo privado de secretos. La carpeta `functions` debe permanecer en la raíz del proyecto.

## Funcionamiento
1. Un visitante que abre `/` sin sesión es redirigido a `/login.html`.
2. El formulario llama `/api/login`.
3. Cloudflare compara la contraseña con PBKDF2 almacenado en `SATMA_USERS_JSON`.
4. Si es correcta, crea una cookie `HttpOnly; Secure; SameSite=Strict` firmada.
5. El middleware permite entonces entregar `index.html` y consultar `/api/weather`.
6. La sesión vence a las 8 horas o al pulsar **Cerrar sesión**.
