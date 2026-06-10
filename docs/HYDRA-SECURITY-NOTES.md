# Hydra · Notas de seguridad y anti-copia

> Estas notas las escribió **Faro** desde la sesión de Phoenix, tras revisar
> el snapshot `cliente-r42-compilado/`. **Pásaselas tal cual a la sesión
> donde vive Hydra** para que las aplique allí. Aquí no tocamos el código
> de Hydra (no está en este repo).

## Modelo de amenaza
Hydra **regula semáforos**: un fallo no es un dashboard caído, es un
**accidente de tráfico**. Hay que asumir varios atacantes posibles:

1. **Insider en la red municipal** (ayuntamiento). Hoy puede llegar al
   `0.0.0.0:3001` de Hydra sin ningún token.
2. **Atacante con llave del nodo de fibra en calle**: abre el armario,
   se plug a un puerto del switch y aparece en la misma LAN. *No
   necesita pisar el ayuntamiento.*
3. **Atacante que solo alcance el módulo Modbus** (`192.168.1.44:502`):
   Modbus TCP **no tiene autenticación ni cifrado**. Si lo alcanza,
   manda comandos directos **saltándose Hydra entero** (matriz de
   conflictos incluida — la matriz vive en Hydra, no en el módulo).
4. **Cliente que recibe la release**: puede copiar / desplegar Hydra
   en otra ciudad sin pagar.

Trabajamos con **defensa en profundidad** (IEC 62443): perímetro,
red, host, aplicación, datos. Que caiga una capa no debe tumbar el sistema.

---

## 1) Auth server-side — el agujero nº 1

**Diagnóstico** (verificado en `backend/server.js` R42, ~443 líneas):
- El backend **no tiene ningún middleware de autenticación**.
- El propio `README.md` del backend invita a usar la API sin token:
  ```bash
  curl -X POST http://localhost:3001/api/test-relay/1
  ```
- El frontend compilado SÍ tiene login/PIN/registro (`pin` ×56,
  `password` ×26, `sesión` ×21 en el bundle), pero **es solo de fachada
  en el navegador**. Un `curl` se la salta.
- WebSocket `/ws` tampoco pide token al conectar.

**No basta con añadir patrón y 2FA al frontend.** Si el backend sigue
abierto, el atacante ni siquiera abre el navegador.

**Plan (en el backend):**

1. **JWT en cada `/api/*` y en `/ws`** (validar al conectar el WS, no
   solo al abrir HTTP).
2. **Hash de credenciales en disco** (PBKDF2 mín. 200k rondas o, mejor,
   **Argon2id**). Nunca contraseñas en claro.
3. Login con los **4 factores** (igual que Phoenix):
   contraseña + PIN + patrón + TOTP (Google Authenticator).
4. **Bloqueo por intentos fallidos** + auditoría de cada intento.
5. **Rotar el token** en cada elevación de privilegio (p. ej. salir de
   modo *solo monitor*).
6. **No usar `localStorage` para el JWT** — cookie `HttpOnly`,
   `Secure`, `SameSite=Strict` (clave si vais a HTTPS).

> Si Hydra reutiliza la pila de auth de Phoenix (Python), una opción
> realista es **un microservicio de auth común** que ambos llamen.
> Mientras tanto, **copia la lógica** (PBKDF2 + JWT HS256 con `exp`
> corto + lockout) en Node.

---

## 2) Bind a la interfaz correcta — no `0.0.0.0`

Hoy: `config-default.json` → `"server": {"port": 3001, "host": "0.0.0.0"}`.
Eso publica el panel en **todas** las interfaces del PC del regulador.

**Recomendado**:
- Si frontend y backend van en el **mismo regulador**, bind a `127.0.0.1`
  y servir el frontend por el mismo proceso (ya lo hace con
  `express.static`). Nadie de fuera lo ve.
- Si necesitas acceso remoto, **detrás de un reverse proxy con TLS**
  (nginx/Caddy) y firewall que solo deje la IP del operador
  (allowlist).

---

## 3) Segmentación de red — bloquea el "llave del nodo"

Hoy todo cuelga de "la misma LAN" entre nodo, ayuntamiento y módulo
Modbus. **Eso es el peor sitio para un regulador de tráfico.**

