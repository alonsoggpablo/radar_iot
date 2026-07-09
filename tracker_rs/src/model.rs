//! Modelo de datos de la nube de puntos del uRAD Industrial.
//!
//! Formato de `PointCloud.txt` (volcado por vehicleCounter con SAVE_RAW_DATA=True):
//!   `<cpu_cycles> <frame> <ts> <num_obj> [x y z velocity snr noise]×N`
//! (una línea por frame; `ts` es epoch en segundos con decimales; `velocity`
//! es la velocidad radial en km/h con signo: + alejándose, − acercándose).

/// Un punto detectado por el radar en un frame.
#[derive(Debug, Clone, Copy)]
pub struct Point {
    pub x: f64,        // posición lateral (m)   — sirve para carril
    pub y: f64,        // rango / distancia longitudinal (m)
    pub z: f64,        // altura (m)
    pub velocity: f64, // velocidad radial (km/h), con signo
    pub snr: f64,      // relación señal/ruido
    pub noise: f64,    // nivel de ruido
}

/// Un frame del radar: cabecera + los puntos detectados en él.
#[derive(Debug, Clone)]
pub struct Frame {
    pub cpu_cycles: u64,
    pub frame: u64,
    pub ts: f64, // epoch (s)
    pub points: Vec<Point>,
}
