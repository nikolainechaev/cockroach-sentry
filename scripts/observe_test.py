"""Part 4.2 - read detections, group them, print summary strings (no embedding, no writing yet)."""
import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()
CONN_STR = os.environ["DB_CONNECTION_STRING"]

def fetch_groups():
    """Group detections by species + zone + night, return summary rows."""
    conn = psycopg2.connect(CONN_STR)
    cur = conn.cursor()
    cur.execute("""
        SELECT
            species,
            zone,
            DATE(detected_at) AS night,
            COUNT(*) AS cnt,
            ROUND(AVG(ambient_temp)::numeric, 1) AS avg_temp,
            ROUND(AVG(ambient_humidity)::numeric, 1) AS avg_hum,
            ROUND(AVG(EXTRACT(HOUR FROM detected_at))::numeric, 0) AS avg_hour
        FROM detections
        GROUP BY species, zone, DATE(detected_at)
        ORDER BY night, species, zone
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows

def build_summary(species, zone, night, cnt, avg_temp, avg_hum, avg_hour):
    """Turn a group into a natural-language sentence."""
    hour = int(avg_hour)
    part_of_day = "at night" if hour <= 5 or hour >= 22 else \
                  "in the morning" if hour < 12 else \
                  "in the afternoon" if hour < 18 else "in the evening"
    return (f"{cnt} {species} detection(s) near the {zone} {part_of_day} "
            f"on {night}, avg temp {avg_temp}C, avg humidity {avg_hum}%")

if __name__ == "__main__":
    groups = fetch_groups()
    print(f"Total observation groups: {len(groups)}\n")
    print("First 10 summaries:")
    for g in groups[:10]:
        print(" -", build_summary(*g))