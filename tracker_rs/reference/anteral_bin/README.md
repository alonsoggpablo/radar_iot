# Software Anteral (referencia) — uRAD Tracking v2.3

`anteral_soft_v2.3.tar.gz` contiene el software del fabricante tal cual está en la
Raspberry (sin `venv_urad/` ni `Results/`):

- `vehicleCounter_smartcities_v2_3.py` — script ABIERTO (lee serie, arma la nube,
  llama a `do_tracking`). Copia legible también en `../vehicleCounter_smartcities_v2_3.py`.
- `uRAD_Tracking_v2_3.cpython-311-aarch64-linux-gnu.so`
- `uRAD_Tracking_highway_v2_3.cpython-311-aarch64-linux-gnu.so`

## Avisos

- **Los `.so` son ARM64 / Python 3.11** → NO cargan en x86 (WSL). Para *ejecutar*
  Anteral hace falta ARM64 (la propia Pi, o `docker run --platform linux/arm64`).
- **El algoritmo de tracking está DENTRO del `.so`** (`do_tracking`, `distance_matrix`,
  `read_header`, `get_commands`, `rotate_points`) — compilado, no legible. Para el
  clon en Rust la referencia real es: formato de la nube (entrada), formato
  `Vehicle_results` (salida) y la config/geometría del `.py` abierto.
- Binarios propietarios de Anteral — uso interno.
