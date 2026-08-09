"""Part 4.1 - test that we can get an embedding from Bedrock."""
import json
import boto3

bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")

def get_embedding(text: str) -> list[float]:
    """Turn a text string into a 1024-dim vector using Titan."""
    response = bedrock.invoke_model(
        modelId="amazon.titan-embed-text-v2:0",
        body=json.dumps({"inputText": text}),
    )
    result = json.loads(response["body"].read())
    return result["embedding"]

if __name__ == "__main__":
    text = "3 cockroach detections near the dishwasher at night, warm and humid"
    vec = get_embedding(text)
    print(f"Text: {text}")
    print(f"Embedding length: {len(vec)}")
    print(f"First 5 values: {vec[:5]}")