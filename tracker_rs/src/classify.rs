//! Clasificación de un track cerrado en tipo de objeto.
//!
//! Categorías Anteral: 1=normal, 2=medio, 3=largo, 4=bici/moto, 5=peatón.
//!
//! LIMITACIÓN CONOCIDA: el uRAD entrega ~1 punto por objeto, así que **no se
//! puede medir la longitud del vehículo de forma fiable** (que es como Anteral
//! separa normal/medio/largo). Con esta señal escasa lo robusto es clasificar
//! por **velocidad + persistencia**; la longitud queda como heurística débil.
//! TODO(dataset): calibrar umbrales comparando con la salida de Anteral sobre
//! los mismos frames; si el número de puntos/duración correlaciona con longitud,
//! usarlo.

use crate::track::FinishedTrack;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[repr(u8)]
pub enum VehicleType {
    Normal = 1,
    Medium = 2,
    Long = 3,
    BikeMoto = 4,
    Pedestrian = 5,
}

/// Umbral de velocidad (km/h) por debajo del cual se considera peatón (doc Anteral).
const PEDESTRIAN_KMH: f64 = 10.0;

pub fn classify(t: &FinishedTrack) -> VehicleType {
    // Peatón: velocidad baja.
    if t.peak_abs_vel < PEDESTRIAN_KMH {
        return VehicleType::Pedestrian;
    }
    // Sin longitud fiable, el resto cae a 'normal' por ahora.
    // TODO(dataset): distinguir bici/moto y medio/largo con features derivadas
    // (nº de puntos, duración del track, dispersión en y).
    VehicleType::Normal
}
