//! Salida de vehículos.
//!
//! Formato compatible con Anteral (`Vehicle_results.txt`): así el bridge y todo
//! el pipeline (MQTT → nexus_radar → Boreas) lo consumen SIN cambios:
//!   `<epoch> <velocity_signed> <x_distance> <type>`
//!
//! Fase 2 (serve en vivo): publicar el track directamente a
//! `aglabs/radar/<site>/<sensor>/track` con el mismo payload JSON que el bridge
//! (ver `/root/radar_iot/bridge/aglabs_radar_bridge.py::parse_line`) y saltarnos
//! el fichero + el tail. Stub abajo.

use crate::classify::{classify, VehicleType};
use crate::track::FinishedTrack;

/// Línea estilo Anteral. `epoch` = último timestamp del track; `velocity_signed`
/// conserva el sentido (− acercándose, + alejándose).
pub fn vehicle_line(t: &FinishedTrack) -> String {
    let ty = classify(t) as u8;
    format!("{:.0} {:.2} {:.2} {}", t.last_ts, t.vel_signed, t.median_x, ty)
}

/// Etiqueta legible (para logs/depuración).
pub fn type_label(t: &FinishedTrack) -> &'static str {
    match classify(t) {
        VehicleType::Normal => "vehicle_normal",
        VehicleType::Medium => "vehicle_medium",
        VehicleType::Long => "vehicle_long",
        VehicleType::BikeMoto => "bike_motorcycle",
        VehicleType::Pedestrian => "pedestrian",
    }
}

// TODO(fase serve): fn publish_mqtt(client, site, sensor, t: &FinishedTrack)
//   → topic aglabs/radar/{site}/{sensor}/track, payload JSON idéntico al bridge.
