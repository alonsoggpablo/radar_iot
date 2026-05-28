# schema — DDL y configuraciones para integrar `nexus_radar` en Boreas + Nexus

Contenido pensado para que el agente **Boreas** y el agente **Nexus** lo apliquen.
**No ejecutar nada de esto contra `boreas_db` directamente** — Regla Hard #2 de
Nexus (`/root/nexus/CLAUDE.md`): todos los cambios de schema van por migración Django.

## Ficheros

| Fichero | Para qué | Quién lo aplica |
|---|---|---|
| [`nexus_radar.sql`](nexus_radar.sql) | DDL de referencia de la hypertable | Boreas (traducir a migración) |
| [`boreas_django_model.py`](boreas_django_model.py) | Modelo Django equivalente, listo para copiar a la app de Nexus en Boreas | Boreas (`makemigrations` + `migrate`) |
| [`telegraf_radar_section.conf`](telegraf_radar_section.conf) | Bloque de input + Starlark processor para `/root/nexus/telegraf/telegraf.conf` | Nexus (`docker restart nexus_telegraf`) |

## Orden de aplicación

1. **Boreas crea la tabla** vía migración Django:
   - Copia `boreas_django_model.py::NexusRadar` a los modelos de la app Nexus en Boreas (probablemente `boreas_app/mediacion/models.py`).
   - `docker exec boreas_app python manage.py makemigrations`
   - `docker exec boreas_app python manage.py migrate`
   - **Después** ejecuta el bloque TimescaleDB (hypertable + compresión + retención) de `nexus_radar.sql` — Django no lo genera. Hacerlo como `RunPython` en la propia migración o a mano tras `migrate`.

2. **Nexus añade el input + processor**:
   - Pega el contenido de `telegraf_radar_section.conf` al final de la sección INPUTS y de la sección PROCESSORS de `/root/nexus/telegraf/telegraf.conf`.
   - Añade `"nexus_radar"` al array `namepass` del `[[outputs.postgresql]]` final.
   - `docker restart nexus_telegraf`
   - Verificar logs: `docker logs -f nexus_telegraf | grep -i radar`

3. **Registrar el sensor en `nexus_device`** (opcional pero recomendado):
   ```sql
   INSERT INTO nexus_device (device_id, alias, site, typology, vendor, model, active)
   VALUES ('radar_iot_001', 'Paso Independencia 3', 'concejo_oviedo_paso_independencia_3',
           'radar', 'Anteral', 'uRAD Smart Traffic RPi v2.0', TRUE)
   ON CONFLICT (device_id) DO UPDATE SET updated_at = NOW();
   ```

## Probar antes de tener sensor real

Usar [`scripts/generate_synthetic_results.py`](../scripts/generate_synthetic_results.py) para producir un `Vehicle_results.txt` falso en la Pi de pruebas. El wrapper lo tail-ea como si fuera el firmware real → publica a `mqtt.aglabs.es` → Telegraf ingresa a `nexus_radar`.
