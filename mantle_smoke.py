import json
import boto3
import requests

from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest

region = "us-east-2"
url = f"https://bedrock-mantle.{region}.api.aws/openai/v1/responses"

session = boto3.Session(region_name=region)
credentials = session.get_credentials()

if credentials is None:
    raise RuntimeError("No AWS credentials configured")

payload = {
    "model": "openai.gpt-5.6-luna",
    "input": "Reply with exactly: AEGIS AWS connection successful.",
    "max_output_tokens": 100,
    "reasoning": {"effort": "none"},
    "store": False,
}

body = json.dumps(payload).encode("utf-8")

request = AWSRequest(
    method="POST",
    url=url,
    data=body,
    headers={"Content-Type": "application/json"},
)

SigV4Auth(
    credentials.get_frozen_credentials(),
    "bedrock-mantle",
    region,
).add_auth(request)

prepared = request.prepare()

response = requests.post(
    url,
    data=body,
    headers=dict(prepared.headers),
    timeout=30,
)

print("HTTP status:", response.status_code)

if response.ok:
    data = response.json()
    print("Model:", data.get("model"))
    print("Usage:", data.get("usage"))
    print("Output:", json.dumps(data.get("output", []), indent=2)[:2000])
else:
    print("AWS error:", response.text[:1500])
