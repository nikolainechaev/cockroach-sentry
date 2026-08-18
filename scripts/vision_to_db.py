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
S3_BUCKET = os.environ.get("S3_BUCKET", "cockroach-sentry-snapshots-189924573299")
bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")
s3 = boto3.client("s3", region_name="us-east-1")
MODEL_ID = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"

def wait_for_motion(pin=17, timeout=None):
    import gpiod
    from gpiod.line import Direction, Value
    import time
    settings = gpiod.LineSettings(direction=Direction.INPUT)
    with gpiod.request_lines("/dev/gpiochip0", consumer="pir-trigger", config={pin: settings}) as req:
        start = time.time()
        while timeout is None or time.time() - start < timeout:
            if req.get_value(pin) == Value.ACTIVE:
                # debounce: require 1s of continuous INACTIVE before re-arming.
                # PIR output flickers active/inactive while motion continues, so a
                # single momentary low reading isn't enough to call it settled.
                quiet_since = None
                while True:
                    if req.get_value(pin) == Value.ACTIVE:
                        quiet_since = None
                    elif quiet_since is None:
                        quiet_since = time.time()
                    elif time.time() - quiet_since > 1.0:
                        break
                    time.sleep(0.1)
                return True
            time.sleep(0.1)
        return False

def read_climate(pin=4, retries=3):
    import adafruit_dht
    import board
    import time
    d = adafruit_dht.DHT22(getattr(board, f"D{pin}"))
    for _ in range(retries):
        try:
            return d.temperature, d.humidity
        except RuntimeError:
            time.sleep(2)
    return None, None

def capture_photo(path):
    from picamera2 import Picamera2
    import time
    picam2 = Picamera2()
    picam2.configure(picam2.create_still_configuration())
    picam2.start()
    time.sleep(2)  # let AE/AWB settle
    picam2.capture_file(path)
    picam2.stop()
    picam2.close()
    time.sleep(0.5)  # let libcamera fully release the device before the next open
    return path

def upload_snapshot(image_path, zone):
    key = f"{zone}/{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}.jpg"
    s3.upload_file(image_path, S3_BUCKET, key)
    return key

def identify_insect(image_path):
    with open(image_path, "rb") as f:
        image_b64 = base64.b64encode(f.read()).decode("utf-8")
    ext = image_path.lower().split(".")[-1]
    media_type = "image/png" if ext == "png" else "image/jpeg"
    prompt = """Carefully examine this image for any insect or small creature (for example: cockroach, fly, ladybug, cicada, ant, spider, beetle, moth, or snake).

Set insect_detected to true whenever any of these creatures is clearly visible in the frame — this includes snake, even though it isn't technically an insect. Only set it to false if the scene is empty, or you're not confident what you're seeing. Don't guess a species just because one is expected.

Respond with ONLY JSON:
{"insect_detected": true/false, "species": "cockroach|fly|ladybug|cicada|ant|spider|beetle|moth|snake|other|unknown", "confidence": 0.0-1.0}
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

def write_detection(species, confidence, zone, s3_key=None, ambient_temp=None, ambient_humidity=None):
    conn = psycopg2.connect(CONN_STR)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO detections
        (detected_at, camera_id, zone, species, species_confidence,
         confidence, track_id, snapshot_s3_key, ambient_temp, ambient_humidity, lights_on)
        VALUES (now(), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """, ("cam-kitchen-1", zone, species, confidence,
          confidence, str(uuid.uuid4()), s3_key, ambient_temp, ambient_humidity, False))
    det_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    return det_id

def run_once(image_path, zone):
    if image_path is None:
        import time
        print("1. Waiting for PIR motion trigger...")
        wait_for_motion()
        print("   -> motion detected, pausing 3s before capture...")
        time.sleep(3)
        image_path = capture_photo(f"/tmp/capture-{uuid.uuid4().hex[:8]}.jpg")
        print(f"   -> saved to {image_path}")
    else:
        print(f"1. Using existing photo: {image_path}")

    print("1b. Reading climate sensor...")
    ambient_temp, ambient_humidity = read_climate()
    print(f"   -> temp={ambient_temp} humidity={ambient_humidity}")

    print("2. Analyzing photo with Claude Vision...")
    result = identify_insect(image_path)
    print(f"   -> {result}")

    if not result["insect_detected"]:
        print("   No insect detected, skipping.")
        return None

    print("3. Uploading snapshot to S3...")
    s3_key = upload_snapshot(image_path, zone)
    print(f"   -> s3://{S3_BUCKET}/{s3_key}")

    print(f"4. Writing detection to database (zone: {zone})...")
    det_id = write_detection(result["species"], result["confidence"], zone, s3_key=s3_key,
                              ambient_temp=ambient_temp, ambient_humidity=ambient_humidity)
    print(f"   -> Detection written with id {det_id}")
    print(f"\nDone! A {result['species']} sighting is now in the database.")
    return det_id

if __name__ == "__main__":
    import time
    arg1 = sys.argv[1] if len(sys.argv) > 1 else None

    if arg1 and os.path.isfile(arg1):
        # single-shot test mode: analyze an existing photo, no PIR wait, no looping
        zone = sys.argv[2] if len(sys.argv) > 2 else "pantry"
        run_once(arg1, zone)
    else:
        # daemon mode: loop forever, PIR-triggered
        zone = arg1 or os.environ.get("SENTRY_ZONE", "pantry")
        print(f"Starting sentry daemon (zone={zone}). Waiting for motion...")
        while True:
            try:
                run_once(None, zone)
            except BaseException as e:
                print(f"Error in cycle: {e}")
            time.sleep(8)