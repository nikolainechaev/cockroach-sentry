"""Part 4.4 - generate embeddings for all observation groups and write them."""
import os
import json
import time
import boto3
import psycopg2
from dotenv import load_dotenv

load_dotenv()
CONN_STR = os.environ["DB_CONNECTION_STRING"]
bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")

def get_embedding(text: str, retries: int = 5) -> list[float]:
    """Titan embedding with exponential backoff for throttling."""
    for attempt in range(retries):
        try:
            resp = bedrock.invoke_model(
                modelId="amazon.titan-embed-text-v2:0",
                body=json.dumps({"inputText": text}),
            )
            return json.loads(resp["body"].read())["embedding"]
        except bedrock.exceptions.ThrottlingException:
            wait = 2 ** attempt
            print(f"  throttled, waiting {wait}s...")
            time.sleep(wait)
    raise RuntimeError("Bedrock throttled too many times")

def fetch_groups(cur):
    cur.execute("""
        SELECT species, zone, DATE(detected_at) AS night,
               COUNT(*) AS cnt,
               ROUND(AVG(ambient_temp)::numeric, 1) AS avg_temp,
               ROUND(AVG(ambient_humidity)::numeric, 1) AS avg_hum,
               ROUND(AVG(EXTRACT(HOUR FROM detected_at))::numeric, 0) AS avg_hour
        FROM detections
        GROUP BY species, zone, DATE(detected_at)
        ORDER BY night, species, zone
    """)
    return cur.fetchall()

def build_summary(species, zone, night, cnt, avg_temp, avg_hum, avg_hour):
    hour = int(avg_hour)
    part = ("at night" if hour <= 5 or hour >= 22 else
            "in the morning" if hour < 12 else
            "in the afternoon" if hour < 18 else "in the evening")
    return (f"{cnt} {species} detection(s) near the {zone} {part} "
            f"on {night}, avg temp {avg_temp}C, avg humidity {avg_hum}%")

def main():
    conn = psycopg2.connect(CONN_STR)
    cur = conn.cursor()

    # Clear old observations so re-running is clean (we had 1 test row)
    cur.execute("DELETE FROM observations")
    conn.commit()
    print("Cleared old observations.")

    groups = fetch_groups(cur)
    print(f"Processing {len(groups)} groups...\n")

    for i, g in enumerate(groups, 1):
        summary = build_summary(*g)
        species, zone = g[0], g[1]
        vec = get_embedding(summary)
        vec_str = "[" + ",".join(str(x) for x in vec) + "]"
        cur.execute(
            "INSERT INTO observations (summary, embedding, species, zone) VALUES (%s,%s,%s,%s)",
            (summary, vec_str, species, zone),
        )
        if i % 25 == 0:
            conn.commit()
            print(f"  {i}/{len(groups)} done...")

    conn.commit()
    cur.execute("SELECT COUNT(*) FROM observations")
    total = cur.fetchone()[0]
    print(f"\nDone! observations table now has {total} rows.")
    cur.close()
    conn.close()

if __name__ == "__main__":
    main()