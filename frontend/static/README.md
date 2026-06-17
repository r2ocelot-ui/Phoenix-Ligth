# Logos / imágenes estáticas de Phoenix-Light

Suelta aquí los archivos de marca. El panel los carga solo (se sirven en
`/ui/static/...`). Si un archivo no existe, hay **respaldo automático** (el
emblema SVG de llama), así que nada se rompe.

## Archivos que el panel busca

| Archivo | Dónde aparece | Recomendado |
|---|---|---|
| `phoenix-icon.png` | Emblema del **menú** + **login** + **favicon** | Cuadrado (256×256 o 512×512), fondo **transparente**, el fénix **rojo simple** |
| `phoenix-hero.png` (opcional) | Cabecera "héroe" del login (futuro) | Apaisado, el fénix épico |

## Cómo ponerlo
1. Recorta el **fénix rojo simple** (solo el icono, fondo transparente).
2. Guárdalo aquí como `phoenix-icon.png`.
3. Recarga el panel con **Ctrl+F5** (para saltar la caché del navegador).

> Mientras no exista `phoenix-icon.png`, se ve el emblema de llama por defecto.
> La CSP permite estos archivos porque van en el mismo origen (`'self'`).
