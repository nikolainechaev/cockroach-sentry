"""Inject a synthetic cockroach detection shift into the pantry zone.

Adds 40 cockroach detections concentrated in the "pantry" zone over the
last 3 nights (hour 0-4, high humidity 60-72%), on top of whatever
baseline fake_generator.py already wrote. This is a test signal meant to
give the downstream pattern/hypothesis agent (hypothesize_test.py etc.) a
clear anomaly to notice and reason about.
"""

import os
import random
import uuid
from datetime import datetime, timedelta, timezone

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from psycopg2.extras import execute_values

ZONE = "pantry"
CAMERA_ID = "cam-pantry-1"
ZONE_BOUNDS = (50, 300, 100, 400)  # x0, x1, y0, y1 (matches fake_generator.py)

NIGHTS_BACK = 3
NIGHT_HOUR_RANGE = (0, 4)  # detections land between 00:00 and 04:00
HUMIDITY_RANGE = (60.0, 72.0)
TEMP_RANGE = (20.0, 23.0)
TOTAL_DETECTIONS = 40

SPECIES = "cockroach"
SPECIES_CONFIDENCE_RANGE = (0.75, 0.98)
CONFIDENCE_RANGE = (0.6, 0.95)


def sample_position():
    x0, x1, y0, y1 = ZONE_BOUNDS
    return random.uniform(x0, x1), random.uniform(y0, y1)


def build_rows():
    rows = []
    today_utc = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    night_starts = [today_utc - timedelta(days=d) for d in range(NIGHTS_BACK)]

    for _ in range(TOTAL_DETECTIONS):
        night_start = random.choice(night_starts)
        hour_offset = random.uniform(*NIGHT_HOUR_RANGE)
        detected_at = night_start + timedelta(hours=hour_offset)

        x, y = sample_position()
        ambient_temp = round(random.uniform(*TEMP_RANGE), 2)
        ambient_humidity = round(random.uniform(*HUMIDITY_RANGE), 2)

        rows.append(
            (
                detected_at,
                CAMERA_ID,
                ZONE,
                SPECIES,
                round(random.uniform(*SPECIES_CONFIDENCE_RANGE), 3),
                int(round(x)),
                int(round(y)),
                round(random.uniform(*CONFIDENCE_RANGE), 3),
                uuid.uuid4(),
                None,  # snapshot_s3_key
                ambient_temp,
                ambient_humidity,
                False,  # lights_on - night hours
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


def print_zone_counts(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT zone, COUNT(*) AS cnt
            FROM detections
            WHERE species = %s
              AND detected_at >= now() - interval '3 days'
            GROUP BY zone
            ORDER BY cnt DESC
            """,
            (SPECIES,),
        )
        results = cur.fetchall()

    print("\nCockroach detections by zone (last 3 days):")
    for zone, cnt in results:
        print(f"  {zone:<12} {cnt}")


def main():
    load_dotenv()
    conn_str = os.environ.get("DB_CONNECTION_STRING")
    if not conn_str:
        raise RuntimeError("DB_CONNECTION_STRING not set in environment/.env")

    rows = build_rows()

    conn = psycopg2.connect(conn_str)
    psycopg2.extras.register_uuid(conn_or_curs=conn)
    try:
        insert_rows(conn, rows)
        print(f"Inserted {len(rows)} {SPECIES} detections into zone '{ZONE}'.")
        print_zone_counts(conn)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
