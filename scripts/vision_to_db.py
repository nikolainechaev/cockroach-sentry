"""Part 7.3 - full pipeline: photo -> Claude Vision -> write detection to CockroachDB."""
import os
import re
import sys
import json
import uuid
import base64
from datetime import datetime
import boto3
import psycopg2
from dotenv import load_dotenv

load_dotenv()
CONN_STR = os.environ["DB_CONNECTION_STRING"]
bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")
MODEL_ID = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"

def identify_insect(image_path):
    with open(image_path, "rb") as f:
        image_b64 = base64.b64encode(f.read()).decode("utf-8")
    ext = image_path.lower().split(".")[-1]
    media_type = "image/png" if ext == "png" else "image/jpeg"
    prompt = """Identify the insect in this image. Respond with ONLY JSON:
{"insect_detected": true/false, "species": "cockroach|fly|ladybug|cicada|other|unknown", "confidence": 0.0-1.0}
No markdown."""
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 300,
        "messages": [{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": image_b64}},
            {"type": "text", "text": prompt},
        ]}],
    }
    resp = bedrock.invoke_model(modelId=MODEL_ID, body=json.dumps(body))
    text = json.loads(resp["body"].read())["content"][0]["text"].strip()
    text = re.sub(r"^```json\s*|\s*```$", "", text)
    return json.loads(text)

def write_detection(species, confidence, zone, s3_key=None):
    conn = psycopg2.connect(CONN_STR)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO detections
        (detected_at, camera_id, zone, species, species_confidence,
         confidence, track_id, snapshot_s3_key, lights_on)
        VALUES (now(), %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """, ("cam-kitchen-1", zone, species, confidence,
          confidence, str(uuid.uuid4()), s3_key, False))
    det_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    return det_id

if __name__ == "__main__":
    image_path = sys.argv[1] if len(sys.argv) > 1 else "scripts/roach.jpg"
    zone = sys.argv[2] if len(sys.argv) > 2 else "pantry"

    print(f"1. Analyzing photo: {image_path}")
    result = identify_insect(image_path)
    print(f"   -> {result}")

    if not result["insect_detected"]:
        print("   No insect detected, skipping.")
        sys.exit(0)

    print(f"2. Writing detection to database (zone: {zone})...")
    det_id = write_detection(result["species"], result["confidence"], zone)
    print(f"   -> Detection written with id {det_id}")
    print(f"\nDone! A {result['species']} sighting is now in the database.")