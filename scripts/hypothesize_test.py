"""Part 5.2 - feed patterns to Claude, get formulated hypotheses (no writing yet)."""
import os
import json
import boto3
import psycopg2
from dotenv import load_dotenv

load_dotenv()
CONN_STR = os.environ["DB_CONNECTION_STRING"]
bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")

MODEL_ID = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"  # adjust if needed

def get_patterns():
    conn = psycopg2.connect(CONN_STR)
    cur = conn.cursor()
    cur.execute("""
        SELECT species, zone, COUNT(*) AS total,
               ROUND(AVG(EXTRACT(HOUR FROM detected_at))::numeric,0) AS avg_hour,
               ROUND(AVG(ambient_temp)::numeric,1) AS avg_temp,
               ROUND(AVG(ambient_humidity)::numeric,1) AS avg_hum
        FROM detections GROUP BY species, zone
        HAVING COUNT(*) >= 10 ORDER BY species, total DESC
    """)
    rows = cur.fetchall()
    cur.close(); conn.close()
    return rows

def ask_claude(patterns_text):
    prompt = f"""You are a pest-monitoring agent. Based on this detection data, form 3-5 concise hypotheses about insect behavior in this home. Each hypothesis should be one sentence, actionable, and reference specific zones/times.

Detection patterns:
{patterns_text}

Respond with ONLY a JSON array of objects, each like:
{{"statement": "...", "species": "...", "confidence": 0.0-1.0}}
No other text."""

    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 1000,
        "messages": [{"role": "user", "content": prompt}],
    }
    resp = bedrock.invoke_model(modelId=MODEL_ID, body=json.dumps(body))
    result = json.loads(resp["body"].read())
    return result["content"][0]["text"]

if __name__ == "__main__":
    rows = get_patterns()
    patterns_text = "\n".join(
        f"{s} at {z}: {t} detections, avg hour {int(h)}, {temp}C, {hum}% humidity"
        for s, z, t, h, temp, hum in rows
    )
    print("Sending patterns to Claude...\n")
    hypotheses = ask_claude(patterns_text)
    print("Claude's hypotheses:")
    print(hypotheses)