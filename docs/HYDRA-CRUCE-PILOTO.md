# Hydra · Cruce piloto — mini-PC AMD + cámaras certificadas + regulador

> Continúa `HYDRA-IA-SEMAFOROS.md`. Aterriza la teoría en piezas concretas:
> qué mini-PC AMD, qué cámaras industriales/homologadas para vía pública, qué
> regulador, qué cableado y cuánto sale. Comparativa final con la opción
> "cámaras con IA dentro" que vimos antes.
>
> Precios **orientativos** (web jun-2026, sin IVA). La versión industrial
> certificada sube 30-50 % sobre el doméstico. Fuentes al final.

## 1. Resumen ejecutivo
- **Recomendado piloto Hydra** → mini-PC **AMD Ryzen AI 9 HX 370** (NPU XDNA 2,
  **50 TOPS**) + 4 cámaras industriales **sin IA** + regulador clásico.
  **≈ 5.100 €/cruce**, sin NVIDIA.
- **Para venta a ayuntamiento** → cámaras ANPR/IA certificadas Dahua/Hikvision
  o térmicas FLIR. **≈ 9.800–18.500 €/cruce**, también sin NVIDIA.
- Diseño "lo del borde manda": IA en edge-box junto al regulador (o dentro de
  la cámara). El regulador recibe **conteo/eventos** y aplica ciclo. No hace
  falta GPU NVIDIA por cruce.

## 2. Mini-PC AMD (sin NVIDIA)
AMD lleva NPU **XDNA** integrada en sus Ryzen AI desde 2024 y **XDNA 2** en
Strix Point (2024-2025). El tope actual (Ryzen AI 9 HX 370) da 50 TOPS de NPU
+ 16 TOPS de iGPU Radeon = ~66 TOPS de cómputo IA en ~30 W. Bate al Hailo-8
(26 TOPS) en bruto y se acerca a un Jetson Orin Nano Super (67 TOPS) sin pisar
NVIDIA.

| Modelo | NPU + GPU IA | Consumo | Precio aprox. | Notas |
|---|---|---|---|---|
| Minisforum UM870 Slim (Ryzen 7 8845HS) | 16 TOPS NPU + 8 TOPS iGPU | 35–65 W | ~700 € | Hawk Point; entrada digna |
| **Minisforum AI X1 Pro** (Ryzen AI 9 HX 370) | **50 TOPS NPU + 16 TOPS iGPU** | 35–54 W | **~1.300 €** | Strix Point, el más capaz hoy sin NVIDIA |
| GMKtec K11 (Ryzen AI 9 HX 370) | 50 TOPS NPU + 16 TOPS iGPU | 35–54 W | ~1.200 € | Alternativa más barata, mismo silicio |
| ASUS NUC 14 Pro AI (Intel Core Ultra) | 11 TOPS NPU + iGPU | 15–28 W | ~1.000 € | Plan B si AMD no llega |
| **OnLogic Karbon 410** (Ryzen Embedded V2000) | iGPU Vega ~3 TOPS | 12–25 W | ~1.500–2.500 € | **Industrial fanless IP40, –40/+70 °C** |
| iBase EC-3300 / Axiomtek tBOX300 (Ryzen Embedded) | iGPU ~6 TOPS | 15–54 W | ~1.700 € | Industrial con expansión M.2/PCIe |

> Honesto: el AMD **Ryzen AI HX 370 doméstico** rinde mucho más que cualquier
> Ryzen Embedded actual, pero **no está homologado** para vía pública. Para
> piloto Hydra interno vale. Para licitación municipal, hay que ir a OnLogic /
> iBase / Axiomtek industriales aunque tengan menos TOPS, o meter el HX 370 en
> un **armario IP54 con SAI y validación EMC** (más curro, pero posible).

## 3. Cámaras certificadas para tráfico
Exigencias típicas en pliegos municipales españoles:
- **IP66/67** (estanqueidad), **IK10** (vandalismo), temp –40 a +70 °C.
- **CE + EN 50293** (compatibilidad EM en sistemas de señalización vial).
- **EN 50121-4** (EMC ferroviario / vías).
- **EN 12368** si la cámara va integrada con la cabeza semafórica.
- A veces homologación específica de DGT o del ayuntamiento.

| Modelo | Tipo | IA dentro | Precio | Notas |
|---|---|---|---|---|
| Dahua IPC-HFW5541E-Z (bullet 5 MP varifocal) | IP industrial | **No** (solo vídeo) | ~280 € | IP67/IK10, robusta, sin IA → el mini-PC hace el trabajo |
| Axis P3267-LVE / Q-line outdoor | IP industrial | No | ~600–1.200 € | Top en fiabilidad y firmware |
| **Dahua ITC413-PW4D-IZ1** (ANPR/ITC) | IP industrial **con IA** | **Sí** (matrícula, conteo) | ~1.700 € | El típico de ayuntamientos en ES |
| Hikvision iDS-TCM403-AI / iDS-2CD7A26G0/P-IZHS | IP industrial con IA | Sí | ~1.500 € | Equivalente Hikvision |
| **FLIR TrafiCam-x / TrafiBot AI** | **Térmica + IA** | Sí (propietario) | ~3.500–4.500 € | Estándar de facto en intersecciones serias; ve de noche y con niebla |
| Bosch DINION IP traffic | IP industrial con analítica básica | Parcial | ~1.000–1.500 € | Buena para conteo, ANPR no |

