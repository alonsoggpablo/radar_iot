# Radar IoT

Planteamiento de integración del **uRAD Smart Traffic RPi** (radar 60 GHz FMCW con Raspberry Pi embebida, fabricado por Anteral) en la plataforma IoT de AGlabs.

Página técnica estática publicada en **<https://aglabs.es/radar_iot/>**.

## Propósito

Documentar internamente y enseñar a clientes cómo encajaría el Smart Traffic RPi en la stack AGlabs:

- **Casos de uso:** aforo multicarril de tráfico para municipios, radar pedagógico / control de velocidad, aforo de bicicletas en carril bici, detección de peatones en pasos de cebra.
- **Arquitectura propuesta:** dispositivo único en columna (radar + RPi en la misma caja IP66) → cliente MQTT/TLS sobre WiFi o 4G → broker `mqtt.aglabs.es` → ingesta Telegraf → hypertable `nexus_radar` en TimescaleDB → vista "Tráfico" en Boreas.
- **Sin bridge externo:** la Raspberry Pi embebida hace de "bridge" — un segundo servicio pm2 en la propia RPi publica los eventos a MQTT.
- **Reutiliza la infra existente:** Mosquitto del proyecto `aglabs_mqtt`, Telegraf de Nexus, dashboards de Boreas, alarmas de Cortex.

## Stack

| Componente | Detalle |
|------------|---------|
| Página | HTML estático + CSS heredado de `https://aglabs.es/static/portal/aglabs.css` |
| Servida por | `boreas_nginx` (bind-mount `/root/radar_iot/web → /app/radar_iot_web:ro`) |
| Patrón URL | path-based bajo `aglabs.es/radar_iot/` (sin subdominio, sin cert nuevo) |
| Registrada en AG | `App(slug='radar_iot')` + `AppItem(slug='home', kind='external', section='proyectos')` |
| Audiencia | `restricted_to_users` = pablo, jose, pravia |

## El dispositivo en cifras

| Parámetro | Valor |
|-----------|-------|
| Hardware / firmware | Smart Traffic RPi v2.0 · Vehicle Monitoring v2.4 (28/10/2025) |
| Tecnología | Radar microondas FMCW + RPi embebida |
| Frecuencia | 60 – 64 GHz (banda ISM exenta en EU) |
| Potencia / FoV | 15 dBm / 160 ° |
| Alcance | 30 m (conteo) · 100 m (otras apps) |
| Velocidad máxima | 180 km/h |
| Distancia lateral | ± 15 m (precisión óptima ± 8 m) |
| Carriles | Hasta 4 con un radar (3 a un sentido) · 6 con precisión degradada |
| Alimentación | 8 – 40 V DC · 4,5 W |
| Procesador | Quad-core ARM Cortex-A72 · 1,8 GHz · 2 GB SDRAM · Linux |
| Conectividad | WiFi nativo · 4G LTE (dongle Huawei opcional) |
| Dimensiones | 171 × 121 × 80 mm · 1,1 kg |
| Protección | IP66 · NEMA 4X / 12 / 13 · UL-508 · UL94 HB |
| Temperatura | -20 a +80 °C (recomendado -20 a +65 °C) |
| Clasificación | normal · medio · largo · bici/moto · peatón (modos urbano y highway) |

Datasheet del fabricante: <https://urad.es/wp-content/descargables/uRAD%20-%20Datasheet%20-%20Smart%20Traffic%20RPi%20-%20ES.pdf>

## Arquitectura de despliegue

Decisión tomada el 2026-05-28. Para detalle operativo y razonamiento, ver [`CLAUDE.md §Conectividad y despliegue`](CLAUDE.md).

```
┌── Emplazamiento (paso de peatones) ──────────────────────────────────┐
│                                                                       │
│   Smart Traffic RPi                Teltonika RUT241                   │
│   ┌────────────────────┐   WiFi/   ┌──────────────────┐               │
│   │ radar 60 GHz + RPi │ ────────► │ 4G WirelessLogic │ ──────────────┼──── VPN OpenVPN ──► Diana
│   │ pm2 svc 'radar'    │   eth     │ gestionado por   │               │                    (inventario,
│   │   ↓ Vehicle_results│           │ Diana            │               │                     forense SSH)
│   │ docker container   │           └──────────────────┘               │
│   │ radar_iot_bridge   │                                              │
│   │   ↓ paho-mqtt WSS  │                                              │
│   └────────┬───────────┘                                              │
└────────────┼──────────────────────────────────────────────────────────┘
             │ wss://mqtt.aglabs.es:443/mqtt
             ▼
       ┌──────────────────┐    ┌──────────┐    ┌────────────────────────┐
       │ aglabs_mosquitto │ ─► │ Telegraf │ ─► │ Boreas hypertable      │
       │ (mqtt.aglabs.es) │    │ (nexus)  │    │ nexus_radar (Timescale)│
       └──────────────────┘    └──────────┘    └─────────┬──────────────┘
                                                          │
                                                          ▼
                                              Vista "Tráfico" en Boreas
                                              + alarmas Cortex
                                              + facturación Vesta
```

**Resumen del reparto de responsabilidades:**

- **Edge (Pi del Smart Traffic):** firmware del fabricante hace tracking + clasificación; wrapper Docker propio (`bridge/`) tail-ea el fichero, persiste a SQLite WAL local (post-mortem + buffer durable), publica a MQTT.
- **Conectividad 4G:** Teltonika RUT241 separado, gestionado por Diana — reutiliza VPN, SIMs, monitorización de la flota AGlabs.
- **Bus MQTT:** `wss://mqtt.aglabs.es:443/mqtt` (WebSocket sobre TLS por 443; el listener 8883 no está expuesto al exterior aún).
- **Centro (Boreas):** hypertable `nexus_radar`, vista "Tráfico", correlación cross-device, facturación a Vesta.

