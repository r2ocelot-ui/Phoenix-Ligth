# Hydra · IA en semáforos — viabilidad, hardware y costes

> Nota de investigación para **Hydra** (división de tráfico de Kumiho), guardada
> desde la sesión de Phoenix-Light el **2026-06-16**. Responde a: *¿hay IA real
> para un semáforo hoy en España, en el regulador, sin meter un mini-PC con NPU
> y sin los tensor cores de NVIDIA?* Precios **orientativos** (búsqueda web
> jun-2026, sin IVA; la versión industrial IP67/fanless/temperatura extendida
> suele subir 30–50 %). Fuentes al final.

## 1. ¿Hay IA real en semáforos en España hoy? — Sí, con matiz
- **Marco legal**: Real Decreto 450/2026 → Sistemas Inteligentes de Transporte
  (SIT) en vías urbanas e interurbanas. Es el "luz verde del gobierno".
- **Semáforos conectados**: detectar ambulancias → corredor verde, analizar
  densidad y ajustar ciclos, reaccionar a peatón que cruza.
- **DGT / Guardia Civil**: ya usan cámaras con visión artificial (multas en
  STOP, radares IA) y pilotos en interurbano (AP-7 Tarragona, límites variables
  por IA). *Lo urbano lo gestiona el ayuntamiento; lo interurbano DGT/GC.*

## 2. El matiz clave: "IA" son DOS cosas
| Parte | Qué hace | Dónde corre |
|---|---|---|
| 🧠 **Percepción** (visión) | Detecta/cuenta coches, peatones, bicis | **Necesita acelerador** (NPU/VPU/GPU) |
| ⚙️ **Decisión** (regulación) | Decide tiempos de verde según demanda | **CPU normal del regulador** |

- La **decisión** cabe en el regulador clásico (CPU normal), pero eso es
  **control adaptativo** clásico (SCOOT/SCATS/MOVA): "inteligente", **no deep
  learning**.
- La **visión** (lo que la gente llama "IA") **sí necesita un acelerador
  neuronal**; no cabe en un regulador clásico (PLC/CPU industrial) en tiempo real.

## 3. ¿Sin NVIDIA y sin mini-PC? — Sí, pero hace falta un NPU en algún sitio
- **NVIDIA NO es obligatorio.** Competencia real para el borde:
  - **Hailo-8** → ~26 TOPS @ 2,5 W (rey del rendimiento/vatio para vídeo always-on).
  - **Google Coral (Edge TPU)** → ~4 TOPS @ 2 W.
  - NPUs integradas: Rockchip RK3588, NXP i.MX8M Plus, Ambarella, Qualcomm…
- **ARM (Ethos-U / Ethos-N)**: NPUs reales pero de gama baja/media; **NO
  equiparables a los tensor cores de NVIDIA**. Para visión de tráfico seria se
  tira de Hailo/Coral/Jetson o de la NPU que ya lleva la cámara.
- **Sin NINGÚN acelerador**: solo si la IA va dentro de la cámara, o si usas
  sensores no-cámara (espiras inductivas/radar/magnetómetros) + algoritmo
  adaptativo (no deep learning).

### Las 3 formas reales hoy
1. **Cámara inteligente** (NPU dentro) → el regulador solo recibe "hay 8 coches".
   *No añades mini-PC: la IA va en la cámara.* (Lo más común.)
2. **Regulador moderno con NPU integrada** (SoC RK3588/NXP) → IA dentro del
   regulador, **sin NVIDIA**.
3. **Sin cámaras**: loops/radar/magnetómetros + control adaptativo (smart, no IA).

## 4. Precios — aceleradores / mini-PC AI
| Equipo | TOPS | Consumo | Precio aprox. (EUR) |
|---|---|---|---|
| Google Coral USB | 4 | 2 W | 60–80 € |
| Hailo-8L M.2 | 13 | ~2 W | ~100 € |
| **Hailo-8 M.2** | 26 | 2,5 W | ~250 € |
| Raspberry Pi 5 + Hailo-8 (kit) | 26 | ~10 W | ~350–400 € |
| **Jetson Orin Nano Super** (dev kit) | 67 | 7–25 W | ~250 € |
| Jetson Orin NX | 100 | 10–25 W | ~600 € |
| **Jetson AGX Orin** (>100 TOPS) | 200–275 | 15–60 W | ~2 000 €+ |

