"""AGlabs Radar IoT bridge — uRAD Smart Traffic RPi → mqtt.aglabs.es.

Tail the Vehicle_results.txt that the manufacturer firmware writes one line
per detected object, persist every event to a local SQLite WAL (durable
buffer + post-mortem store), publish to MQTT, expose health + state.

Topics:
    aglabs/radar/<site>/<sensor>/track     one per object (qos=1)
    aglabs/radar/<site>/<sensor>/event     derived semantics (qos=1)
    aglabs/radar/<site>/<sensor>/state     retained config snapshot
    aglabs/radar/<site>/<sensor>/$health   retained heartbeat + LWT
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import signal
import sqlite3
import ssl
import sys
import threading
import time
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

import paho.mqtt.client as mqtt

WRAPPER_VERSION = "0.1.0"

TYPE_LABEL = {
    1: "vehicle_normal",
    2: "vehicle_medium",
    3: "vehicle_long",
    4: "bike_motorcycle",
    5: "pedestrian",
}


def env(key: str, default=None, cast=str):
    raw = os.environ.get(key, default)
    if raw is None:
        return None
    if cast is bool:
        return str(raw).strip().lower() in ("1", "true", "yes", "on")
    return cast(raw)


class Config:
    site = env("RADAR_SITE", "unknown_site")
    sensor_id = env("RADAR_SENSOR_ID", "radar_iot_000")
    results_path = Path(env("RADAR_RESULTS_PATH", "/results/Vehicle_results.txt"))
    local_db = Path(env("RADAR_LOCAL_DB", "/var/lib/radar_iot/events.sqlite"))
    retention_days = env("RADAR_RETENTION_DAYS", "90", int)
    speed_limit_kmh = env("RADAR_SPEED_LIMIT_KMH", "0", float)  # 0 disables
    highway_scenario = env("RADAR_HIGHWAY_SCENARIO", "false", bool)

    mqtt_host = env("MQTT_HOST", "mqtt.aglabs.es")
    mqtt_port = env("MQTT_PORT", "443", int)
    mqtt_transport = env("MQTT_TRANSPORT", "websockets")  # 'tcp' | 'websockets'
    mqtt_path = env("MQTT_PATH", "/mqtt")
    mqtt_tls = env("MQTT_TLS", "true", bool)
    mqtt_username = env("MQTT_USERNAME", None)
    mqtt_password = env("MQTT_PASSWORD", None)
    mqtt_topic_base = env("MQTT_TOPIC_BASE", "aglabs/radar")

    heartbeat_s = env("HEARTBEAT_INTERVAL_S", "60", int)
    publish_retry_s = env("PUBLISH_RETRY_INTERVAL_S", "5", int)
    tail_poll_ms = env("TAIL_POLL_MS", "100", int)

    log_level = env("LOG_LEVEL", "INFO")


def topic(suffix: str) -> str:
    return f"{Config.mqtt_topic_base}/{Config.site}/{Config.sensor_id}/{suffix}"


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def parse_ts_token(token: str) -> str:
    """Normaliza un timestamp a ISO-8601 UTC con ms.

    Acepta tres formatos:
      - epoch (float),
      - ISO-8601 (con 'T' o espacio),
      - Anteral uRAD: 'yyyy/mm/dd HH:MM:SS' (hora LOCAL del Pi, naive).
    """
    try:
        return datetime.fromtimestamp(float(token), tz=timezone.utc).isoformat(
            timespec="milliseconds"
        ).replace("+00:00", "Z")
    except ValueError:
        pass
    try:
        dt = datetime.fromisoformat(token.replace("Z", "+00:00"))
    except ValueError:
        # Formato Anteral: hora local del Pi sin tz -> astimezone la interpreta local.
        dt = datetime.strptime(token, "%Y/%m/%d %H:%M:%S")
    return dt.astimezone(timezone.utc).isoformat(
        timespec="milliseconds"
    ).replace("+00:00", "Z")


def parse_line(line: str) -> dict | None:
    """One line: '<ts> <velocity_kmh_signed> <x_distance_m> <type>'.

    velocity is signed in km/h: positive = receding, negative = approaching.
    Returns None on parse failure (logged, never raises).

    Soporta el formato real de Anteral 'yyyy/mm/dd HH:MM:SS <vel> <x> <type>'
    (el timestamp ocupa DOS tokens, fecha y hora) además del formato legacy de
    4 tokens con timestamp en uno solo (epoch/ISO, usado por el bench).
    """
    parts = line.strip().split()
    if len(parts) < 4:
        return None
    # Anteral: fecha con '/' + hora con ':' -> el ts son los 2 primeros tokens.
    if len(parts) >= 5 and "/" in parts[0] and ":" in parts[1]:
        ts_token, rest = f"{parts[0]} {parts[1]}", parts[2:5]
    else:
        ts_token, rest = parts[0], parts[1:4]
    try:
        ts = parse_ts_token(ts_token)
        v_signed = float(rest[0])
        x = float(rest[1])
        t = int(rest[2])
    except (ValueError, IndexError) as e:
        logging.warning("unparseable line %r: %s", line, e)
        return None

    fw_raw = f"{ts_token} {' '.join(rest)}"
    event_id = hashlib.sha256(
        f"{Config.sensor_id}|{fw_raw}".encode()
    ).hexdigest()[:32]

    return {
        "ts": ts,
        "site": Config.site,
        "sensor": Config.sensor_id,
        "type": t,
        "type_label": TYPE_LABEL.get(t, f"unknown_{t}"),
        "velocity_kmh": abs(v_signed),
        "velocity_signed_kmh": v_signed,
        "direction": "approaching" if v_signed < 0 else "receding",
        "x_distance_m": x,
        "fw_raw": fw_raw,
        "external_event_id": event_id,
    }


def derive_event(track: dict) -> dict | None:
    """v0.1 derivation: speed violation. More semantics in v0.2."""
    if Config.speed_limit_kmh <= 0:
        return None
    if track["type"] not in (1, 2, 3):
        return None
    if track["velocity_kmh"] <= Config.speed_limit_kmh:
        return None
    return {
        "ts": track["ts"],
        "site": Config.site,
        "sensor": Config.sensor_id,
        "kind": "speed_violation",
        "limit_kmh": Config.speed_limit_kmh,
        "measured_kmh": track["velocity_kmh"],
        "type": track["type"],
        "type_label": track["type_label"],
        "direction": track["direction"],
        "external_event_id": f"sv_{track['external_event_id']}",
    }


class Store:
    """Append-only durable queue + post-mortem store."""

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        external_event_id TEXT UNIQUE NOT NULL,
        ts TEXT NOT NULL,
        suffix TEXT NOT NULL,
        payload TEXT NOT NULL,
        published_at TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX IF NOT EXISTS idx_unpub ON events(id) WHERE published_at IS NULL;
    CREATE INDEX IF NOT EXISTS idx_ts ON events(ts);
    CREATE TABLE IF NOT EXISTS meta (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );
    """

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._lock = threading.Lock()
        with self._conn() as c:
            c.executescript(self.SCHEMA)
            c.execute("PRAGMA journal_mode=WAL")

    def _conn(self):
        c = sqlite3.connect(str(self.path), timeout=30)
        c.row_factory = sqlite3.Row
        return c

    def insert(self, external_event_id: str, ts: str, suffix: str, payload: dict) -> bool:
        with self._lock, closing(self._conn()) as c:
            try:
                c.execute(
                    "INSERT INTO events(external_event_id, ts, suffix, payload) VALUES (?,?,?,?)",
                    (external_event_id, ts, suffix, json.dumps(payload)),
                )
                c.commit()
                return True
            except sqlite3.IntegrityError:
                return False  # duplicate, idempotent

    def pending(self, limit=100):
        with self._lock, closing(self._conn()) as c:
            rows = c.execute(
                "SELECT id, suffix, payload FROM events WHERE published_at IS NULL ORDER BY id LIMIT ?",
                (limit,),
            ).fetchall()
        return [(r["id"], r["suffix"], json.loads(r["payload"])) for r in rows]

    def mark_published(self, row_id: int):
        with self._lock, closing(self._conn()) as c:
            c.execute(
                "UPDATE events SET published_at=? WHERE id=?",
                (utcnow_iso(), row_id),
            )
            c.commit()

    def queue_depth(self) -> int:
        with self._lock, closing(self._conn()) as c:
            return c.execute(
                "SELECT COUNT(*) AS n FROM events WHERE published_at IS NULL"
            ).fetchone()["n"]

    def get_meta(self, key: str, default=None):
        with self._lock, closing(self._conn()) as c:
            r = c.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return r["value"] if r else default

    def set_meta(self, key: str, value: str):
        with self._lock, closing(self._conn()) as c:
            c.execute(
                "INSERT INTO meta(key, value) VALUES(?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )
            c.commit()

    def purge_old(self, retention_days: int):
        cutoff = (
            datetime.now(timezone.utc).timestamp() - retention_days * 86400
        )
        cutoff_iso = datetime.fromtimestamp(cutoff, tz=timezone.utc).isoformat()
        with self._lock, closing(self._conn()) as c:
            r = c.execute(
                "DELETE FROM events WHERE published_at IS NOT NULL AND ts < ?",
                (cutoff_iso,),
            )
            c.commit()
            return r.rowcount


class Bridge:
    def __init__(self):
        self.store = Store(Config.local_db)
        self.stop_evt = threading.Event()
        self.client = self._build_client()
        self.connected = threading.Event()
        self.last_detection_ts: str | None = None

    def _build_client(self) -> mqtt.Client:
        c = mqtt.Client(
            client_id=Config.sensor_id,
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            transport=Config.mqtt_transport,
            # clean_session=True a propósito: la fiabilidad la da nuestro store
            # local (events.sqlite con reintento), NO la sesión persistente del
            # broker. Con clean_session=False el broker acumulaba mensajes QoS1
            # a topics ya denegados (p.ej. de un site anterior mal-ACLeado) y los
            # reintentaba en cada reconexión → 'disconnected: not authorised' en
            # bucle y el dato nuevo nunca salía. clean_session=True evita esa
            # clase de fallo y el churn de 'session taken over'. (2026-07-09)
            clean_session=True,
        )
        if Config.mqtt_transport == "websockets":
            c.ws_set_options(path=Config.mqtt_path)
        if Config.mqtt_tls:
            c.tls_set(cert_reqs=ssl.CERT_REQUIRED)
        if Config.mqtt_username:
            c.username_pw_set(Config.mqtt_username, Config.mqtt_password)
        c.will_set(
            topic("$health"),
            json.dumps({"status": "offline", "ts": utcnow_iso()}),
            qos=1,
            retain=True,
        )
        c.on_connect = self._on_connect
        c.on_disconnect = self._on_disconnect
        return c

    def _on_connect(self, client, _ud, _flags, reason_code, _props=None):
        if reason_code == 0:
            logging.info("MQTT connected to %s:%s", Config.mqtt_host, Config.mqtt_port)
            self.connected.set()
            self._publish_state()
            self._publish_health()
        else:
            logging.warning("MQTT connect failed rc=%s", reason_code)

    def _on_disconnect(self, *_args, **_kwargs):
        logging.warning("MQTT disconnected")
        self.connected.clear()

    def _publish_state(self):
        payload = {
            "ts": utcnow_iso(),
            "wrapper_version": WRAPPER_VERSION,
            "config": {
                "site": Config.site,
                "sensor": Config.sensor_id,
                "highway_scenario": Config.highway_scenario,
                "speed_limit_kmh": Config.speed_limit_kmh,
                "results_path": str(Config.results_path),
                "retention_days": Config.retention_days,
            },
        }
        self.client.publish(topic("state"), json.dumps(payload), qos=1, retain=True)

    def _publish_health(self):
        try:
            payload = {
                "status": "online",
                "ts": utcnow_iso(),
                "wrapper_version": WRAPPER_VERSION,
                "uptime_s": int(time.monotonic()),
                "queue_depth": self.store.queue_depth(),
                "last_detection_ts": self.last_detection_ts,
            }
            self.client.publish(topic("$health"), json.dumps(payload), qos=1, retain=True)
        except Exception:
            logging.exception("health publish failed")

    # ---- tail thread ------------------------------------------------------
    def _newest_results_file(self):
        """El build de Anteral rota el fichero por día: escribe
        ``<YYYY-MM-DD>_Vehicle_results.txt`` (y builds antiguos/bench el plano
        ``Vehicle_results.txt``). Seguimos el más reciente que case con
        ``*<basename>`` dentro del dir de Results; fallback al path configurado.
        """
        base = Config.results_path
        try:
            cands = sorted(
                base.parent.glob(f"*{base.name}"),
                key=lambda p: p.stat().st_mtime,
            )
        except OSError:
            cands = []
        if cands:
            return cands[-1]
        return base if base.exists() else None

    def tail_loop(self):
        base_name = Config.results_path.name
        cur_name = self.store.get_meta("tail_file", "")
        offset = int(self.store.get_meta("last_file_offset", "0"))
        last_inode = None
        f = None
        logging.info(
            "tail starting (following newest *%s, resume file=%r offset=%d)",
            base_name, cur_name, offset,
        )
        while not self.stop_evt.is_set():
            try:
                target = self._newest_results_file()
                if target is None:
                    time.sleep(1)
                    continue
                st = target.stat()
                # Re-abrir si: primer arranque, cambió el fichero (rollover de
                # día), cambió el inode (rotación in-place) o truncado.
                need_open = (
                    f is None
                    or target.name != cur_name
                    or st.st_ino != last_inode
                    or offset > st.st_size
                )
                if need_open:
                    if target.name != cur_name:
                        logging.info("tail switching to %s", target.name)
                        cur_name = target.name
                        offset = 0
                        self.store.set_meta("tail_file", cur_name)
                    elif offset > st.st_size:
                        logging.warning("file truncated, restarting from 0")
                        offset = 0
                    if f:
                        f.close()
                    f = open(target, "r")
                    last_inode = st.st_ino
                    f.seek(offset)
                line = f.readline()
                if not line:
                    time.sleep(Config.tail_poll_ms / 1000.0)
                    continue
                if not line.endswith("\n"):
                    f.seek(offset)
                    time.sleep(Config.tail_poll_ms / 1000.0)
                    continue
                offset = f.tell()
                self._handle_line(line)
                self.store.set_meta("last_file_offset", str(offset))
            except Exception:
                logging.exception("tail iteration failed; backing off")
                time.sleep(1)
        if f:
            f.close()

    def _handle_line(self, line: str):
        track = parse_line(line)
        if track is None:
            return
        if self.store.insert(track["external_event_id"], track["ts"], "track", track):
            self.last_detection_ts = track["ts"]
            logging.debug("track persisted %s", track["external_event_id"])
        event = derive_event(track)
        if event is not None:
            self.store.insert(event["external_event_id"], event["ts"], "event", event)

    # ---- publisher thread -------------------------------------------------
    def publisher_loop(self):
        while not self.stop_evt.is_set():
            if not self.connected.is_set():
                self.stop_evt.wait(Config.publish_retry_s)
                continue
            batch = self.store.pending(limit=100)
            if not batch:
                self.stop_evt.wait(Config.publish_retry_s)
                continue
            for row_id, suffix, payload in batch:
                try:
                    info = self.client.publish(
                        topic(suffix), json.dumps(payload), qos=1, retain=False
                    )
                    info.wait_for_publish(timeout=10)
                    if info.is_published():
                        self.store.mark_published(row_id)
                    else:
                        logging.warning("publish unconfirmed id=%d", row_id)
                        break
                except Exception:
                    logging.exception("publish failed id=%d", row_id)
                    break

    # ---- heartbeat thread -------------------------------------------------
    def heartbeat_loop(self):
        while not self.stop_evt.is_set():
            if self.connected.is_set():
                self._publish_health()
            self.stop_evt.wait(Config.heartbeat_s)

    # ---- maintenance thread -----------------------------------------------
    def maintenance_loop(self):
        while not self.stop_evt.is_set():
            try:
                n = self.store.purge_old(Config.retention_days)
                if n:
                    logging.info("purged %d events older than %dd", n, Config.retention_days)
            except Exception:
                logging.exception("purge failed")
            self.stop_evt.wait(24 * 3600)

    def run(self):
        logging.info(
            "starting radar_iot_bridge v%s site=%s sensor=%s",
            WRAPPER_VERSION, Config.site, Config.sensor_id,
        )
        self.client.connect_async(Config.mqtt_host, Config.mqtt_port, keepalive=60)
        self.client.loop_start()

        threads = [
            threading.Thread(target=self.tail_loop, name="tail", daemon=True),
            threading.Thread(target=self.publisher_loop, name="pub", daemon=True),
            threading.Thread(target=self.heartbeat_loop, name="hb", daemon=True),
            threading.Thread(target=self.maintenance_loop, name="maint", daemon=True),
        ]
        for t in threads:
            t.start()

        signal.signal(signal.SIGTERM, lambda *_: self.stop_evt.set())
        signal.signal(signal.SIGINT, lambda *_: self.stop_evt.set())

        while not self.stop_evt.is_set():
            time.sleep(1)

        logging.info("stopping")
        try:
            self.client.publish(
                topic("$health"),
                json.dumps({"status": "offline", "ts": utcnow_iso()}),
                qos=1, retain=True,
            ).wait_for_publish(timeout=5)
        except Exception:
            pass
        self.client.loop_stop()
        self.client.disconnect()


def main():
    logging.basicConfig(
        level=getattr(logging, Config.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(threadName)s %(message)s",
    )
    if not Config.mqtt_username or not Config.mqtt_password:
        logging.warning("MQTT credentials unset — connection will likely fail")
    Bridge().run()


if __name__ == "__main__":
    main()
