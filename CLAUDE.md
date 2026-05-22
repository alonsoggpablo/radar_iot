# Radar IoT — planteamiento de integración del sensor uRAD en AGlabs

Documento técnico estático que propone cómo integrar el **uRAD Smart Radar Sensor** (Anteral, 60 GHz FMCW) en la plataforma IoT de AGlabs vía bridge RS-485 → MQTT.

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

uRAD Smart Radar Sensor — radar microondas 60 GHz FMCW con caja IP66 (115 × 90 × 65 mm, 560 g), alcance 100 m, velocidad ≤ 180 km/h, alimentación 8-42 V DC (0,5-2,5 W). Salidas RS-485 + UART + 2× GPIO optoacoplados. Configuración por WiFi (AP local con app web). Fabricado por **Anteral S.L.** (Huarte, Navarra) — [urad.es](https://urad.es). Datasheet base: <https://urad.es/wp-content/descargables/uRAD%20-%20Datasheet%20-%20Smart%20Radar%20Sensor%20-%20ES.pdf> (versión 20/10/2025).

Trae **tres aplicaciones** preinstalables cargables por WiFi:
1. Detección de velocidad y distancia en tiempo real (multi-carril, ID único por vehículo).
2. Detección específica de bicicletas (carril configurable, GPIO de aviso).
3. Detección de peatones en paso de cebra (área y sensibilidad configurables, GPIO de aviso).

---

## Arquitectura propuesta (resumen — el detalle vive en `index.html`)

```
[uRAD radar]──RS-485──[Bridge ESP32 + MAX485]──MQTT/TLS──[mqtt.aglabs.es]
   │GPIO opto                                                    │
   ▼                                                             ▼
[Señalización local]                            [Telegraf → nexus_radar]
                                                             │
                                                             ▼
                                                  [Boreas — vista Tráfico]
```

- **Nivel 1 — sensor en columna.** RS-485 + GPIO opto. Configuración WiFi local.
- **Nivel 2 — bridge.** ESP32 industrial DIN + transceiver MAX485 (caso económico), o Teltonika RUT241 con conversor RS-485↔IP (caso robusto con 4G LTE). Publica MQTT/TLS con QoS 1 y LWT.
- **Nivel 3 — broker AGlabs (`mqtt.aglabs.es`)**. Reusa el Mosquitto ya operativo del proyecto `aglabs_mqtt`. Cero infra nueva de mensajería.
- **Nivel 4 — Boreas.** Ingesta vía `nexus_telegraf` a hypertable nueva `nexus_radar`. Visualización en vista "Tráfico" embebida en Boreas, alarmas reusando Cortex.

**Topics MQTT propuestos:**

```
aglabs/radar/<site>/<sensor>/track   # cada objeto detectado con velocidad/distancia/id
aglabs/radar/<site>/<sensor>/event   # cruces de umbral, GPIO actuado, etc.
aglabs/radar/<site>/<sensor>/state   # configuración activa, app cargada
aglabs/radar/<site>/<sensor>/$health # LWT + heartbeat
```

Payload JSON, timestamp ISO 8601 UTC. ACL Mosquitto por `client_id` (ya implementado en `aglabs_mqtt`).

---

## Estado actual (a 2026-05-22)

**Solo documentación.** No hay sensor adquirido todavía. No hay bridge desarrollado. No hay hypertable `nexus_radar`. La página es un planteamiento para alinear a AGlabs internamente y para enseñar a clientes potenciales.

**Siguientes pasos** (también listados en §06 de `index.html`):

1. Adquirir 1 unidad de evaluación con caja IP66 (presupuesto a Anteral).
2. Prototipar el bridge con ESP32 + MAX485, reusando la base del bridge Tactica de `aglabs_mqtt`.
3. Definir esquema de `nexus_radar` y parser en `nexus_telegraf`.
4. Primera vista "Tráfico" en Boreas reusando componentes `nexus_*`.
5. Primer cliente piloto: concejo/ayuntamiento (perfil `gestor_concejo`).

---

## Gotchas a recordar

- **No es cliente MQTT nativo.** El sensor habla RS-485 con un protocolo propio del fabricante; el bridge es obligatorio.
- **GPIO opto debe cerrar el lazo local, no remoto.** La señalización (semáforo, baliza) se activa directamente por el GPIO del sensor en < 50 ms, sin depender del broker. MQTT es para registro/dashboard. Esto preserva seguridad funcional ante caída de red.
- **La banda 60 GHz es ISM exenta en EU.** No requiere licencia ni tasas municipales para uso de espectro.
- **Configuración por WiFi sólo en instalación.** Una vez configurado, el sensor opera headless por RS-485. El AP WiFi es para uso de campo del instalador.
- **Caja propia obligatoria en columna.** Aunque la caja del sensor es IP66, el bridge necesita una caja IP65 anexa para electrónica + fuente + protecciones.

---

## Política de documentación

Cualquier cambio funcional notable en este proyecto debe actualizarse en paralelo en este `CLAUDE.md` y en [`README.md`](README.md), por la política global de AGlabs (ver [`/root/CLAUDE.md §Política de documentación`](/root/CLAUDE.md)). El README es la cara pública del proyecto en GitHub; este CLAUDE.md es el contexto operativo para agentes IA.
