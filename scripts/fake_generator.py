"""Generate ~3 weeks of synthetic insect detection events into CockroachDB."""

import math
import os
import random
import uuid
from datetime import datetime, timedelta, timezone

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from psycopg2.extras import execute_values

DAYS_BACK = 21
FRAME_W, FRAME_H = 1920, 1080

# Pixel bounding boxes per zone within the camera frame(s).
ZONE_BOUNDS = {
    "sink": (100, 400, 600, 900),
    "dishwasher": (420, 700, 650, 950),
    "stove": (750, 1100, 500, 800),
    "trash": (1200, 1500, 700, 1000),
    "window": (1400, 1900, 100, 400),
    "pantry": (50, 300, 100, 400),
}

ZONE_CAMERA = {
    "sink": "cam-kitchen-1",
    "dishwasher": "cam-kitchen-1",
    "stove": "cam-kitchen-1",
    "trash": "cam-kitchen-1",
    "window": "cam-kitchen-1",
    "pantry": "cam-pantry-1",
}

# active_hours end may exceed 24 to express windows that cross midnight
# (e.g. cockroaches 23:00-05:00). daily_rate is the Poisson mean event
# count per day/night for that species.
SPECIES_PROFILES = {
    "cockroach": {
        "zones": [("sink", 0.4), ("dishwasher", 0.4), ("trash", 0.2)],
        "active_hours": (23, 29),
        "daily_rate": 6.0,
        "species_confidence": (0.70, 0.98),
        "confidence": (0.55, 0.95),
        "burst_lengths": [1, 2, 3, 4],
        "burst_weights": [45, 25, 20, 10],
    },
    "fly": {
        "zones": [("window", 0.5), ("stove", 0.3), ("trash", 0.2)],
        "active_hours": (8, 18),
        "daily_rate": 5.0,
        "species_confidence": (0.55, 0.9),
        "confidence": (0.5, 0.9),
        "burst_lengths": [1, 2, 3],
        "burst_weights": [55, 30, 15],
    },
    "ladybug": {
        "zones": [("window", 1.0)],
        "active_hours": (9, 16),
        "daily_rate": 1.0,
        "species_confidence": (0.5, 0.85),
        "confidence": (0.45, 0.85),
        "burst_lengths": [1, 2],
        "burst_weights": [80, 20],
    },
    "cicada": {
        "zones": [("window", 0.7), ("pantry", 0.3)],
        "active_hours": (15, 20),
        "daily_rate": 0.6,
        "species_confidence": (0.4, 0.8),
        "confidence": (0.4, 0.8),
        "burst_lengths": [1, 2],
        "burst_weights": [85, 15],
    },
    "unknown": {
        "zones": [(z, 1.0) for z in ZONE_BOUNDS],
        "active_hours": (0, 24),
        "daily_rate": 1.2,
        "species_confidence": (0.2, 0.5),
        "confidence": (0.3, 0.7),
        "burst_lengths": [1, 2],
        "burst_weights": [90, 10],
    },
}


def poisson(lam):
    limit = math.exp(-lam)
    k = 0
    p = 1.0
    while True:
        k += 1
        p *= random.random()
        if p <= limit:
            return k - 1


def weighted_choice(pairs):
    items, weights = zip(*pairs)
    return random.choices(items, weights=weights, k=1)[0]


def sample_hour_offset(active_hours):
    start, end = active_hours
    mode = (start + end) / 2
    return random.triangular(start, end, mode)


def sample_position(zone):
    x0, x1, y0, y1 = ZONE_BOUNDS[zone]
    return random.uniform(x0, x1), random.uniform(y0, y1)


def drift_position(x, y, zone):
    x0, x1, y0, y1 = ZONE_BOUNDS[zone]
    nx = min(max(x + random.uniform(-15, 15), x0), x1)
    ny = min(max(y + random.uniform(-15, 15), y0), y1)
    return nx, ny


