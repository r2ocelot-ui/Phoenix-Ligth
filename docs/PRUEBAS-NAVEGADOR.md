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
