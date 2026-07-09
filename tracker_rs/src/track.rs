//! Asociación y seguimiento de objetos entre frames.
//!
//! Primer corte deliberadamente simple para tener algo funcional contra el que
//! comparar la salida de Anteral:
//!   - asociación por **vecino más cercano** con *gating* (radio máximo),
//!   - suavizado de posición/velocidad tipo **alpha-beta**,
//!   - ciclo de vida por hits/misses (un track se confirma con `min_hits` y se
//!     cierra tras `max_misses` frames sin verse).
//!
//! TODO(dataset): con el dataset real de tráfico —
//!   1) sustituir alpha-beta por Kalman (nalgebra) con modelo de velocidad
//!      constante y gating por Mahalanobis,
//!   2) afinar `gate_m`/`max_misses`/`min_hits` comparando conteos con Anteral,
//!   3) manejar asociación multi-objeto (Hungarian) cuando haya varios puntos.

use crate::model::{Frame, Point};

#[derive(Debug, Clone)]
pub struct TrackerParams {
    pub gate_m: f64,     // radio de asociación (m)
    pub max_misses: u32, // frames sin actualizar antes de cerrar el track
    pub min_hits: u32,   // hits mínimos para considerarlo objeto real
    pub alpha: f64,      // suavizado de posición/velocidad (0..1)
}

impl Default for TrackerParams {
    fn default() -> Self {
        Self { gate_m: 2.5, max_misses: 8, min_hits: 3, alpha: 0.5 }
    }
}

#[derive(Debug, Clone)]
struct Track {
    id: u64,
    x: f64,
    y: f64,
    vx: f64,
    vy: f64,
    peak_abs_vel: f64,   // |velocidad radial| máxima observada (km/h)
    last_vel_signed: f64,
    xs: Vec<f64>,        // historial de x para mediana (estimación de carril)
    first_ts: f64,
    last_ts: f64,
    hits: u32,
    misses: u32,
}

/// Track ya cerrado, listo para clasificar y emitir.
#[derive(Debug, Clone)]
pub struct FinishedTrack {
    pub id: u64,
    pub first_ts: f64,
    pub last_ts: f64,
    pub hits: u32,
    pub median_x: f64,     // x_distance representativo (m)
    pub peak_abs_vel: f64, // km/h
    pub vel_signed: f64,   // última velocidad radial con signo (sentido)
    pub track_len_m: f64,  // recorrido longitudinal aproximado (m)
}

pub struct Tracker {
    p: TrackerParams,
    tracks: Vec<Track>,
    next_id: u64,
}

impl Tracker {
    pub fn new(p: TrackerParams) -> Self {
        Self { p, tracks: Vec::new(), next_id: 1 }
    }

    /// Procesa un frame y devuelve los tracks que se cierran en él.
    pub fn update(&mut self, frame: &Frame) -> Vec<FinishedTrack> {
        let n = self.tracks.len();
        let mut matched = vec![false; n];
        let mut spawns: Vec<Track> = Vec::new();

        for pt in &frame.points {
            // vecino más cercano entre los tracks previos aún sin emparejar
            let mut best: Option<usize> = None;
            let mut best_d = self.p.gate_m;
            for i in 0..n {
                if matched[i] {
                    continue;
                }
                let t = &self.tracks[i];
                let d = ((t.x - pt.x).powi(2) + (t.y - pt.y).powi(2)).sqrt();
                if d < best_d {
                    best_d = d;
                    best = Some(i);
                }
            }
            match best {
                Some(i) => {
                    self.update_track(i, pt, frame.ts);
                    matched[i] = true;
                }
                None => {
                    let id = self.next_id;
                    self.next_id += 1;
                    spawns.push(new_track(id, pt, frame.ts));
                }
            }
        }

        // envejecer los tracks previos no vistos; cerrar los que pasan max_misses
        let mut finished = Vec::new();
        let mut kept = Vec::new();
        for (i, mut t) in std::mem::take(&mut self.tracks).into_iter().enumerate() {
            if !matched[i] {
                t.misses += 1;
            }
            if t.misses > self.p.max_misses {
                if t.hits >= self.p.min_hits {
                    finished.push(finish(&t));
                }
            } else {
                kept.push(t);
            }
        }
        kept.extend(spawns);
        self.tracks = kept;
        finished
    }

    /// Cierra todos los tracks abiertos (fin de la reproducción / apagado).
    pub fn flush(&mut self) -> Vec<FinishedTrack> {
        let out = self
            .tracks
            .iter()
            .filter(|t| t.hits >= self.p.min_hits)
            .map(finish)
            .collect();
        self.tracks.clear();
        out
    }

    fn update_track(&mut self, i: usize, pt: &Point, ts: f64) {
        let a = self.p.alpha;
        let t = &mut self.tracks[i];
        t.vx = a * (pt.x - t.x) + (1.0 - a) * t.vx;
        t.vy = a * (pt.y - t.y) + (1.0 - a) * t.vy;
        t.x = a * pt.x + (1.0 - a) * t.x;
        t.y = a * pt.y + (1.0 - a) * t.y;
        t.xs.push(pt.x);
        t.last_vel_signed = pt.velocity;
        if pt.velocity.abs() > t.peak_abs_vel {
            t.peak_abs_vel = pt.velocity.abs();
        }
        t.last_ts = ts;
        t.hits += 1;
        t.misses = 0;
    }
}

fn new_track(id: u64, pt: &Point, ts: f64) -> Track {
    Track {
        id,
        x: pt.x,
        y: pt.y,
        vx: 0.0,
        vy: 0.0,
        peak_abs_vel: pt.velocity.abs(),
        last_vel_signed: pt.velocity,
        xs: vec![pt.x],
        first_ts: ts,
        last_ts: ts,
        hits: 1,
        misses: 0,
    }
}

fn finish(t: &Track) -> FinishedTrack {
    let mut xs = t.xs.clone();
    xs.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
    let median_x = if xs.is_empty() { 0.0 } else { xs[xs.len() / 2] };
    FinishedTrack {
        id: t.id,
        first_ts: t.first_ts,
        last_ts: t.last_ts,
        hits: t.hits,
        median_x,
        peak_abs_vel: t.peak_abs_vel,
        vel_signed: t.last_vel_signed,
        track_len_m: t.vy.abs() * (t.last_ts - t.first_ts).max(0.0),
    }
}
