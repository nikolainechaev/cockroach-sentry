"""Part 4.6 - semantic search: find observations similar in MEANING to a query."""
import os
import json
import boto3
import psycopg2
from dotenv import load_dotenv

load_dotenv()
CONN_STR = os.environ["DB_CONNECTION_STRING"]
bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")

def get_embedding(text: str) -> list[float]:
    resp = bedrock.invoke_model(
        modelId="amazon.titan-embed-text-v2:0",
        body=json.dumps({"inputText": text}),
    )
    return json.loads(resp["body"].read())["embedding"]

def search(query: str, k: int = 5):
    vec = get_embedding(query)
    vec_str = "[" + ",".join(str(x) for x in vec) + "]"
    conn = psycopg2.connect(CONN_STR)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT summary, embedding <-> %s AS distance
        FROM observations
        ORDER BY distance
        LIMIT %s
        """,
        (vec_str, k),
    )
    results = cur.fetchall()
    cur.close()
    conn.close()
    return results

if __name__ == "__main__":
    queries = [
        "cockroach activity near the dishwasher at night",
        "flying insects by the window during daytime",
        "warm humid conditions with pests",
    ]
    for q in queries:
        print(f"\n=== Query: '{q}' ===")
        for summary, dist in search(q):
            print(f"  [{dist:.3f}] {summary}")