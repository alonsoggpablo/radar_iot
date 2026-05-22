# Radar IoT

Planteamiento de integración del sensor radar **uRAD Smart Radar Sensor** (60 GHz FMCW, fabricado por Anteral) en la plataforma IoT de AGlabs.

Página técnica estática publicada en **<https://aglabs.es/radar_iot/>**.

## Propósito

Documentar internamente y enseñar a clientes cómo encajaría el sensor uRAD en la stack AGlabs:

- **Casos de uso:** pasos de peatones inteligentes, radar pedagógico / control de velocidad, aforo de bicicletas en carril bici, aforo multicarril de tráfico para municipios.
- **Arquitectura propuesta:** sensor en columna (RS-485) → bridge ESP32/Teltonika (MQTT/TLS) → broker `mqtt.aglabs.es` → ingesta Telegraf → hypertable `nexus_radar` en TimescaleDB → vista "Tráfico" en Boreas.
- **Reutiliza la infra existente:** Mosquitto del proyecto `aglabs_mqtt`, Telegraf de Nexus, dashboards de Boreas, alarmas de Cortex.

## Stack

| Componente | Detalle |
|------------|---------|
| Página | HTML estático + CSS heredado de `https://aglabs.es/static/portal/aglabs.css` |
| Servida por | `boreas_nginx` (bind-mount `/root/radar_iot/web → /app/radar_iot_web:ro`) |
| Patrón URL | path-based bajo `aglabs.es/radar_iot/` (sin subdominio, sin cert nuevo) |
| Registrada en AG | `App(slug='radar_iot')` + `AppItem(slug='home', kind='external', section='proyectos')` |
| Audiencia | `restricted_to_users` = pablo, jose, pravia |

## El sensor en cifras

| Parámetro | Valor |
|-----------|-------|
| Tecnología | Radar microondas FMCW |
| Frecuencia | 60 – 64 GHz (banda ISM exenta en EU) |
| Potencia / FoV | 15 dBm / 160 ° |
| Alcance | ≤ 100 m |
| Velocidad máxima | 180 km/h |
| Alimentación | 8 – 42 V DC · 0,5 – 2,5 W |
| Interfaces | RS-485 · UART · 2× GPIO opto · WiFi (config) |
| Protección | IP66 · NEMA 4X / 12 / 13 · UL-508 |
| Temperatura | -20 a +80 °C |

Datasheet completo del fabricante: <https://urad.es/wp-content/descargables/uRAD%20-%20Datasheet%20-%20Smart%20Radar%20Sensor%20-%20ES.pdf>

## Estado

**Solo documentación a 2026-05-22.** No hay hardware adquirido ni desarrollo iniciado. Para detalles operativos, arquitectura completa, topics MQTT, BOM y gotchas, ver [`CLAUDE.md`](CLAUDE.md) y la propia página [`web/index.html`](web/index.html).

## Editar la página

```bash
# Modificar y publicar (nginx la sirve directamente, sin restart):
vim /root/radar_iot/web/index.html
```

Los SVG de icono y favicon viven en [`web/icon.svg`](web/icon.svg) (cobre, para el card del portal AG) y [`web/favicon.svg`](web/favicon.svg) (tinta oscura, para la pestaña del navegador).
