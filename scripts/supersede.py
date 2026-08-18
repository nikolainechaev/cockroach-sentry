"""Part 6.3 - atomically supersede an outdated hypothesis with a new one (single ACID transaction)."""
import os
import json
import boto3
import psycopg2
from dotenv import load_dotenv

load_dotenv()
CONN_STR = os.environ["DB_CONNECTION_STRING"]
bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")
MODEL_ID = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"

def recent_stats(cur, species, zone, days=3):
    cur.execute("""
        SELECT COUNT(*),
               ROUND(AVG(EXTRACT(HOUR FROM detected_at))::numeric,0),
               ROUND(AVG(ambient_humidity)::numeric,1)
        FROM detections
        WHERE species=%s AND zone=%s AND detected_at > now() - (%s||' days')::INTERVAL
    """, (species, zone, days))
    return cur.fetchone()

def new_statement_via_claude(species, zone, cnt, hour, hum, old_statement):
    prompt = f"""You are a pest-monitoring agent updating your beliefs based on new evidence.

Your OLD hypothesis was: "{old_statement}"

But in the last 3 days, new data shows a shift: {cnt} {species} detections at the '{zone}' zone, avg hour {int(hour)}, {hum}% humidity.

Write ONE updated hypothesis sentence reflecting this new pattern. Be specific and actionable. Respond with ONLY the sentence, no quotes, no JSON."""
    body = {"anthropic_version":"bedrock-2023-05-31","max_tokens":300,
            "messages":[{"role":"user","content":prompt}]}
    resp = bedrock.invoke_model(modelId=MODEL_ID, body=json.dumps(body))
    return json.loads(resp["body"].read())["content"][0]["text"].strip()

def main():
    conn = psycopg2.connect(CONN_STR)
    cur = conn.cursor()

    species, new_zone = "cockroach", "pantry"

    # get the old hypothesis
    cur.execute("""SELECT id, statement FROM hypotheses
                   WHERE species=%s AND valid=true ORDER BY confidence DESC LIMIT 1""", (species,))
    old_id, old_statement = cur.fetchone()

    # get recent stats for the new zone
    cnt, hour, hum = recent_stats(cur, species, new_zone)
    print(f"Old hypothesis (id {old_id}): {old_statement}")
    print(f"New evidence: {cnt} detections at {new_zone}, hour {int(hour)}, {hum}% humidity\n")

    # ask Claude to formulate the new belief
    new_statement = new_statement_via_claude(species, new_zone, cnt, hour, hum, old_statement)
    print(f"New hypothesis: {new_statement}\n")

    # ===== THE ATOMIC TRANSACTION =====
    try:
        # 1. insert the new hypothesis, get its id
        cur.execute("""INSERT INTO hypotheses (statement, species, confidence, evidence_count, valid)
                       VALUES (%s, %s, %s, %s, true) RETURNING id""",
                    (new_statement, species, 0.9, cnt))
        new_id = cur.fetchone()[0]

        # 2. mark the old one superseded, pointing to the new one
        cur.execute("""UPDATE hypotheses
                       SET valid=false, superseded_by=%s
                       WHERE id=%s""", (new_id, old_id))

        conn.commit()  # both changes commit together, or neither
        print(f"✓ Atomic supersede complete.")
        print(f"  Old hypothesis {old_id} -> valid=false, superseded_by={new_id}")
        print(f"  New hypothesis {new_id} -> valid=true")
    except Exception as e:
        conn.rollback()
        print(f"✗ Transaction failed, rolled back: {e}")

    cur.close()
    conn.close()

if __name__ == "__main__":
    main()