> Detalle: el **Orin Nano Super cuesta lo mismo que un Hailo-8 (~250 €) y rinde
> 2,5× más TOPS (67 vs 26), pero consume 5–10× más**. En un cuadro 24/7 con
> respaldo, **el vatio pesa más que el TOPS**. Por encima de 100 TOPS en formato
> pequeño, NVIDIA no tiene rival (Hailo se queda en 26–40).

## 5. Precios — cámaras
| Tipo | Precio (EUR) | Qué hace |
|---|---|---|
| Cámara IP sencilla | 30–80 € | Solo vídeo; la IA la hace otro equipo |
| Cámara IP tráfico industrial (IP67, varifocal) | 150–300 € | Solo vídeo, robusta |
| **Cámara ANPR/IA integrada** (Dahua/Hikvision) | 800–2 500 € | IA dentro: cuenta, matrícula, peatón |

## 6. Arquitecturas por cruce (≈ 4 cámaras)
- **A · Cámaras sencillas + mini-PC central**: 4×60 € + Jetson Orin NX 600 €
  ≈ **840 €/cruce**. Barato, IA centralizada; más cable y punto único de fallo.
- **B · Cámaras IA integradas**: 4×1 000 € ≈ **4 000 €/cruce**. Plug-and-play,
  certificadas, independientes; 4–5× más caro.
- **C · Híbrida (la de los pilotos)**: 4×200 € + Hailo-8/Pi5 o Orin Nano ~400 €
  ≈ **1 200 €/cruce**. Buen punto medio.

## 7. Conclusión / diseño recomendado para Hydra
- Cámaras sencillas + mini-PC NPU sale **3–4× más barato** que cámaras IA
  integradas y **funciona** (es lo que hacen Frigate/DeepStream).
- **Pero** el tráfico **municipal** suele exigir homologación (IP67, temp.
  extendida, CE/EN50155…) → ahí piden cámaras ANPR certificadas (caras). Para
  **piloto / Hydra interno**, la vía barata es ideal; para **vender a
  ayuntamiento**, contar con cámaras certificadas.
- Mini-PC: **Hailo + Pi 5** gana en TOPS/€ y €/W; **NVIDIA Orin NX/AGX** cuando
  necesitas >100 TOPS reales o varios streams a 30 fps con YOLO grande.
- **Patrón limpio (estilo Phoenix "lo del borde manda")**: IA en la cámara o en
  un edge-box junto al regulador → el regulador recibe conteo/eventos y aplica
  el ciclo. Hydra NO necesita una GPU NVIDIA por cruce.

## Fuentes (jun-2026)
- Xataka — semáforos inteligentes en España (marco legal): https://www.xataka.com/movilidad/semaforos-inteligentes-estan-pasito-cerca-espana-nuevo-marco-legal-esto-que-cambia-que-todavia-no
- El Confidencial Digital — AP-7 DGT/IA: https://www.elconfidencialdigital.com/articulo/guardia-civil/autopista-catalana-donde-dgt-prueba-limite-inedito-inteligencia-artificial/20250906064500978812.html
- AIMultiple — Edge AI chips 2026: https://research.aimultiple.com/edge-ai-chips/
- Hailo-8 M.2 (26 TOPS / 2,5 W): https://hailo.ai/products/ai-accelerators/hailo-8-m2-ai-acceleration-module/
- Welectron — Hailo-8 M.2 a 249 €: https://www.welectron.com/Waveshare-27812-Hailo-8-AI-M2-module-only_1
- NVIDIA Jetson Orin Nano Super (67 TOPS): https://www.nvidia.com/en-us/autonomous-machines/embedded-systems/jetson-orin/nano-super-developer-kit/
- By Demes — cámara ANPR Dahua tráfico: https://bydemes.com/es/productos/cctv/camaras-ip/captura-matriculas-trafico/DAHUA-4611