## 4. Regulador (la "decisión")
La decisión cabe en CPU normal (control adaptativo SCOOT/SCATS/MOVA). No
necesita NPU. Lo que cuenta es la **homologación** y el armario.

- **Siemens Sitraffic sX** / **Swarco MR-3** / **Citilux SC-IO** → reguladores
  homologados de vía pública. ~3.000–6.000 € (con armario).
- **PLC Beckhoff CX9020** / Phoenix Contact AXC F → si el cruce es **privado**
  (campus, parking, polígono) o piloto interno. ~800–1.200 €. **NO** se puede
  colgar en vía municipal sin homologación.
- En el piloto Hydra, asumo PLC genérico (no es producto final).

## 5. Cableado y armario

```
                        ┌─────────────────────────────────────┐
                        │ Armario IP54 / IP66 + SAI 1500 VA   │
                        │                                     │
   Red eléctrica ──────►│ Diferencial + magnetotérmico        │
                        │                                     │
                        │ Switch industrial PoE++ (Moxa)──────┼──► 4× cámara IP industrial
                        │                                     │     (Cat6 outdoor STP gel-filled,
                        │ Mini-PC AMD (edge-box)              │      o fibra OM3 si >30 m)
                        │   └── Frigate / DeepStream / YOLO   │
                        │   └── MQTT → conteo/eventos ────────┼──► Regulador (vía Modbus/RS485)
                        │                                     │
                        │ Router 4G industrial (backhaul)     │
                        └─────────────────────────────────────┘
```

- **Vídeo**: Cat6 STP outdoor (gel-filled, doble cubierta UV) con PoE+ para
  ≤30 m. Para tramos largos, **fibra OM3** + conversor industrial (Moxa /
  Hirschmann).
- **PoE**: switch industrial PoE++ 8 puertos (Moxa EDS-G508E-PN o Hirschmann
  Spider) ~500 €. Cámaras 4 K se zampan 15-25 W cada una, sube el budget.
- **Backhaul**: router 4G/5G industrial (Teltonika RUT241 ~200 €, Robustel
  R3000 ~600 €) + SIM M2M ~10 €/mes.
- **SAI**: APC Smart-UPS 1500 VA o equivalente Riello industrial ~450 €.
  20 min de respaldo dan para reconectar y avisar.

## 6. BOM por cruce piloto (4 brazos)

### Opción A — Mini-PC AMD + cámaras industriales sin IA ⭐ **PILOTO**
| Concepto | Coste |
|---|---:|
| Minisforum AI X1 Pro (Ryzen AI 9 HX 370, 50 TOPS) + caja IP54 | 1.300 € |
| 4× Dahua IPC-HFW5541E-Z (5 MP industrial sin IA) | 1.120 € |
| Switch PoE+ industrial Moxa EDS-G508E | 500 € |
| Router 4G industrial Teltonika RUT241 | 200 € |
| SAI APC Smart-UPS 1500 VA | 450 € |
| Regulador (PLC piloto Beckhoff CX9020 + I/O) | 1.000 € |
| Cableado Cat6 outdoor + fibra reserva + canaleta | 300 € |
| Armario chapa IP54 600×400×200 | 250 € |
| **Total ≈** | **5.120 €** |

### Opción B — Cámaras ANPR/IA certificadas, sin edge-box
| Concepto | Coste |
|---|---:|
| 4× Dahua ITC413-PW4D-IZ1 (ANPR con IA on-board) | 7.000 € |
| Switch industrial PoE++ (más potencia, 30 W/puerto) | 600 € |
| Router 4G industrial | 200 € |
| SAI | 450 € |
| Regulador (PLC piloto) | 1.000 € |
| Cableado + armario | 550 € |
| **Total ≈** | **9.800 €** |

### Opción C — FLIR térmica (estándar mundial intersecciones)
| Concepto | Coste |
|---|---:|
| 4× FLIR TrafiCam-x / TrafiBot AI (térmica + IA) | 16.000 € |
| Switch industrial PoE++ | 600 € |
| Router 4G + SAI + regulador + cableado | 2.100 € |
| **Total ≈** | **18.700 €** |

## 7. Comparativa final

