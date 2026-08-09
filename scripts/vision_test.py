"""Part 7.2 - Claude Vision: identify insect species from a photo."""
import os
import json
import base64
import sys
import boto3
from dotenv import load_dotenv

load_dotenv()
bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")
MODEL_ID = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"

def identify_insect(image_path: str) -> dict:
    # read image as base64
    with open(image_path, "rb") as f:
        image_bytes = f.read()
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")

    # detect media type from extension
    ext = image_path.lower().split(".")[-1]
    media_type = "image/png" if ext == "png" else "image/jpeg"

    prompt = """Look at this image. Identify if there is an insect and what species/type it is.
Respond with ONLY a JSON object like:
{"insect_detected": true/false, "species": "cockroach|fly|ladybug|cicada|other|unknown", "confidence": 0.0-1.0, "description": "brief visual description"}
No other text, no markdown."""

    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 500,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image", "source": {
                    "type": "base64", "media_type": media_type, "data": image_b64
                }},
                {"type": "text", "text": prompt},
            ],
        }],
    }

    resp = bedrock.invoke_model(modelId=MODEL_ID, body=json.dumps(body))
    text = json.loads(resp["body"].read())["content"][0]["text"].strip()
    # strip markdown fences if present
    import re
    text = re.sub(r"^```json\s*|\s*```$", "", text)
    return json.loads(text)

if __name__ == "__main__":
    image_path = sys.argv[1] if len(sys.argv) > 1 else "scripts/test_bug.jpg"
    print(f"Analyzing image: {image_path}\n")
    result = identify_insect(image_path)
    print("Claude Vision result:")
    print(f"  Insect detected: {result['insect_detected']}")
    print(f"  Species: {result['species']}")
    print(f"  Confidence: {result['confidence']}")
    print(f"  Description: {result['description']}")