**Mínimo recomendado** (lo que pide IEC 62443 / ISA-95):

| Zona | Qué va dentro | Qué puede entrar |
|---|---|---|
| **OT — Modbus** | Módulos Waveshare `192.168.1.44:502` | **Solo** la IP del backend de Hydra. Nada más. |
| **OT — Hydra** | El servidor Node de Hydra | Panel de operadores (allowlist) + salud |
| **Ofimática del ayto** | PCs de oficina | Nada de OT |

**Cómo se materializa**:
- **VLANs separadas** por zona en los switches; **firewall L3** entre
  zonas con reglas por defecto `deny`.
- **802.1X** o **port security** en el switch del nodo de fibra:
  si alguien con llave plug un cable a un puerto suelto, el switch no
  le pasa tráfico hasta que el equipo se autentique con certificado.
  Esto **mata el ataque de "llave del nodo"** en el punto exacto.
- **MAC sticky** como fallback si 802.1X aún no se puede.
- **VPN site-to-site con IPsec** entre nodos de calle y ayuntamiento
  (no LAN plana extendida). Así el "ovillo" no se desenrolla con un
  cable.
- **Cifrado del tráfico también dentro de la LAN**: HTTPS para la API
  y `wss://` para el WebSocket (TLS, no http).

> Modbus TCP **no se puede autenticar** por diseño. La defensa es
> aislarlo: que solo Hydra le hable y nadie más llegue al `:502`.
> Si en un futuro pasáis a **Modbus Secure (RFC 8359)** o
> tuneláis Modbus por IPsec, mejor; mientras tanto, segmentación dura.

---

## 4) Validar la matriz de conflictos también en `/api/relay/:n`

Hoy: en `server.js`, `handleTick` (WebSocket) **sí** valida con
`conflictMatrix.validate(...)` antes de mover relés. Pero
`POST /api/relay/:n` **no la valida**, va directo a `driver.setRelay`.

Un cliente legítimo (que conoce la API) podría encender dos verdes
incompatibles **sin que la matriz lo bloquee**. La protección física
solo está en uno de los dos caminos.

**Fix**: que `setRelay`/`flashRelay` pasen por el mismo `validate` que
el `tick`. Si conflicto → 400 + audit + opcionalmente all-off.

---

## 5) Licencia firmada + activación (anti-copia)

Hoy Hydra no tiene licenciamiento. Quien recibe la release puede:
- desplegarla en otra ciudad sin pagar;
- modificar `audit-log.js` para dejar de auditar;
- distribuirla.

**Plan híbrido (recomendado)**:

1. Genera **Ed25519** (clave privada tuya / pública en el cliente).
2. Firma una **licencia por instalación**:
   ```json
   {
     "cliente": "Ayuntamiento de X",
     "fp": "<huella del equipo: hostname + MAC + ¿serial módulo Modbus?>",
     "iat": 1717000000,
     "exp": 1748000000,
     "features": ["regulador-30ch"],
     "max_modulos": 1
   }
   ```
3. El backend verifica al arrancar con la **clave pública**. Si firma o
   huella no cuadran → modo **solo lectura** + banner rojo. No "se cierra
   bonito", se degrada a inútil para el atacante pero auditando.
4. **Renovación periódica online** (opcional, requiere internet): pega
   a tu servidor cada N días y refresca la licencia. Si el ayto pierde
   internet, sigue funcionando hasta `exp`.

> **No uses HMAC** para licencias comerciales si Hydra va instalado
> en el cliente: el secreto viajaría en el binario y se puede extraer.
> Ed25519 mantiene el secreto SOLO en tu lado.

> En Phoenix ya tenemos el esqueleto en `licensing.py` (con HMAC, marcado
> como "migrar a Ed25519"). Conviene **el mismo esquema en los dos**.

---

## 6) Hardening del proceso (host)

- **Usuario sin privilegios** dedicado para correr Node (no `root`, no
  `Administrador`).
- **systemd** (Linux) o **Service** (Windows) con auto-restart **y**
  watchdog. Si Node cae, los relés se apagan solos (lo hace
  `installShutdownHandlers`).
- **Logs rotados** (`logrotate`) — `audit-YYYY-MM-DD.jsonl` crece sin
  control hoy.
