# radar_iot_bridge — wrapper Docker que publica los eventos del Smart Traffic RPi a `mqtt.aglabs.es`

Tail-ea `Vehicle_results.txt` (escrito por el firmware Vehicle Monitoring v2.4 del fabricante), persiste cada evento a SQLite WAL local para post-mortem + buffer durable, y publica a cuatro topics MQTT.

## Quickstart en la Raspberry Pi del Smart Traffic

```bash
# Una sola vez:
cd /opt
sudo git clone https://github.com/<org>/radar_iot.git
cd radar_iot/bridge
sudo cp .env.example .env
sudo vim .env                    # rellenar site, sensor, credenciales MQTT
sudo docker compose up -d --build

# Verificar:
sudo docker logs -f radar_iot_bridge
```

## Variables de entorno

Ver `.env.example`. Las más importantes:

| Variable | Para qué |
|---|---|
| `RADAR_SITE` | slug del emplazamiento — entra en el topic MQTT |
| `RADAR_SENSOR_ID` | id del sensor — también `client_id` MQTT |
| `RADAR_SPEED_LIMIT_KMH` | si >0, genera evento `speed_violation` cuando un vehículo supera el umbral |
| `MQTT_HOST/PORT/TRANSPORT/PATH` | broker AGlabs — por defecto `wss://mqtt.aglabs.es:443/mqtt` |
| `MQTT_USERNAME/PASSWORD` | credenciales por sensor (ACL en Mosquitto AGlabs) |
| `RADAR_RETENTION_DAYS` | rotación del SQLite local |

## Topics emitidos

```
aglabs/radar/<site>/<sensor>/track     qos=1, no-retain   un mensaje por objeto
aglabs/radar/<site>/<sensor>/event     qos=1, no-retain   speed_violation (v0.1)
aglabs/radar/<site>/<sensor>/state     qos=1, retain      snapshot de config
aglabs/radar/<site>/<sensor>/$health   qos=1, retain      heartbeat + LWT
```

LWT: el broker publica `{"status":"offline"}` retained en `$health` si el cliente desaparece sin desconectar limpiamente.

## Post-mortem local

```bash
sudo docker exec -it radar_iot_bridge sqlite3 /var/lib/radar_iot/events.sqlite
> SELECT ts, suffix, json_extract(payload,'$.type_label') AS type, \
>        json_extract(payload,'$.velocity_kmh') AS v_kmh \
> FROM events WHERE ts > '2026-05-28T14:00:00Z' ORDER BY ts;
```

## Versiones

- `0.1.0` (2026-05-28) — MVP: tail + SQLite WAL + MQTT WSS + speed_violation derivation + heartbeat retained.

Próximas iteraciones documentadas en `/root/radar_iot/CLAUDE.md` §"Wrapper Docker".