## El wrapper Docker — `bridge/`

Primera versión funcional **v0.1.0** publicada el 2026-05-28 en [`bridge/`](bridge/). Stack: Python 3.11 + `paho-mqtt` + SQLite WAL, ~300 líneas, una sola dependencia externa.

| Fichero | Para qué |
|---|---|
| [`bridge/aglabs_radar_bridge.py`](bridge/aglabs_radar_bridge.py) | Wrapper completo — 4 hilos (tail, publisher, heartbeat, maintenance) |
| [`bridge/Dockerfile`](bridge/Dockerfile) | Imagen `python:3.11-slim` multi-arch |
| [`bridge/docker-compose.yml`](bridge/docker-compose.yml) | Servicio `radar_iot_bridge`, `restart: unless-stopped`, `mem_limit: 256m` |
| [`bridge/.env.example`](bridge/.env.example) | Plantilla de variables — copiar a `.env` y rellenar `RADAR_SITE`, `RADAR_SENSOR_ID`, `MQTT_USERNAME`, `MQTT_PASSWORD` |
| [`bridge/README.md`](bridge/README.md) | Quickstart de despliegue en la Pi |

**Topics MQTT que emite (sobre `aglabs/radar/<site>/<sensor>/`):**

| Topic | Cuándo | Retained |
|---|---|---|
| `…/track` | un mensaje por objeto consolidado por el firmware (peatón, bici, vehículo) | no |
| `…/event` | derivados — `speed_violation` en v0.1, futuros conflictos peatón-vehículo en v0.2 | no |
| `…/state` | snapshot de configuración activa, en startup y en cambios | sí |
| `…/$health` | heartbeat cada 60 s + Last Will & Testament al desconectar | sí |

## Ingesta a Boreas — DDL y Telegraf

Para que los eventos publicados al broker AGlabs aparezcan en `boreas_db`:

1. **Crear la hypertable `nexus_radar`** vía migración Django en Boreas. DDL de referencia y modelo Django listos en [`schema/`](schema/).
2. **Extender `nexus_telegraf`** con el bloque de input + Starlark de [`schema/telegraf_radar_section.conf`](schema/telegraf_radar_section.conf).
3. Detalle paso a paso en [`schema/README.md`](schema/README.md).

## Prueba en LAN con Raspberry Pi de desarrollo (sin sensor real)

Permite validar todo el pipeline antes de que llegue el Smart Traffic:

```bash
# 1) En la Pi de pruebas:
git clone https://github.com/alonsoggpablo/radar_iot.git
cd radar_iot/bridge
cp .env.example .env  &&  vim .env             # rellenar SITE, SENSOR_ID, credenciales MQTT

# Override del bind-mount real por una carpeta sintética
cp docker-compose.override.yml.example docker-compose.override.yml

# 2) Generador sintético en otra terminal (fuera del contenedor):
mkdir -p /tmp/radar_results
python3 ../scripts/generate_synthetic_results.py \
    --output /tmp/radar_results/Vehicle_results.txt --rate 6

# 3) Arrancar el bridge:
docker compose up --build

# 4) Suscribirse desde MQTTX (https://mqtt.aglabs.es) a:
#    aglabs/radar/+/+/+
# Deberías ver:
#   - mensajes en .../track cada ~6 segundos en media
#   - alguna .../event speed_violation (los infractores van a 45-65 km/h)
#   - .../state retained al arrancar
#   - .../$health retained cada 60 segundos
```

**Credenciales MQTT para la prueba:** si todavía no hay usuario `radar_iot_001` en el ACL de `aglabs_mosquitto`, pídelo al agente `aglabs_mqtt` (`/root/aglabs_mqtt`) o arranca un Mosquitto local en la LAN apuntando ahí — el wrapper acepta cualquier host en `MQTT_HOST`.

**Inspeccionar SQLite local en la Pi:**

```bash
docker exec -it radar_iot_bridge sqlite3 /var/lib/radar_iot/events.sqlite \
    "SELECT ts, suffix, json_extract(payload,'$.type_label') AS type, \
            json_extract(payload,'$.velocity_kmh') AS v_kmh \
     FROM events ORDER BY ts DESC LIMIT 20;"
```

## Estado

**Documentación + wrapper v0.1.0 listos, sin hardware todavía.** Próximos pasos detallados en [`CLAUDE.md §Estado actual`](CLAUDE.md).

**2026-06-11 — primer Pi real (radar_iot_001, vía Atlas):** el wrapper se desplegó
end-to-end en un Pi tras un RUT. Dos hallazgos (ver `CLAUDE.md §Formato de
Vehicle_results.txt`): (1) el `timestamp` real de Anteral es `yyyy/mm/dd HH:MM:SS`
(2 tokens) — `parse_line` ya lo soporta, validado inyectando líneas reales →
`track`/`event` por MQTT; (2) **bloqueo de vendor**: el Tracking de Anteral
crashea con numpy 2.x al procesar detecciones (v2.4 y v2.3), pendiente de un build
compatible de Anteral — hasta entonces no fluyen detecciones reales.

## Editar la página

```bash
# Modificar y publicar (nginx la sirve directamente, sin restart):
vim /root/radar_iot/web/index.html
```

Los SVG de icono y favicon viven en [`web/icon.svg`](web/icon.svg) (cobre, para el card del portal AG) y [`web/favicon.svg`](web/favicon.svg) (tinta oscura, para la pestaña del navegador).