| Aspecto | A · Mini-PC AMD + cám. industrial | B · Cámaras IA certificadas | C · FLIR térmica |
|---|---|---|---|
| **Coste / cruce** | **~5.100 €** | ~9.800 € | ~18.700 € |
| **NPU / cómputo IA** | 50 TOPS NPU + 16 TOPS iGPU (AMD XDNA 2) | 4 TOPS por cámara (propietario) | propietario FLIR |
| **Cámaras certificadas EN 50293** | Sí (industriales IP67 sin IA) | Sí (industriales con IA) | Sí (referente del sector) |
| **Homologación municipal** | Parcial — el mini-PC HX 370 doméstico exige armario IP54 + validación EMC. Cámara sí, regulador exige homologado real | Sí — cámaras y stack reconocidos en pliegos | Sí — estándar de facto en intersecciones |
| **NVIDIA dentro** | **No** (AMD XDNA) | No (NPU propietario cámara) | No (propietario FLIR) |
| **Punto único de fallo** | Sí: si cae el mini-PC, las 4 cámaras quedan ciegas | No: cada cámara es independiente | No: cada cámara es independiente |
| **Mantenimiento / desarrollo** | Abres una caja Linux y trasteas (Frigate / DeepStream / YOLO) | Caja negra del fabricante | Caja negra del fabricante |
| **Visión nocturna / niebla** | Depende de la cámara (IR ~30 m) | IR de la cámara | **Térmica real** — gana con diferencia |
| **Bueno para** | Piloto Hydra, polígono, parking, campus | Cruce municipal con licitación | Carretera real, autovía, intersección con prestaciones |

## 8. vs `HYDRA-IA-SEMAFOROS.md` — qué cambia con piezas concretas

| | Cálculo previo | Cálculo realista (este doc) |
|---|---|---|
| **A · Cámaras sencillas + mini-PC central** | ~840 € | **~5.100 €** (con SAI, router 4G, switch industrial, armario IP54) |
| **B · Cámaras IA integradas** | ~4.000 € | **~9.800 €** (cámaras certificadas EN 50293, no domésticas) |
| **C · Híbrida** | ~1.200 € | (cubierta por A — la "híbrida" es la A bien hecha) |

> El cálculo anterior asumía piezas de "garaje" (cámara IP doméstica 60 €,
> Hailo-8 250 €, sin SAI, sin router 4G, sin armario industrial). **Para
> cuadro 24/7 en vía pública multiplica por ~5**. Con piezas serias, A sigue
> ganando: 5.100 € vs 9.800 € (B) vs 18.700 € (C).

## 9. Conclusión / patrón recomendado para Hydra
1. **Piloto interno** → Opción A. 5.100 €/cruce, AMD Ryzen AI HX 370 con
   50 TOPS de NPU, **sin NVIDIA**, cámaras Dahua industriales sin IA. Frigate
   o YOLO sobre AMD ROCm/ONNX-Runtime+VAAPI. 4 streams 1080p sin sudar.
2. **Venta a ayuntamiento** → Opción B (cámaras ANPR Dahua/Hikvision
   homologadas) o C (FLIR si exigen térmica/noche). Multiplica por 2-4× pero
   pasa pliego sin pelear.
3. **Sin NVIDIA confirmado**: AMD XDNA 2 (HX 370) o XDNA (8845HS) cubren
   tráfico urbano con holgura. No hace falta Jetson.
4. **El regulador no cambia**: clásico homologado (Siemens / Swarco /
   Citilux) recibiendo conteo/eventos vía MQTT/Modbus. El edge-box AMD solo
   es percepción; la decisión la toma el regulador.
5. **Frontera Phoenix/Hydra**: este patrón ("lo del borde manda, el control
   recibe eventos") es **el mismo** que en Phoenix-Light (luminaria + cuadro
   con dimming IA). Los hermanos comparten arquitectura, distinto dominio.

## Fuentes
- AMD Ryzen AI 300 series / XDNA 2 (NPU 50 TOPS): https://www.amd.com/en/products/processors/laptop/ryzen/ai-300-series.html
- Minisforum AI X1 Pro (Ryzen AI 9 HX 370): https://store.minisforum.com/products/minisforum-x1-pro
- GMKtec K11 (Ryzen AI 9 HX 370): https://www.gmktec.com/products/gmktec-k11
- OnLogic Karbon 410 industrial AMD: https://www.onlogic.com/karbon-410/
- Dahua ITC413-PW4D-IZ1 ANPR: https://www.dahuasecurity.com/products/All-Products/ITC-Cameras
- Dahua IPC-HFW5541E-Z industrial: https://www.dahuasecurity.com/products/All-Products/Network-Cameras
- FLIR TrafiBot AI / TrafiCam: https://www.flir.com/products/trafibot-ai-hd/
- Moxa EDS-G508E switch industrial PoE: https://www.moxa.com/en/products/industrial-network-infrastructure/ethernet-switches/managed-switches/eds-g500e-series
- Teltonika RUT241 router 4G industrial: https://teltonika-networks.com/products/routers/rut241
- EN 50293 — EMC en sistemas de señalización vial: https://standards.cencenelec.eu/
- Frigate NVR (IA en edge con NPU/GPU): https://frigate.video/
