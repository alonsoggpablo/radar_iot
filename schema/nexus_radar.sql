-- =============================================================================
-- nexus_radar — hypertable para eventos del Smart Traffic RPi
--
-- NO ejecutar este SQL directamente contra boreas_db. Por Regla Hard #2 de
-- Nexus, los cambios de schema en boreas_db se hacen vía migración Django en
-- Boreas. Este fichero es DOCUMENTACIÓN del schema diseñado — el agente
-- Boreas debe traducirlo a un Model + makemigrations + migrate.
--
-- Modelo Django equivalente listo en `schema/boreas_django_model.py`.
-- =============================================================================

CREATE TABLE IF NOT EXISTS nexus_radar (
    time                  TIMESTAMPTZ      NOT NULL,
    device_id             TEXT             NOT NULL,     -- = RADAR_SENSOR_ID del wrapper
    site                  TEXT,                          -- = RADAR_SITE del wrapper
    kind                  TEXT             NOT NULL,     -- 'track' | 'speed_violation' | futuros
    object_type           SMALLINT,                      -- 1..5 según firmware
    type_label            TEXT,                          -- vehicle_normal|vehicle_medium|vehicle_long|bike_motorcycle|pedestrian
    velocity_kmh          DOUBLE PRECISION,              -- valor absoluto
    velocity_signed_kmh   DOUBLE PRECISION,              -- positivo=alejándose, negativo=acercándose
    direction             TEXT,                          -- 'approaching' | 'receding'
    x_distance_m          DOUBLE PRECISION,
    speed_limit_kmh       DOUBLE PRECISION,              -- solo para kind='speed_violation'
    external_event_id     TEXT             NOT NULL,
    fw_raw                TEXT                           -- línea original del Vehicle_results.txt (forense)
);

-- Hypertable con chunks de 1 día (consistente con nexus_measurement)
SELECT create_hypertable(
    'nexus_radar', 'time',
    chunk_time_interval => INTERVAL '1 day',
    if_not_exists       => TRUE
);

-- Índices
-- Patrón primario: WHERE device_id = ? AND kind = ? ORDER BY time DESC
CREATE INDEX IF NOT EXISTS idx_nexus_radar_device_kind_time
    ON nexus_radar (device_id, kind, time DESC);

-- Patrón secundario: scan por emplazamiento (aforo concejo, comparativa pasos)
CREATE INDEX IF NOT EXISTS idx_nexus_radar_site_time
    ON nexus_radar (site, time DESC) WHERE site IS NOT NULL;

-- Idempotencia hacia el wrapper: cada (sensor, fw_raw) genera un único id.
-- Telegraf debería ignorar conflictos por este UNIQUE en futuras versiones.
CREATE UNIQUE INDEX IF NOT EXISTS uq_nexus_radar_event_id
    ON nexus_radar (external_event_id);

-- Compresión a partir de 7 días (mismo patrón que nexus_measurement)
ALTER TABLE nexus_radar SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'device_id, kind',
    timescaledb.compress_orderby   = 'time DESC'
);

SELECT add_compression_policy(
    'nexus_radar',
    compress_after => INTERVAL '7 days',
    if_not_exists  => TRUE
);

-- Retención: 365 días en raw. Los continuous aggregates (siguiente versión)
-- pueden quedar más tiempo. Igual que nexus_measurement.
SELECT add_retention_policy(
    'nexus_radar',
    drop_after    => INTERVAL '365 days',
    if_not_exists => TRUE
);

COMMENT ON TABLE nexus_radar IS
    'Eventos del uRAD Smart Traffic RPi: detecciones consolidadas (kind=track) y derivados (kind=speed_violation, ...). Una fila por línea de Vehicle_results.txt o por evento derivado por el wrapper radar_iot_bridge.';

COMMENT ON COLUMN nexus_radar.device_id IS
    'Identificador del sensor (= RADAR_SENSOR_ID del wrapper, ej. radar_iot_001). Debe existir en nexus_device.';
COMMENT ON COLUMN nexus_radar.site IS
    'Slug del emplazamiento (= RADAR_SITE del wrapper, ej. concejo_oviedo_paso_independencia_3).';
COMMENT ON COLUMN nexus_radar.kind IS
    'Tipo de evento: track (objeto consolidado por firmware), speed_violation (derivado), futuros.';
COMMENT ON COLUMN nexus_radar.object_type IS
    'Clasificación firmware: 1=vehicle_normal, 2=vehicle_medium, 3=vehicle_long, 4=bike_motorcycle, 5=pedestrian.';
COMMENT ON COLUMN nexus_radar.external_event_id IS
    'Idempotency key sha256(sensor|fw_raw)[:32]. Generado por el wrapper.';
COMMENT ON COLUMN nexus_radar.fw_raw IS
    'Línea original de Vehicle_results.txt. Solo para forense — no usar en queries operativas.';
