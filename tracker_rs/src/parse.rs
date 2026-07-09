//! Parser del formato de texto `PointCloud.txt`.
//!
//! `<cpu_cycles> <frame> <ts> <num_obj> [x y z velocity snr noise]×N`
//!
//! El 4º campo (`num_obj`) es el que declara el firmware; NO nos fiamos de él,
//! consumimos los campos reales que vengan en grupos de 6. Frames sin puntos
//! (solo cabecera) devuelven un `Frame` con `points` vacío — son válidos y el
//! tracker los usa para envejecer/cerrar tracks.

use crate::model::{Frame, Point};

const POINT_FIELDS: usize = 6; // x y z velocity snr noise

/// Parsea una línea. Devuelve `None` si la cabecera no es parseable.
pub fn parse_line(line: &str) -> Option<Frame> {
    let f: Vec<&str> = line.split_whitespace().collect();
    if f.len() < 4 {
        return None;
    }
    let cpu_cycles = f[0].parse().ok()?;
    let frame = f[1].parse().ok()?;
    let ts = f[2].parse().ok()?;

    let mut points = Vec::new();
    for chunk in f[4..].chunks(POINT_FIELDS) {
        if chunk.len() < POINT_FIELDS {
            break; // cola incompleta: ignorar
        }
        let p = Point {
            x: chunk[0].parse().ok()?,
            y: chunk[1].parse().ok()?,
            z: chunk[2].parse().ok()?,
            velocity: chunk[3].parse().ok()?,
            snr: chunk[4].parse().ok()?,
            noise: chunk[5].parse().ok()?,
        };
        points.push(p);
    }
    Some(Frame { cpu_cycles, frame, ts, points })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn header_only_frame() {
        let fr = parse_line("336013266 1 1783593647.979 1").unwrap();
        assert_eq!(fr.frame, 1);
        assert!(fr.points.is_empty());
    }

    #[test]
    fn one_point_frame() {
        // ejemplo real capturado el 2026-07-09 (objeto a 11.4 m, 23.6 km/h)
        let fr = parse_line("2410990465 638 1783593679.904 1 -3.365 11.382 1.495 23.561 74 421").unwrap();
        assert_eq!(fr.points.len(), 1);
        assert!((fr.points[0].y - 11.382).abs() < 1e-6);
        assert!((fr.points[0].velocity - 23.561).abs() < 1e-6);
    }
}
