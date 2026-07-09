//! radar_tracker — tracker propio de nube de puntos del uRAD Industrial.
//!
//! Objetivo: sustituir el `do_tracking` compilado de Anteral (que crashea con
//! numpy y se cuelga) por un procesado propio, robusto y ajustable. La nube de
//! puntos cruda ya es accesible (la arma el Python abierto de Anteral / se puede
//! leer del serie), así que solo reimplementamos la asociación + clasificación.
//!
//! Uso:
//!   radar_tracker replay <PointCloud.txt>   # reproduce un dump y saca vehículos
//!   radar_tracker serve                     # (TODO) ingesta serie en vivo + MQTT
//!
//! `replay` imprime en stdout las líneas de vehículo (formato Anteral, listas
//! para el pipeline) y un resumen por stderr — pensado para validar contra la
//! salida de Anteral sobre los MISMOS frames.

mod classify;
mod model;
mod output;
mod parse;
mod track;

use std::io::BufRead;

fn main() {
    let args: Vec<String> = std::env::args().collect();
    match args.get(1).map(String::as_str) {
        Some("replay") => match args.get(2) {
            Some(path) => replay(path),
            None => {
                eprintln!("uso: radar_tracker replay <PointCloud.txt>");
                std::process::exit(2);
            }
        },
        Some("serve") => {
            eprintln!(
                "serve: pendiente — ingesta serie en vivo (serialport, config 115200 / \
                 data 921600, /dev/serial0) + publicación MQTT. Ver README §Roadmap."
            );
            std::process::exit(1);
        }
        _ => {
            eprintln!("uso: radar_tracker replay <PointCloud.txt> | serve");
            std::process::exit(2);
        }
    }
}

fn replay(path: &str) {
    let file = match std::fs::File::open(path) {
        Ok(f) => f,
        Err(e) => {
            eprintln!("no puedo abrir {path}: {e}");
            std::process::exit(1);
        }
    };

    let mut tracker = track::Tracker::new(track::TrackerParams::default());
    let (mut nframes, mut npoints, mut nveh) = (0u64, 0u64, 0u64);
    let mut by_type = [0u64; 6]; // índices 1..5

    let mut emit = |ft: &track::FinishedTrack, by_type: &mut [u64; 6], nveh: &mut u64| {
        let ty = classify::classify(ft) as usize;
        by_type[ty] += 1;
        *nveh += 1;
        println!("{}", output::vehicle_line(ft));
    };

    for line in std::io::BufReader::new(file).lines().map_while(Result::ok) {
        if let Some(frame) = parse::parse_line(&line) {
            nframes += 1;
            npoints += frame.points.len() as u64;
            for ft in tracker.update(&frame) {
                emit(&ft, &mut by_type, &mut nveh);
            }
        }
    }
    for ft in tracker.flush() {
        emit(&ft, &mut by_type, &mut nveh);
    }

    eprintln!("--- resumen: frames={nframes} puntos={npoints} vehiculos={nveh} ---");
    eprintln!(
        "  por tipo: normal={} medio={} largo={} bici/moto={} peaton={}",
        by_type[1], by_type[2], by_type[3], by_type[4], by_type[5]
    );
}
