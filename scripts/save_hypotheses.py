"""Part 5.3 - generate hypotheses via Claude and save them to the hypotheses table."""
import os
import re
import json
import boto3
import psycopg2
from dotenv import load_dotenv

load_dotenv()
CONN_STR = os.environ["DB_CONNECTION_STRING"]
bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")
MODEL_ID = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"

def get_patterns(cur):
    cur.execute("""
        SELECT species, zone, COUNT(*) AS total,
               ROUND(AVG(EXTRACT(HOUR FROM detected_at))::numeric,0) AS avg_hour,
               ROUND(AVG(ambient_temp)::numeric,1) AS avg_temp,
               ROUND(AVG(ambient_humidity)::numeric,1) AS avg_hum
        FROM detections GROUP BY species, zone
        HAVING COUNT(*) >= 10 ORDER BY species, total DESC
    """)
    return cur.fetchall()

def ask_claude(patterns_text):
    prompt = f"""You are a pest-monitoring agent. Based on this detection data, form 3-5 concise hypotheses about insect behavior in this home. Each hypothesis should be one sentence, actionable, and reference specific zones/times.

Detection patterns:
{patterns_text}

Respond with ONLY a JSON array of objects, each like:
{{"statement": "...", "species": "...", "confidence": 0.0-1.0}}
No other text, no markdown."""
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 1000,
        "messages": [{"role": "user", "content": prompt}],
    }
    resp = bedrock.invoke_model(modelId=MODEL_ID, body=json.dumps(body))
    text = json.loads(resp["body"].read())["content"][0]["text"]
    # strip markdown fences if present
    text = re.sub(r"^```json\s*|\s*```$", "", text.strip())
    return json.loads(text)

def main():
    conn = psycopg2.connect(CONN_STR)
    cur = conn.cursor()

    # clear old hypotheses so re-running is clean
    cur.execute("DELETE FROM hypotheses")
    conn.commit()
    print("Cleared old hypotheses.")

    patterns = get_patterns(cur)
    patterns_text = "\n".join(
        f"{s} at {z}: {t} detections, avg hour {int(h)}, {temp}C, {hum}% humidity"
        for s, z, t, h, temp, hum in patterns
    )
    print("Asking Claude for hypotheses...")
    hyps = ask_claude(patterns_text)

    for h in hyps:
        cur.execute(
            """INSERT INTO hypotheses (statement, species, confidence, evidence_count, valid)
               VALUES (%s, %s, %s, %s, true)""",
            (h["statement"], h.get("species", "unknown"), h["confidence"], 0),
        )
    conn.commit()

    cur.execute("SELECT COUNT(*) FROM hypotheses WHERE valid = true")
    total = cur.fetchone()[0]
    print(f"\nSaved {total} hypotheses to the database.")

    print("\nCurrent hypotheses:")
    cur.execute("SELECT statement, confidence FROM hypotheses WHERE valid = true ORDER BY confidence DESC")
    for stmt, conf in cur.fetchall():
        print(f"  [{conf}] {stmt}")

    cur.close()
    conn.close()

if __name__ == "__main__":
    main()