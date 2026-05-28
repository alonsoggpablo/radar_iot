"""Generador sintético de Vehicle_results.txt para probar el wrapper sin sensor.

Emula el firmware Vehicle Monitoring v2.4 del uRAD Smart Traffic RPi:
escribe una línea cada vez que "detecta" un objeto, con la firma temporal
de un paso de peatones realista (peatones cruzando, bicis, coches a 30-50 km/h,
algún coche infractor por encima del límite).

Uso (en la Raspberry Pi de pruebas, fuera del contenedor):

    mkdir -p /tmp/radar_results
    python3 scripts/generate_synthetic_results.py \
        --output /tmp/radar_results/Vehicle_results.txt \
        --rate 6                          # un evento cada ~6 segundos en media

Luego apuntar el wrapper a esa carpeta:

    # En bridge/.env:
    RADAR_RESULTS_PATH=/results/Vehicle_results.txt
    # En docker-compose.yml: cambiar el bind mount a /tmp/radar_results:/results:ro

    cd bridge && docker compose up --build
"""

from __future__ import annotations

import argparse
import random
import sys
import time
from pathlib import Path

# Reparto realista por horario diurno en un paso de peatones urbano.
# (type, peso, velocidad_kmh, distancia_m_range, direction_bias)
# velocidad_kmh: tupla (lo, hi) — la dirección la asigna el signo al final.
PROFILE = [
    # type 1 — vehículo normal urbano (mayoría)
    (1, 0.40, (20.0, 45.0), (3.0, 8.0)),
    # type 1 — vehículo infractor ocasional (15% de los vehículos)
    (1, 0.08, (45.0, 65.0), (3.0, 8.0)),
    # type 2 — vehículo medio (furgoneta, SUV)
    (2, 0.12, (25.0, 40.0), (3.0, 8.0)),
    # type 3 — vehículo largo (camión, autobús) — poco frecuente
    (3, 0.04, (20.0, 35.0), (3.0, 8.0)),
    # type 4 — bici/moto
    (4, 0.10, (10.0, 25.0), (2.0, 6.0)),
    # type 5 — peatón
    (5, 0.26, (3.0, 7.0), (0.5, 5.0)),
]


def pick_event():
    r = random.random()
    cum = 0.0
    for t, w, vrange, xrange in PROFILE:
        cum += w
        if r <= cum:
            v = random.uniform(*vrange)
            x = random.uniform(*xrange)
            sign = -1 if random.random() < 0.5 else 1
            return t, sign * v, x
    t, _, vrange, xrange = PROFILE[-1]
    return t, random.uniform(*vrange), random.uniform(*xrange)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", required=True, type=Path,
                   help="Ruta del Vehicle_results.txt sintético")
    p.add_argument("--rate", type=float, default=6.0,
                   help="Intervalo medio entre eventos en segundos (default 6)")
    p.add_argument("--burst", type=int, default=0,
                   help="Si >0, escribe N eventos de una vez y termina")
    p.add_argument("--append", action="store_true",
                   help="No truncar el fichero al arrancar")
    args = p.parse_args()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if args.append else "w"

    with open(args.output, mode, buffering=1) as f:  # line-buffered
        if args.burst:
            now = time.time()
            for i in range(args.burst):
                t, v, x = pick_event()
                ts = now - (args.burst - i) * args.rate
                f.write(f"{ts:.3f} {v:.2f} {x:.2f} {t}\n")
            print(f"wrote {args.burst} events to {args.output}", file=sys.stderr)
            return

        print(f"streaming to {args.output} (mean interval {args.rate}s) — Ctrl+C to stop",
              file=sys.stderr)
        try:
            while True:
                t, v, x = pick_event()
                ts = time.time()
                f.write(f"{ts:.3f} {v:.2f} {x:.2f} {t}\n")
                # Intervalo exponencial → mejor modelo de tráfico real (Poisson)
                time.sleep(random.expovariate(1.0 / args.rate))
        except KeyboardInterrupt:
            print("stopped", file=sys.stderr)


if __name__ == "__main__":
    main()
