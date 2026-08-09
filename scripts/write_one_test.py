"""Part 4.3 - write ONE observation with its embedding to test the VECTOR format."""
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

if __name__ == "__main__":
    summary = "13 cockroach detections near the dishwasher at night, warm and humid"
    species = "cockroach"
    zone = "dishwasher"

    print("Getting embedding...")
    vec = get_embedding(summary)
    print(f"Got vector of length {len(vec)}")

    # CockroachDB VECTOR wants a string like '[0.1,0.2,...]'
    vec_str = "[" + ",".join(str(x) for x in vec) + "]"

    print("Inserting into observations...")
    conn = psycopg2.connect(CONN_STR)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO observations (summary, embedding, species, zone)
        VALUES (%s, %s, %s, %s)
        """,
        (summary, vec_str, species, zone),
    )
    conn.commit()

    # verify it landed
    cur.execute("SELECT COUNT(*) FROM observations")
    total = cur.fetchone()[0]
    print(f"Success! observations table now has {total} row(s).")
    cur.close()
    conn.close()