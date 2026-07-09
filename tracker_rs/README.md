# radar_tracker_rs — tracker propio de nube de puntos (uRAD Industrial)

Prototipo en Rust para **sustituir el `do_tracking` compilado de Anteral** por un
procesado propio, robusto y ajustable. Nace porque el `.so` de Anteral crashea de
forma intermitente (`ValueError: setting an array element with a sequence` en
`distance_matrix`) y a veces **cuelga el radar** hasta un reinicio manual.

## Por qué es viable

La nube de puntos cruda **ya es accesible**: el `vehicleCounter_smartcities_v2_3.py`
de Anteral (código ABIERTO) lee el serie y arma la nube antes de pasarla al `.so`.
Lo único que reimplementamos es la parte que crashea: **asociación entre frames +
clasificación**. No hay que reversear el radar.

## Formato de entrada (`PointCloud.txt`, SAVE_RAW_DATA=True)

Una línea por frame:

```
<cpu_cycles> <frame> <ts> <num_obj> [x y z velocity snr noise]×N
```

- `ts`: epoch (s) con decimales.
- por punto: `x` lateral (m), `y` rango (m), `z` altura (m), `velocity` radial
  (km/h con signo: − acercándose / + alejándose), `snr`, `noise`.
- **El uRAD entrega ~1 punto por objeto** (hace clustering en su firmware). Ej.
  real capturado: `... 638 1783593679.904 1 -3.365 11.382 1.495 23.561 74 421`
  = un objeto a **y=11,4 m** a 23,6 km/h.

## Estructura

```
src/
├── model.rs     # Point, Frame
├── parse.rs     # PointCloud.txt -> Frame (+ tests con líneas reales)
├── track.rs     # Tracker: vecino más cercano + alpha-beta + ciclo de vida
├── classify.rs  # FinishedTrack -> tipo (por velocidad/persistencia)
├── output.rs    # línea estilo Anteral (Vehicle_results) + stub MQTT
└── main.rs       # CLI: replay <file> | serve
```

## Uso

```bash
cargo build --release
# reproducir un dump y sacar los vehículos (formato Anteral) + resumen:
./target/release/radar_tracker replay samples/2026-07-09_PointCloud_sample.txt
cargo test    # tests del parser con líneas reales
```

`replay` saca por **stdout** las líneas `<epoch> <vel_signed> <x> <type>` (las
consume el pipeline tal cual) y por **stderr** un resumen (frames, puntos,
vehículos por tipo). Pensado para **comparar con la salida de Anteral** sobre los
mismos frames.

## Roadmap

- **Fase 1 (offline, este esqueleto)** — parseo + tracking + clasificación +
  `replay`. Std-only, compila sin red.
- **Fase 2 (validación)** — con un dataset real de tráfico (captura en hora
  punta), afinar `TrackerParams` (`gate_m`, `max_misses`, `min_hits`) y los
  umbrales de clasificación **comparando conteos con Anteral**. Sustituir el
  alpha-beta por **Kalman** (nalgebra) con gating por Mahalanobis; asociación
  multi-objeto (Hungarian) cuando haya varios puntos/frame.
- **Fase 3 (serve en vivo)** — leer el serie directamente (`serialport`: config
  115200 + data 921600, `/dev/serial0`; el framing/TLV está en `read_header`/
  `get_commands` del `.so`, probablemente formato tipo TI mmWave, a confirmar
  capturando paquetes) y **publicar los tracks a MQTT** (`rumqttc`) con el mismo
  payload que el bridge → un único daemon Rust reemplaza *python de Anteral + .so
  + bridge*.

## Limitación conocida

Con ~1 punto por objeto **no se puede medir longitud** de vehículo con fiabilidad
(así separa Anteral normal/medio/largo). Clasificamos por velocidad/persistencia;
distinguir tipos por tamaño requiere más señal o heurísticas derivadas (nº de
puntos, duración del track). Es una limitación del sensor, no solo del software.
