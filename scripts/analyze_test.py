"""Part 5.1 - analyze observations to find patterns (SQL only, no LLM, no writing)."""
import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()
CONN_STR = os.environ["DB_CONNECTION_STRING"]

def analyze():
    conn = psycopg2.connect(CONN_STR)
    cur = conn.cursor()
    # Aggregate detections by species+zone: total count, avg hour, avg conditions
    cur.execute("""
        SELECT
            species,
            zone,
            COUNT(*) AS total_detections,
            ROUND(AVG(EXTRACT(HOUR FROM detected_at))::numeric, 0) AS avg_hour,
            ROUND(AVG(ambient_temp)::numeric, 1) AS avg_temp,
            ROUND(AVG(ambient_humidity)::numeric, 1) AS avg_hum
        FROM detections
        GROUP BY species, zone
        HAVING COUNT(*) >= 10
        ORDER BY species, total_detections DESC
    """)
    return cur.fetchall()

if __name__ == "__main__":
    rows = analyze()
    print("Patterns found (species + zone, min 10 detections):\n")
    current_species = None
    for species, zone, total, hour, temp, hum in rows:
        if species != current_species:
            print(f"\n{species.upper()}:")
            current_species = species
        print(f"  {zone}: {total} detections, avg hour {int(hour)}, "
              f"{temp}C, {hum}% humidity")