def sample_ambient(hour, zone):
    diurnal = 3.0 * math.sin((hour - 9) / 24 * 2 * math.pi)
    temp = 21.5 + diurnal + random.uniform(-1.5, 1.5)

    humidity_base = 45.0
    if zone in ("sink", "dishwasher"):
        humidity_base += 10.0
    night_bump = 4.0 if hour < 6 or hour >= 22 else 0.0
    humidity = humidity_base + night_bump + random.uniform(-4.0, 4.0)

    return round(temp, 2), round(min(max(humidity, 0), 100), 2)


def lights_on_for_hour(hour):
    on = 7 <= hour < 23
    if random.random() < 0.05:
        on = not on
    return on


def clamp(value, lo, hi):
    return min(max(value, lo), hi)


def generate_rows():
    rows = []
    start_date = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    ) - timedelta(days=DAYS_BACK)

    for day_offset in range(DAYS_BACK):
        day_start = start_date + timedelta(days=day_offset)

        for species, profile in SPECIES_PROFILES.items():
            event_count = poisson(profile["daily_rate"])

            for _ in range(event_count):
                zone = weighted_choice(profile["zones"])
                camera_id = ZONE_CAMERA[zone]
                hour_offset = sample_hour_offset(profile["active_hours"])
                event_time = day_start + timedelta(hours=hour_offset)
                hour = event_time.hour

                ambient_temp, ambient_humidity = sample_ambient(hour, zone)
                lights_on = lights_on_for_hour(hour)

                track_id = uuid.uuid4()
                burst_len = random.choices(
                    profile["burst_lengths"], weights=profile["burst_weights"], k=1
                )[0]

                x, y = sample_position(zone)
                species_conf_lo, species_conf_hi = profile["species_confidence"]
                conf_lo, conf_hi = profile["confidence"]
                base_species_conf = random.uniform(species_conf_lo, species_conf_hi)
                base_conf = random.uniform(conf_lo, conf_hi)

                for frame in range(burst_len):
                    detected_at = event_time + timedelta(
                        seconds=frame * random.uniform(1, 6)
                    )
                    if frame > 0:
                        x, y = drift_position(x, y, zone)

                    species_confidence = clamp(
                        base_species_conf + random.uniform(-0.05, 0.05), 0.0, 1.0
                    )
                    confidence = clamp(
                        base_conf + random.uniform(-0.05, 0.05), 0.0, 1.0
                    )

                    rows.append(
                        (
                            detected_at,
                            camera_id,
                            zone,
                            species,
                            round(species_confidence, 3),
                            int(round(x)),
                            int(round(y)),
                            round(confidence, 3),
                            track_id,
                            None,  # snapshot_s3_key
                            ambient_temp,
                            ambient_humidity,
                            lights_on,
                        )
                    )

    rows.sort(key=lambda r: r[0])
    return rows


def insert_rows(conn, rows):
    columns = [
        "detected_at",
        "camera_id",
        "zone",
        "species",
        "species_confidence",
        "x",
        "y",
        "confidence",
        "track_id",
        "snapshot_s3_key",
        "ambient_temp",
        "ambient_humidity",
        "lights_on",
    ]
    query = f"INSERT INTO detections ({', '.join(columns)}) VALUES %s"
    with conn.cursor() as cur:
        execute_values(cur, query, rows)
    conn.commit()


def main():
    load_dotenv()
    conn_str = os.environ.get("DB_CONNECTION_STRING")
    if not conn_str:
        raise RuntimeError("DB_CONNECTION_STRING not set in environment/.env")

    rows = generate_rows()

    conn = psycopg2.connect(conn_str)
    psycopg2.extras.register_uuid(conn_or_curs=conn)
    try:
        insert_rows(conn, rows)
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM detections")
            total = cur.fetchone()[0]
    finally:
        conn.close()

    print(f"Inserted {len(rows)} rows this run. Total rows in detections: {total}")


if __name__ == "__main__":
    main()