- **Permisos del fichero de licencia + `audit/`**: `chmod 600` para que
  el atacante local no los lea/edite. Idealmente, **firma de la cadena
  de auditoría** (cada línea con hash de la anterior — append-only de
  verdad).
- **NTP confiable**: si el reloj se desincroniza, `exp` de licencia y
  TOTP fallan en silencio. Forzar `chrony`/`w32time` contra un servidor
  conocido.

---

## 7) Otros vectores menores pero reales

- **Token en URL del WebSocket** (si lo añades). NO lo mandes por
  query string — los proxies y logs lo capturan. Usa `Authorization`
  en el handshake o cookie.
- **`localStorage` para el token**: cualquier XSS = robo del JWT.
  Revisa que el frontend compilado **no inyecta HTML dinámico** de
  fuentes no fiables (auditoría, mensajes Modbus, etc.).
- **CSP estricta** en el `index.html` del frontend: `default-src 'self'`,
  sin `unsafe-inline`. Esto mitiga XSS muy fuerte.
- **Cabeceras HTTP**: `X-Content-Type-Options: nosniff`,
  `Referrer-Policy: no-referrer`, `Permissions-Policy: ()`.
- **Limit de tasa** en `/api/*` (`express-rate-limit`) — defensa contra
  fuerza bruta de login.
- **No incluir mapas fuente** (`.map`) en el build de producción.
  Comprueba que el bundle de Vite va sin sourcemaps. Por lo que vi en
  R42, **ya está**: `index-DKdou2Jy.js` sin `.map` al lado. ✅

---

## 8) Anti-ingeniería inversa — la verdad sin humo

Hydra es **Node.js**. Ningún truco te lo va a hacer "imposible de
descompilar":
- El **frontend minificado** que tiene Hydra (build Vite) es un bache,
  no un muro. Cualquiera con `js-beautify` lo lee.
- **`pkg`/`nexe`** empaquetan Node en un binario, pero las cadenas
  siguen ahí.
- Lo único que **de verdad** protege la propiedad intelectual es:
  1. **Empaquetado limpio** (no entregues `.git`, tests internos,
     comentarios de diseño). En Hydra R42 esto ya está. ✅
  2. **Lógica de valor en TU servidor** (modelo híbrido / SaaS).
     Lo que no entregas, no se copia. ← *protección real*.
  3. **Licencia firmada + activación** (sección 5).
  4. **Legal**: registrar autoría (Registro de Propiedad Intelectual /
     Safe Creative) + `LICENSE`/EULA. Es la palanca que usas en
     juicio.

> Conclusión honesta: no harás Hydra "no copiable". Lo haces **no
> rentable de copiar, legalmente perseguible e inútil sin tu
> licencia/servidor**. Ese es el objetivo realista.

---

## Checklist priorizada (para la otra sesión)

🔴 **Hacer ya — agujeros reales**:
- [ ] Auth server-side en todos los `/api/*` y `/ws` (JWT + lockout).
- [ ] Validar matriz de conflictos también en `/api/relay/:n`.
- [ ] Bind a `127.0.0.1` (o detrás de proxy con allowlist), no `0.0.0.0`.
- [ ] HTTPS + WSS (TLS) — con certificado propio si es OT cerrada.

🟠 **Antes de entregar a cliente**:
- [ ] Licencia firmada Ed25519 + huella del equipo.
- [ ] Logs rotados, permisos `600` sobre licencia y auditoría.
- [ ] CSP + cabeceras de seguridad en el HTML del frontend.
- [ ] LICENSE/EULA + registrar autoría (RPI / Safe Creative).

🟡 **Infra (lo coordinas con el ayuntamiento)**:
- [ ] VLANs separadas: OT-Modbus, OT-Hydra, ofimática.
- [ ] Firewall L3 con `deny` por defecto entre zonas.
- [ ] 802.1X o port security en el switch del nodo de calle.
- [ ] VPN site-to-site IPsec entre nodos y ayuntamiento.

🟢 **Hardening continuo**:
- [ ] NTP fiable, usuario sin privilegios para el proceso.
- [ ] Cadena de auditoría hash-encadenada.
- [ ] Renovación online de licencia.
