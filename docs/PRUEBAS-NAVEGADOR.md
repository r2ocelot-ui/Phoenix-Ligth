# Phoenix-Light · Pruebas rápidas desde el navegador (F12 → Console)

> Recetas para probar endpoints **sin clicar por la interfaz**, pegándolas en la
> consola del navegador. Útiles para verificar que el backend responde bien.
> (Reconstruido el 14-jun: las líneas originales se dieron en una sesión que se
> resumió y se perdió el texto literal — por eso ahora viven aquí.)

## Cómo abrir la consola
1. Con el panel abierto (`http://localhost:8000/ui/`) y **sesión iniciada**.
2. Pulsa **F12** (o clic derecho → Inspeccionar) → pestaña **Console**.
3. Pega una línea y pulsa Enter.

## Calentamiento (¿la consola funciona?)
```js
2 + 2
```
Debe responder `4`. Solo confirma que la consola está viva.

## El token de sesión
El panel guarda el JWT en `localStorage` bajo la clave **`ph_token`**. Todas las
pruebas lo mandan en la cabecera `Authorization`. Para verlo:
```js
localStorage.getItem('ph_token')
```

## Pruebas de endpoints (offline, sin fotocélula)

> Verás `Promise {<pending>}` un instante y luego el objeto con el resultado:
> es normal, `fetch` es asíncrono.

**Amanecer / atardecer astronómico de un cuadro** (la "línea larga" de aquel día):
```js
fetch('/api/v1/cabinets/CAB-001/sun',{headers:{Authorization:'Bearer '+localStorage.getItem('ph_token')}}).then(r=>r.json()).then(console.log)
```
Devuelve `sunrise_utc` / `sunset_utc` para la posición del CM. Calculado offline.

**Nivel de dimming recomendado AHORA** (sol + tarifa, modo asesor):
```js
fetch('/api/v1/cabinets/CAB-001/auto-level',{headers:{Authorization:'Bearer '+localStorage.getItem('ph_token')}}).then(r=>r.json()).then(console.log)
```
Devuelve `recommended_level`, si `is_dark`, el `tariff_period` y el `floor`.

**Tramo de tarifa actual y su tope**:
```js
fetch('/api/v1/tariff/now',{headers:{Authorization:'Bearer '+localStorage.getItem('ph_token')}}).then(r=>r.json()).then(console.log)
```
Devuelve `period` (P1/P2/P3), `label` (Punta/Llano/Valle) y `level_cap`.

**Precio de la luz en tiempo real** (si activas `PHOENIX_PRICE_SOURCE=ree`):
```js
fetch('/api/v1/tariff/price',{headers:{Authorization:'Bearer '+localStorage.getItem('ph_token')}}).then(r=>r.json()).then(console.log)
```
Con el proveedor apagado (por defecto) devuelve `{available:false}`. Activado y
con internet, `{available:true, price_eur_kwh, eur_mwh, at}`. Si la API externa
falla, cae a `available:false` y el sistema usa los tramos fijos.

**Topes de tarifa de un proyecto** (nuevo, 14-jun):
```js
fetch('/api/v1/projects/1/tariff',{headers:{Authorization:'Bearer '+localStorage.getItem('ph_token')}}).then(r=>r.json()).then(console.log)
```
Devuelve los topes del proyecto, los `effective` (sustituyendo NULL por el global) y los `defaults`.

## Plantilla genérica (cualquier GET)
Cambia la ruta por la que quieras (`/api/v1/...`):
```js
fetch('/api/v1/RUTA_AQUI',{headers:{Authorization:'Bearer '+localStorage.getItem('ph_token')}}).then(r=>r.json()).then(console.log)
```

> Nota: estas pruebas son de **solo lectura** (GET). No cambian nada en el sistema.
> Para POST/PUT mejor usar la interfaz, que valida y audita.

## Pruebas del bloque 16-jun · data:transfer · backup · emergencia parcial

**¿Tengo el permiso `data:transfer`?** Lo necesitas para importar/exportar:
```js
fetch('/api/v1/auth/me',{headers:{Authorization:'Bearer '+localStorage.getItem('ph_token')}}).then(r=>r.json()).then(m=>console.log(m.permissions.includes('data:transfer')?'✓ data:transfer':'✗ falta data:transfer'))
```
Si entras como `phoenix` (owner) saldrá ✓ siempre (wildcard). Como `operador` o
`tecnico`: ✗ (y los botones ⬇ CSV / ⬆ Importar no aparecen en pantalla).

**Backup JSON de un CM completo** (cuadro + circuitos + luminarias):
```js
fetch('/api/v1/cabinets/CAB-001/backup',{headers:{Authorization:'Bearer '+localStorage.getItem('ph_token')}}).then(r=>r.json()).then(console.log)
```
Devuelve `{schema_version:1, cabinet, circuits, lightpoints}`. Cada luminaria
lleva `circuit_number` (clave estable, no un id transitorio). El mismo JSON
lo descarga el botón **⬇ Backup JSON** en Topología → ficha del CM.

**Restaurar un backup en OTRO CM** (lo usa como plantilla; UPSERT, no borra):
```js
const payload = /* pega aquí el JSON descargado de un CM */ {};
fetch('/api/v1/cabinets/CAB-NUEVO/restore',{method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+localStorage.getItem('ph_token')},body:JSON.stringify(payload)}).then(r=>r.json()).then(console.log)
```
Resumen: `{circuits_created, circuits_updated, lp_created, lp_updated, errors}`.

**Emergencia POR CM** (solo dos cuadros, no todo el ámbito):
```js
fetch('/api/v1/emergency/all-on',{method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+localStorage.getItem('ph_token')},body:JSON.stringify({cabinet_codes:['CAB-001','CAB-002']})}).then(r=>r.json()).then(console.log)
```
Sin body (`body:'{}'`) o con la lista vacía → emergencia global (todo el scope),
como antes. Apagar igual: `/api/v1/emergency/clear` con o sin `cabinet_codes`.

**Quién está en emergencia AHORA**:
```js
fetch('/api/v1/emergency/status',{headers:{Authorization:'Bearer '+localStorage.getItem('ph_token')}}).then(r=>r.json()).then(console.log)
```
Devuelve `{active, cabinets:['CAB-001',…]}` — solo los CMs del scope.
