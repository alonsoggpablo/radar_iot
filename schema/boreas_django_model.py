"""Modelo Django equivalente a `nexus_radar.sql`.

Copiar a la app de Nexus dentro de Boreas (probablemente `boreas_app/mediacion/models.py`
o donde estén los modelos `NexusMeasurement`, `NexusElectrical`, `NexusIaq`, ...).

Luego:
    docker exec boreas_app python manage.py makemigrations
    docker exec boreas_app python manage.py migrate

Tras la migración, ejecutar a mano (o en una RunPython de la propia migración)
los `SELECT create_hypertable`, `add_compression_policy`, `add_retention_policy`
de `nexus_radar.sql` — Django no los emite solo.
"""

from django.db import models


class NexusRadar(models.Model):
    KIND_TRACK = "track"
    KIND_SPEED_VIOLATION = "speed_violation"
    KIND_CHOICES = [
        (KIND_TRACK, "Track (objeto consolidado por firmware)"),
        (KIND_SPEED_VIOLATION, "Infracción de velocidad"),
    ]

    OBJECT_TYPE_CHOICES = [
        (1, "vehicle_normal"),
        (2, "vehicle_medium"),
        (3, "vehicle_long"),
        (4, "bike_motorcycle"),
        (5, "pedestrian"),
    ]

    DIRECTION_APPROACHING = "approaching"
    DIRECTION_RECEDING = "receding"

    time = models.DateTimeField(db_index=False)
    device_id = models.TextField()
    site = models.TextField(null=True, blank=True)
    kind = models.TextField(choices=KIND_CHOICES)
    object_type = models.SmallIntegerField(null=True, blank=True, choices=OBJECT_TYPE_CHOICES)
    type_label = models.TextField(null=True, blank=True)
    velocity_kmh = models.FloatField(null=True, blank=True)
    velocity_signed_kmh = models.FloatField(null=True, blank=True)
    direction = models.TextField(null=True, blank=True)
    x_distance_m = models.FloatField(null=True, blank=True)
    speed_limit_kmh = models.FloatField(null=True, blank=True)
    external_event_id = models.TextField(unique=True)
    fw_raw = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "nexus_radar"
        managed = True
        indexes = [
            models.Index(fields=["device_id", "kind", "-time"],
                         name="idx_nexus_radar_dev_kind_t"),
            models.Index(fields=["site", "-time"],
                         name="idx_nexus_radar_site_time",
                         condition=models.Q(site__isnull=False)),
        ]

    def __str__(self):
        return f"{self.time.isoformat()} {self.device_id} {self.kind} {self.type_label}"
