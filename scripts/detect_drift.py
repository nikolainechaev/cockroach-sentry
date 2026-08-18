"""Part 6.2 - detect whether the current cockroach hypothesis still matches recent data."""
import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()
CONN_STR = os.environ["DB_CONNECTION_STRING"]

def recent_top_zone(cur, species, days=3):
    """Which zone dominates for this species in the last N days?"""
    cur.execute("""
        SELECT zone, COUNT(*) AS cnt
        FROM detections
        WHERE species = %s AND detected_at > now() - (%s || ' days')::INTERVAL
        GROUP BY zone ORDER BY cnt DESC LIMIT 1
    """, (species, days))
    row = cur.fetchone()
    return (row[0], row[1]) if row else (None, 0)

def current_hypothesis(cur, species):
    """The active hypothesis for this species."""
    cur.execute("""
        SELECT id, statement FROM hypotheses
        WHERE species = %s AND valid = true
        ORDER BY confidence DESC LIMIT 1
    """, (species,))
    return cur.fetchone()

def main():
    conn = psycopg2.connect(CONN_STR)
    cur = conn.cursor()

    species = "cockroach"
    hyp = current_hypothesis(cur, species)
    top_zone, cnt = recent_top_zone(cur, species, days=3)

    print(f"Species: {species}")
    if hyp:
        hyp_id, statement = hyp
        print(f"Current hypothesis: {statement}")
    else:
        print("No current hypothesis.")
        return

    print(f"\nRecent top zone (last 3 days): {top_zone} ({cnt} detections)")

    # Drift check: does the current hypothesis mention the recent top zone?
    if top_zone and top_zone.lower() not in statement.lower():
        print(f"\n⚠️  DRIFT DETECTED: recent activity is at '{top_zone}', "
              f"but the hypothesis doesn't mention it.")
        print("    -> This hypothesis is a candidate for supersession.")
    else:
        print("\n✓ Hypothesis still matches recent data.")

    cur.close()
    conn.close()

if __name__ == "__main__":
    main()