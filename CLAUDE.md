# Radar IoT — planteamiento de integración del uRAD Smart Traffic RPi en AGlabs

Documento técnico estático que propone cómo integrar el **uRAD Smart Traffic RPi** (Anteral, radar 60 GHz FMCW con Raspberry Pi embebida) en la plataforma IoT de AGlabs vía cliente MQTT sobre WiFi/4G.

---

## Publicación

- **URL pública:** [`https://aglabs.es/radar_iot/`](https://aglabs.es/radar_iot/) — página estática (HTML + CSS, sin JS).
- **Patrón:** path-based bajo `aglabs.es`, sin subdominio. Convención AGlabs para proyectos pequeños — ver [`/root/CLAUDE.md §Convención: páginas estáticas de proyectos`](/root/CLAUDE.md).
- **Fuente:** [`web/index.html`](web/index.html) + [`web/favicon.svg`](web/favicon.svg) (tinta `#2B2825`) + [`web/icon.svg`](web/icon.svg) (cobre `#A68B5B`, usado en la card del portal).
- **Sirve:** `boreas_nginx` vía bind-mount `/root/radar_iot/web → /app/radar_iot_web:ro`. Location `^~ /radar_iot/` en el bloque `aglabs.es` de [`/root/boreas_rgiot/nginx.conf`](../boreas_rgiot/nginx.conf), justo después de `lora_iot`.
- **Portal AG:** registrado como `App` slug `radar_iot` + `AppItem` slug `home` en Sección Proyectos, kind `external`, `path=/radar_iot/`, `restricted_to_users` = pablo, jose, pravia (mismo trío que LoRa IoT).
- **Estilo:** hereda `https://aglabs.es/static/portal/aglabs.css` (sistema de diseño AGlabs — Fraunces + Inter, paleta Birch/Lake/Moss). Sin marca propia.
- **Edición:** modificar [`web/index.html`](web/index.html) directamente; nginx sirve el cambio inmediatamente (sin restart, sin redeploy).

---

## El dispositivo en una línea

uRAD Smart Traffic RPi — solución integrada de Smart Cities en una sola caja IP66 (171 × 121 × 80 mm, 1,1 kg) que combina el módulo radar uRAD Industrial 60 GHz FMCW con una Raspberry Pi (Quad-core ARM Cortex-A72, 1,8 GHz, 2 GB SDRAM, Raspberry Pi OS) y un dongle 4G Huawei opcional. Alimentación 8–40 V DC (4,5 W), conexión WiFi nativa de la RPi. Hardware v2.0, firmware Vehicle Monitoring v2.4 (manual fechado 28/10/2025). Fabricado por **Anteral S.L.** (Huarte, Navarra) — [urad.es](https://urad.es).

**Documentación oficial del fabricante:**
- Datasheet: <https://urad.es/wp-content/descargables/uRAD%20-%20Datasheet%20-%20Smart%20Traffic%20RPi%20-%20ES.pdf> (versión 20/10/2025).
- Manual de usuario: `uRAD - User Manual - Smart Traffic RPi - ES - 251028.pdf` (versión 28/10/2025) — entregado en mano con la compra.

Alcance: 30 m (modo conteo) / 100 m (otras apps), velocidad ≤ 180 km/h, distancia lateral ± 15 m (precisión óptima hasta ± 8 m), hasta 4 carriles con un radar (6 con precisión degradada), efectividad declarada > 95 %.

**Casos de uso del firmware nativo:**
1. Conteo bidireccional de vehículos con velocidad positiva (alejándose) y negativa (acercándose) simultánea.
2. Clasificación por tipo: 1 = normal (< 8 m), 2 = medio (8–15 m), 3 = largo (> 15 m), 4 = bici/moto, 5 = peatón (< 10 km/h).
3. Radar pedagógico, control de velocidad, aforo de bicis en carril bici, detección de peatones en pasos de cebra.

---

## Arquitectura propuesta (resumen — el detalle vive en `index.html`)

```
┌──── Smart Traffic RPi (caja IP66 única) ────┐
│                                              │
│  [uRAD Industrial 60 GHz]──UART──[Raspberry Pi]──WiFi/4G──[mqtt.aglabs.es]
│                                      │                              │
│                                      ▼                              ▼
│                          Vehicle_results.txt          [Telegraf → nexus_radar]
└──────────────────────────────────────┘                              │
                                                                       ▼
                                                            [Boreas — vista Tráfico]
```

- **Nivel 1 — dispositivo único en columna.** Radar + RPi en la misma caja IP66. La RPi ejecuta `vehicleCounter_smartcities_v2_x.py` (servicio pm2 `radar`) y, en la integración AGlabs, un segundo proceso publica los eventos a MQTT. **No hay bridge externo** — la diferencia clave respecto a la variante modular del radar.
- **Nivel 2 — broker AGlabs (`mqtt.aglabs.es`)**. Reusa el Mosquitto del proyecto `aglabs_mqtt`. Cero infra nueva de mensajería.
- **Nivel 3 — Boreas.** Ingesta vía `nexus_telegraf` a hypertable nueva `nexus_radar`. Visualización en vista "Tráfico" embebida en Boreas, alarmas reusando Cortex.

**Topics MQTT propuestos:**

```
aglabs/radar/<site>/<sensor>/track     # vehículo detectado: timestamp, velocity_kmh, x_m, type, id
aglabs/radar/<site>/<sensor>/event     # cruces de umbral, alarmas
aglabs/radar/<site>/<sensor>/state     # config activa, app cargada
aglabs/radar/<site>/<sensor>/$health   # LWT + heartbeat
```

Payload JSON, timestamp ISO 8601 UTC. ACL Mosquitto por `client_id` (ya implementado en `aglabs_mqtt`).

---

## Acceso a la RPi del dispositivo

Patrón de acceso del fabricante (no apto para producción, suficiente para configuración y debugging en campo):

1. **AP móvil del instalador** con SSID `uRAD_SN****` (los 4 últimos dígitos del SN y la clave llegan con la compra en un documento aparte).
2. La RPi se asocia automáticamente al levantarse el AP.
3. SSH o VNC contra la IP que muestra el móvil/portátil con el AP creado. Credenciales: usuario `pi`, clave `Anteral`.
4. Software en `~/Desktop/uRAD_Tracking_v2_x/`:
   - `vehicleCounter_smartcities_v2_x.py` — programa principal.
   - `*.so` — librerías compiladas (no editables).
   - `Results/` — outputs (`Vehicle_results.txt`, `PointCloud.txt` si está activo).

**Servicio pm2 `radar`** ya instalado y configurado para arranque automático:
```bash
pm2 list                  # estado
pm2 start radar           # arrancar (lanza vehicleCounter_smartcities_v2_x.py)
pm2 stop  radar
pm2 save                  # persistir estado
pm2 startup               # habilitar boot — copiar/ejecutar el comando "sudo env PATH..." que devuelve
```

---

## Parámetros de configuración (firmware Vehicle Monitoring v2.4)

Editar las constantes al principio de `vehicleCounter_smartcities_v2_x.py`:

| Variable | Valor recomendado | Comentario |
|---|---|---|
| `HIGHWAY_SCENARIO` | `False` para urbano · `True` para ≥ 120 km/h | True: menos resolución, no clasifica bicis/peatones |
| `USB_COMMUNICATION` | `False` | El radar habla por UART, no USB |
| `USE_FAN` | `True` | Ventilador PWM en pin 12 |
| `USB_CONNECTOR_UPWARD` | `False` | El dispositivo se monta con el conector hacia abajo |
| `pitch_angle` | según altura (ver tabla §Instalación) | Inclinación con la vertical |
| `yaw_angle` | `0` (1 carril), `±15` (2 carriles), `±30` (3) | Signo: + a la izquierda de la calzada, − a la derecha |
| `VELOCITY_POSITIVE/NEGATIVE` | ambos `True` | Para contar en ambos sentidos |
| `X_MIN/MAX_*_VELOCITY` | según geometría | Ventanas X (metros) por sentido |
| `SAVE_RESULTS` | `True` | Activar fichero `Vehicle_results.txt` |
| `SAVE_RAW_DATA` | `False` | Solo `True` para debug — fichero `PointCloud.txt` muy pesado |
| `OUTPUT_DATE_TIME_FORMAT` | `0` (ISO) o `1` (UNIX timestamp) | Para parseo aguas abajo, `1` es más fácil |
| `DEBUG_VEHICLES_DEF` | `True` solo en pruebas | Imprime cada vehículo en consola |

**Formato de `Vehicle_results.txt`** — una línea por vehículo, 4 columnas:
```
timestamp   velocity_kmh   x_distance_m   type
```
`type ∈ {1: normal <8m, 2: medio 8–15m, 3: largo >15m, 4: bici/moto, 5: peatón <10km/h}`

**GOTCHA (2026-06-11) — el `timestamp` de Anteral son DOS tokens.** El firmware
real escribe el timestamp como `yyyy/mm/dd HH:MM:SS` (con `/` y un espacio en
medio, hora **local** del Pi), así que una línea real tiene **5 tokens**
separados por espacio, no 4. El primer `parse_line` del bridge asumía un
timestamp de un solo token (epoch/ISO) → tiraba **toda** línea real con
`unparseable line … Invalid isoformat string: '2026/06/11'`. Arreglado:
`parse_line`/`parse_ts_token` aceptan ahora el formato Anteral (5 tokens,
`yyyy/mm/dd HH:MM:SS`) además del legacy de 4 tokens (bench/sintético).

**GOTCHA (2026-06-12) — el build real de Anteral rota por día y usa epoch+UUID.**
Con el crash de numpy resuelto, el build v2.3 que entregó Anteral resultó escribir
distinto a lo documentado: (a) **fichero con fecha** `Results/<YYYY-MM-DD>_Vehicle_results.txt`
(no el plano `Vehicle_results.txt`), y (b) líneas con **timestamp epoch + un UUID
de track al final**: `<epoch> <vel> <x> <type> <uuid>` (5 columnas). El parser ya
lo cubre (epoch en `parse_ts_token`, el UUID sobra y se ignora; Atlas genera su
propio `external_event_id`). Para la rotación diaria, `tail_loop` ahora **sigue el
`*Vehicle_results.txt` más reciente** del dir y cambia de fichero (desde offset 0)
al cambiar el día. **Validado end-to-end real**: detecciones del radar →
`nexus_radar` en boreas_db (track + speed_violation).

**GOTCHA OPERACIONAL — las "detecciones" en banco/oficina son ARTEFACTOS, no
tráfico.** El Tracking de Anteral es un contador de vehículos: fuerza **todo**
cluster que rastrea a un tipo (1-5) + velocidad; no sabe que no hay calzada. Por
eso, colocado en una oficina, emite `track`s igualmente. Hay que distinguir:
- Detecciones lentas (~3 km/h, tipo 5 peatón) ≈ una **persona** pasando — reales.
- Detecciones rápidas (75–119 km/h, tipos vehículo-largo/moto, a ~1,7 m,
  acercándose) = **ruido/multipath/eco** en sala cerrada (reflexiones en paredes,
  mobiliario, cristales), amplificado si corre la variante **highway**.
  Físicamente imposibles (ningún camión a 1,7 m a 119 km/h) → targets fantasma.
El 60 GHz se atenúa en paredes/cristal, así que **no** ve coches de la calle por
una ventana. **Los datos solo son significativos con el radar apuntando a una vía
real** según la geometría del manual de Anteral (altura ≥3 m, inclinación por
tabla, tramo recto 0–25 m, `yaw` por nº de carriles, `HIGHWAY_SCENARIO=false`
para uso urbano). Hasta entonces, `nexus_radar` recibe ruido — útil solo para
validar el pipeline, no para conclusiones de tráfico.

**Bloqueo de vendor pendiente (Anteral) — crash numpy 2.x.** En las RPi con
Debian 13 / numpy 2.x el Tracking Software (v2.4 con Python 3.13 del sistema, y
v2.3 en venv Python 3.11 — ambos con numpy 2.4.6) **crashea al procesar
detecciones** en `distance_matrix` (`ValueError: setting an array element with a
sequence` / `TypeError: only 0-dimensional arrays…`): numpy 2.x rechaza la
construcción de arrays "ragged". Con la escena vacía no crashea (frames `[]`);
revienta en cuanto hay objetos. El firmware del radar funciona ("Radar
working"). **Hasta que Anteral entregue un build compatible con numpy 2.x (o
para un Python donde se pueda fijar numpy<2), `Vehicle_results.txt` queda vacío
y no fluyen detecciones reales** — el bridge ya está listo para cuando lleguen.

---

## Instalación — geometría (manual del fabricante)

**Altura ↔ inclinación** (fórmula: `tilt = atan(height / 15)` grados):

| Altura | Pitch |
|---|---|
| 3 m | 11 ° |
| 4 m | 15 ° |
| 5 m | 18 ° |
| 6 m | 22 ° |

**Yaw según carriles** a un lado del radar: 1 carril → 0°, 2 carriles → 15°, 3 carriles → 30°. Signo: radar a la **izquierda** de la calzada → yaw **positivo**; radar a la **derecha** → yaw **negativo** (observador detrás del radar).

**Otras reglas:**
- Conector hacia abajo.
- Tramo recto en los 0–25 m frente al radar. Evitar curvas.
- Evitar tramos donde los vehículos paren completamente (genera duplicados).
- Para 6 carriles (3+3), recomendado un radar por sentido — la precisión cae más allá de ± 8 m laterales.
- Caja, anclaje y abrazaderas vienen incluidos (columna cilíndrica con articulación de ajuste vertical).

---

## Conectividad y despliegue — decisión arquitectónica

**Tomado el 2026-05-28 tras conversación con la agente Sonia.** Se documenta aquí porque condiciona la compra del hardware y todo el código posterior.

### Topología elegida — Escenario B (Smart Traffic detrás de Teltonika RUT241)

El Smart Traffic se compra **sin** el dongle 4G Huawei interno. La conectividad 4G se aporta con un **Teltonika RUT241** próximo al sensor (WiFi o ethernet entre RUT y Pi del Smart Traffic). Tres motivos:

1. **Reutilización de la flota AGlabs.** Diana (`/root/diana`) ya gestiona ~316 RUT241 con su API ubus, su VPN OpenVPN WirelessLogic, su inventario de IPs y sus SIMs SIMPro. Añadir un RUT241 más es coste marginal cero operativo; añadir una SIM y una pila 4G por dispositivo no.
2. **Acceso forense desde la base.** Diana ya tunela por VPN hasta cada RUT241, y desde el RUT se puede saltar por SSH a la LAN. Para el patrón de post-mortem "SSH + `sqlite3` en la Pi" que sustituye a la Django-app-per-Pi (ver §Almacenamiento local), esto es lo que abre el canal.
3. **Discovery automático.** Diana ya tiene `probe_lan_collectors` que clasifica Raspberry Pis detrás de un Teltonika. La Smart Traffic aparece sola en su inventario una vez conectada.

**Lo que NO hace Diana:** desplegar software en la Pi. Diana es Teltonika-only (API ubus / RutOS). El despliegue del wrapper Docker en la Pi del Smart Traffic vive aparte (ver siguiente sección). Esta separación se mantiene deliberadamente — Diana no debe asumir scope de "gestor genérico de Linux".

### Patrón de despliegue del wrapper en la Pi

| Fase | Patrón | Cuándo |
|---|---|---|
| Piloto (1 unidad) | SSH manual + `docker compose up -d` | Primer despliegue, sin automatización |
| Flota pequeña (2-5) | `cron` + `git pull` + `docker compose pull` cada 15 min | Cuando entre el segundo cliente |
| Flota grande (>5) | Imagen Docker en registry privado + watchtower o ansible-pull, reporte de versión vía MQTT `$health` | Cuando se justifique |

**Mientras tanto, todas las Pis reportan su `wrapper_version` actual en el topic `$health` retained, desde el día uno.** Así, cuando crezca la flota, ya está la telemetría de versión sin trabajo extra.

**Cuándo crear el proyecto hermano de Diana** (provisional: `cosmos` o `atlas` — "gestor de Pis Docker"): solo si la flota AGlabs de Pis (radar + Lar + colectores M-Bus + otros) supera ~10 unidades. No antes — extender Diana ahora sería mission creep.

### Comunicación con Boreas — `mqtt.aglabs.es` exclusivamente

**Único canal en producción.** El wrapper publica a `wss://mqtt.aglabs.es:443/mqtt` (WebSocket sobre TLS por el 443 de `boreas_nginx`). Se elige WSS en 443 en vez de MQTT/TLS en 8883 porque a 2026-05-28 el listener 8883 de `aglabs_mosquitto` **no está expuesto al exterior** — solo escucha dentro de `boreas_net`. El 443 ya está abierto y termina TLS en nginx que proxea por WebSocket al listener 9001 interno del broker. Además, 443 sobrevive mejor a firewalls de operador 4G que 8883.

Si en el futuro se abre 8883 al exterior, basta cambiar `MQTT_PORT=8883` y `MQTT_TRANSPORT=tcp` en `.env` de la Pi — sin cambios de código.

**Cuatro topics, semántica fijada:**

```
aglabs/radar/<site>/<sensor>/track     qos=1, no-retain   un mensaje por objeto consolidado
aglabs/radar/<site>/<sensor>/event     qos=1, no-retain   derivados (speed_violation, futuros conflictos peatón-vehículo)
aglabs/radar/<site>/<sensor>/state     qos=1, retain      snapshot de config activa (en startup y en cambios)
aglabs/radar/<site>/<sensor>/$health   qos=1, retain      heartbeat + LWT (status online/offline)
```

ACL en `aglabs_mosquitto` por `client_id` (= `<sensor_id>`). Cada Pi recibe usuario+password único; ambos viven en `bridge/.env` no commiteado.

### Almacenamiento local — SQLite WAL en la Pi, no Django app

**Decisión:** la Pi mantiene un SQLite WAL append-only con TODOS los eventos (consolidados + derivados) durante 30-90 días (configurable, default 90), rotado automáticamente. Cumple dos funciones:

- **Buffer durable** cuando MQTT/red están caídos. Los eventos se publican cuando vuelve la conexión sin pérdida.
- **Forense de profundidad** para post-mortem (atropello, fallo de actuador, anomalía sin diagnóstico claro desde Boreas).

**No** se expone vía HTTP/Django desde la Pi por defecto. Tres razones: superficie de ataque por dispositivo, complejidad de discovery/VPN/certs, baja frecuencia real del caso de uso forense. Acceso: SSH a la Pi (vía túnel Diana → RUT241 → LAN) + `sqlite3 /var/lib/radar_iot/events.sqlite` directamente.

**Excepción que reabriría el debate:** si la Pi controla actuadores reales (relé de semáforo, baliza), entonces sí justifica un endpoint mínimo FastAPI **solo lectura, solo autenticado, solo dentro VPN AGlabs**, que devuelva los últimos N eventos con el detalle "input → decisión → estado actuador → respuesta". Versión 2 como muy pronto.

### Reparto canónico de responsabilidades — el patrón que se reusa para futuras Pis IoT AGlabs

> **Edge (Pi):** decisiones tiempo real con latencia mínima sin depender de la red. Buffer durable. Forense local.
> **Bus (MQTT `mqtt.aglabs.es`):** hechos consolidados, configuración explícita, salud del nodo.
> **Centro (Boreas + Cortex + Vesta):** correlación cross-device, histórico, alarmas contextuales, facturación.

Este es el mismo patrón que usan Nexus, Diana, Lar y aglabs_mqtt — coherencia operativa cross-portfolio.

---

## Wrapper Docker — `bridge/`

Código fuente: [`bridge/aglabs_radar_bridge.py`](bridge/aglabs_radar_bridge.py) (~300 líneas Python 3.11, dependencia única `paho-mqtt==2.1.0`). Empaquetado en [`bridge/Dockerfile`](bridge/Dockerfile) sobre `python:3.11-slim` (multi-arch, vale para Pi 3/4/5 y para desarrollo en x86). Orquestado con [`bridge/docker-compose.yml`](bridge/docker-compose.yml).

### Anatomía

Cuatro hilos sobre un solo proceso Python:

| Hilo | Función |
|---|---|
| `tail` | Sigue `Vehicle_results.txt` por polling (`TAIL_POLL_MS` default 100). Persiste offset del fichero en SQLite (`meta.last_file_offset`) para sobrevivir a reinicios sin duplicar. Detecta rotación/truncado del fichero por cambio de inode. |
| `pub` | Drena la cola SQLite (filas con `published_at IS NULL`) y publica al broker MQTT con QoS 1 + `wait_for_publish`. Reintentos cada `PUBLISH_RETRY_INTERVAL_S`. |
| `hb` | Publica `$health` retained cada `HEARTBEAT_INTERVAL_S` (default 60s) con `uptime_s`, `queue_depth`, `last_detection_ts`, `wrapper_version`. |
| `maint` | Una vez al día, `DELETE` de eventos publicados con `ts` anteriores a `RETENTION_DAYS` (default 90). |

### Esquema SQLite

```sql
CREATE TABLE events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    external_event_id TEXT UNIQUE NOT NULL,    -- sha256(sensor|fw_raw)[:32]
    ts TEXT NOT NULL,                          -- ISO 8601 UTC
    suffix TEXT NOT NULL,                      -- 'track' | 'event'
    payload TEXT NOT NULL,                     -- JSON con el cuerpo MQTT
    published_at TEXT,                         -- NULL hasta confirmación MQTT
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
```

`external_event_id` UNIQUE → idempotencia: si el wrapper se reinicia entre escritura SQLite y publicación, el reintento usa el mismo id; si re-procesara la misma línea, el INSERT falla con `IntegrityError` (capturado, ignorado).

### Idempotencia hacia Boreas

`external_event_id` también va en el payload del topic `track`. Si Telegraf/Boreas implementan upsert por ese campo (patrón Vesta), un mensaje duplicado por red no genera fila duplicada. Por ahora Telegraf no lo hace; se documenta para cuando se diseñe la ingesta de `nexus_radar`.

### Variables de entorno

Ver [`bridge/.env.example`](bridge/.env.example). Las críticas:

| Variable | Default | Para qué |
|---|---|---|
| `RADAR_SITE` | `unknown_site` | Slug del emplazamiento — primer nivel del topic |
| `RADAR_SENSOR_ID` | `radar_iot_000` | ID del sensor — segundo nivel del topic Y `client_id` MQTT (debe ser único por dispositivo) |
| `RADAR_SPEED_LIMIT_KMH` | `0` (off) | Si >0, el wrapper genera evento derivado `speed_violation` para tipos 1/2/3 que superen el umbral |
| `RADAR_HIGHWAY_SCENARIO` | `false` | Solo informativo (publicado en `state`). El switch real está en el script del fabricante. **Mantener en `false` para uso urbano** (Regla §"Gotchas"). |
| `MQTT_HOST/PORT/TRANSPORT/PATH` | `mqtt.aglabs.es:443` WSS `/mqtt` | Broker AGlabs |
| `MQTT_USERNAME/PASSWORD` | sin default | Credenciales por sensor; ACL `aglabs_mosquitto` |
| `RADAR_RETENTION_DAYS` | `90` | Rotación SQLite |

### Volúmenes Docker

```yaml
volumes:
  - /home/pi/Desktop/uRAD_Tracking_v2_x/Results:/results:ro   # fichero del fabricante, read-only
  - radar_iot_data:/var/lib/radar_iot                          # SQLite persistente
```

**No tocar el servicio pm2 `radar` del fabricante.** Nuestro contenedor monta `Results/` en read-only — no puede dañarlo aunque haya un bug. Patrón AGlabs: cero acoplamiento con el firmware del proveedor.

### Cumplimiento de reglas globales (`/root/CLAUDE.md`)

- **Regla #1 (nombres servicio):** servicio se llama `radar_iot_bridge` (prefijado). No usa nombres genéricos.
- **Regla #3 (`restart: unless-stopped`):** sí.
- **Regla #6 (`mem_limit`):** sí, 256 MiB / 256 MiB. El proceso real consume ~40-60 MiB; 256 MiB deja margen para SQLite growth.
- **Política de documentación dual:** este CLAUDE.md y [`README.md`](README.md) se actualizan en paralelo (commit que añadió este bridge).

### Próximas iteraciones planificadas

| Versión | Añade |
|---|---|
| 0.1.0 (actual, 2026-05-28) | MVP — tail + SQLite WAL + MQTT WSS + speed_violation + heartbeat |
| 0.2.0 | Conflicto peatón-vehículo (ventana temporal en el wrapper). Deduplicación de objetos que paran. Interval summaries. |
| 0.3.0 | Migrar tail por polling a inotify (`watchdog`). |
| 0.4.0 | Endpoint admin FastAPI minimal (read-only, solo si se conectan actuadores). |

---

## Ingesta a Boreas — `schema/` y Telegraf

Para que los eventos del broker lleguen a `boreas_db`, hay dos piezas que viven en otros repos y se aplican vía sus agentes correspondientes:

- **Hypertable `nexus_radar`** — DDL de referencia en [`schema/nexus_radar.sql`](schema/nexus_radar.sql) + modelo Django listo para copiar en [`schema/boreas_django_model.py`](schema/boreas_django_model.py). El agente **Boreas** debe trasladarlo a migración Django (`makemigrations` + `migrate`) y completar manualmente `create_hypertable` + `add_compression_policy` + `add_retention_policy` que Django no emite. **Regla Hard #2 de Nexus**: nunca `CREATE TABLE` crudo en `boreas_db`.
- **Input + Starlark processor de Telegraf** — bloque autocontenido en [`schema/telegraf_radar_section.conf`](schema/telegraf_radar_section.conf) para pegar al final de [`/root/nexus/telegraf/telegraf.conf`](/root/nexus/telegraf/telegraf.conf). Después, añadir `"nexus_radar"` al array `namepass` del `[[outputs.postgresql]]` y `docker restart nexus_telegraf`.

El Starlark del bloque extrae el `ts` del payload JSON (timestamp del firmware, no de ingesta), aplana los campos a columnas de `nexus_radar`, normaliza `kind` ('track' del topic, 'speed_violation' del campo `kind` del payload de event), descarta los topics `state` y `$health` (que solo viven retained en el broker en v0.1).

Schema clave (campos relevantes — detalle completo en [`schema/nexus_radar.sql`](schema/nexus_radar.sql)):

| Columna | Tipo | Origen |
|---|---|---|
| `time` | TIMESTAMPTZ | `ts` del payload (UTC) |
| `device_id` | TEXT | `RADAR_SENSOR_ID` del wrapper, via topic |
| `site` | TEXT | `RADAR_SITE` del wrapper, via topic |
| `kind` | TEXT | `track` \| `speed_violation` \| futuros |
| `object_type` | SMALLINT | 1-5 firmware |
| `velocity_kmh`, `velocity_signed_kmh`, `direction`, `x_distance_m` | FLOAT/TEXT | datos del firmware |
| `external_event_id` | TEXT UNIQUE | sha256(sensor\|fw_raw)[:32] del wrapper |
| `fw_raw` | TEXT | línea original (forense) |

Idempotencia: el wrapper publica el mismo `external_event_id` en reintentos. El UNIQUE en `nexus_radar` evita duplicados a costa de un upsert futuro en Telegraf (v0.2 — hoy se acepta el INSERT-or-skip por el log de Telegraf).

## Prueba en LAN con Pi de desarrollo — sin sensor

Pensada para validar todo el pipeline antes de comprar el Smart Traffic real. Pasos resumidos (detalle en [`README.md`](README.md)):

1. `git clone` del repo en la Pi de pruebas.
2. `cd bridge && cp .env.example .env` y rellenar credenciales MQTT.
3. `cp docker-compose.override.yml.example docker-compose.override.yml` — apunta el bind-mount a `/tmp/radar_results/` en vez de la ruta del Smart Traffic.
4. En otra terminal: `python3 scripts/generate_synthetic_results.py --output /tmp/radar_results/Vehicle_results.txt --rate 6` (simulador con perfil realista de paso de peatones — peatones, bicis, vehículos a 20-45 km/h, con ~8% de infractores >45 km/h).
5. `docker compose up --build` — el bridge tail-ea el fichero sintético como si fuera real.
6. Verificar en MQTTX (`wss://mqtt.aglabs.es/mqtt`) los topics `aglabs/radar/<site>/<sensor>/{track,event,state,$health}`.

**Credencial MQTT de prueba:** `radar_iot_001` provisionada en `aglabs_mosquitto` desde 2026-05-28 (publish-only sobre `aglabs/radar/+/+/{track,event,state,$health}`). El password de v1 está guardado en la memoria del agente `aglabs_mqtt` (`mqtt_credentials.md`) y debe pegarse en `bridge/.env` del repo radar_iot — nunca commitear. Para registrar **el segundo sensor** (`radar_iot_002` etc.) la receta vive en [`/root/aglabs_mqtt/CLAUDE.md §"Usuarios MQTT (password_file + ACL)"`](../aglabs_mqtt/CLAUDE.md) — esencialmente: hash con `mosquitto_passwd`, copy/paste del bloque ACL de `radar_iot_001` cambiando el nombre, `docker restart aglabs_mosquitto`. Las ACL viven en `/root/aglabs_mqtt/mosquitto/config/aclfile` y los hashes en `/root/aglabs_mqtt/mosquitto/config/passwordfile` (ambos gitignored). El subscriber de Telegraf (`nexus_telegraf`) ya tiene `read` permitido sobre `aglabs/radar/#` — un sensor nuevo es invisible al broker hasta que se le da credencial+ACL, pero el momento que publique, Telegraf lo verá sin tocar nada.

## Estado actual (a 2026-05-28)

**Documentación + wrapper v0.1.0 + DDL + Telegraf + generador sintético, todo en repo (commit `Sonia 0.1`).** Sin hardware todavía. Pendiente:

- Aplicar migración `nexus_radar` en Boreas (esperando al agente Boreas).
- Extender `nexus_telegraf.conf` con `[[inputs.mqtt_consumer]]` apuntando a `tcp://aglabs_mosquitto:1883` (usuario `nexus_telegraf`, topics `aglabs/radar/#`) — esperando al agente Nexus. El usuario ya está provisionado en `aglabs_mosquitto`; password en memoria de Claude (`mqtt_credentials.md`).
- ~~Provisionar credencial `radar_iot_001` en `aglabs_mosquitto`~~ — hecho 2026-05-28.
- Adquirir Smart Traffic RPi + Teltonika RUT241 (esperando presupuesto Anteral).

**Siguientes pasos** (revisados 2026-05-28):

1. **Solicitar presupuesto a Anteral** (`contact@urad.es`) — 1 unidad de evaluación Smart Traffic RPi **sin dongle 4G** (Escenario B: la conectividad la aportará un Teltonika RUT241 gestionado por Diana). Preguntas concretas a Anteral en §"Gotchas" y en [`README.md`](README.md).
2. **Provisionar Teltonika RUT241** del inventario AGlabs vía Diana — coordenadas GPS del emplazamiento, SIM WirelessLogic, registro en `nexus_device`.
3. **Probar wrapper en bench** con un `Vehicle_results.txt` sintético antes de que llegue el sensor real — desde un x86 con Docker, apuntando a `mqtt.aglabs.es`. Validar que llegan los cuatro topics a MQTTX.
4. **Definir esquema de `nexus_radar`** (TimescaleDB hypertable) y parser en `nexus_telegraf` consumiendo los topics. DDL pendiente — debe alinearse con el payload v0.1.0 del wrapper.
5. **Primera vista "Tráfico"** en Boreas reusando componentes `nexus_*`.
6. **Primer cliente piloto:** concejo/ayuntamiento (perfil `gestor_concejo`).

---

## Gotchas a recordar

- **El sensor no es cliente MQTT nativo.** Hay que añadir nuestro wrapper Python en la RPi. La diferencia vs la variante modular es que **no hace falta hardware bridge externo** — solo software.
- **No tocar el servicio pm2 `radar`.** Es el del fabricante. Nuestro código va en un servicio adicional. Mantener separación para que un re-flash del firmware del proveedor no rompa nuestra integración.
- **Buffer local obligatorio.** Una caída de WiFi/4G no debe perder conteos. Cola local (SQLite, fichero append-only) en la RPi antes de la publicación MQTT.
- **La banda 60 GHz es ISM exenta en EU.** No requiere licencia ni tasas municipales. Certificación CE bajo examen tipo EU n.º 803416897303 (RED 3.1a, 3.1b, 3.2, RoHS).
- **Configuración por WiFi sólo en instalación/mantenimiento.** AP móvil con SSID `uRAD_SN****`. Una vez configurado, el dispositivo opera headless.
- **Temperatura recomendada -20 a +65 °C** (rango operativo declarado -20 a +80 °C). Hay un disipador interno + tapón de ventilación + ventilador PWM.
- **Modo highway vs urbano cambia la clasificación.** Con `HIGHWAY_SCENARIO=True` el firmware no separa bicicletas ni peatones — los reporta como tipo 1. Mantener `False` para uso municipal estándar.
- **Distancia máxima depende del modo.** 30 m para conteo, 100 m para detecciones en tiempo real (radar pedagógico, control de acceso). No mezclar expectativas.

---

## Política de documentación

Cualquier cambio funcional notable en este proyecto debe actualizarse en paralelo en este `CLAUDE.md` y en [`README.md`](README.md), por la política global de AGlabs (ver [`/root/CLAUDE.md §Política de documentación`](/root/CLAUDE.md)). El README es la cara pública del proyecto en GitHub; este CLAUDE.md es el contexto operativo para agentes IA.
