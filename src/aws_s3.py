"""Optional S3 document synchronization primitives; no calls occur at import time."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class S3Document:
    key: str
    etag: str | None
    content: str


class S3DocumentSource:
    def __init__(self, bucket: str, prefix: str = "documents/", region: str | None = None, client=None):
        self.bucket, self.prefix, self.region, self.client = bucket, prefix, region, client

    def _client(self):
        import boto3
        return self.client or boto3.client("s3", region_name=self.region)

    def list_json_keys(self) -> list[str]:
        keys = []
        token = None
        while True:
            request = {"Bucket": self.bucket, "Prefix": self.prefix}
            if token:
                request["ContinuationToken"] = token
            response = self._client().list_objects_v2(**request)
            keys.extend(obj["Key"] for obj in response.get("Contents", []) if obj["Key"].endswith(".json"))
            if not response.get("IsTruncated"):
                return sorted(keys)
            token = response.get("NextContinuationToken")

    def fetch(self, key: str) -> S3Document:
        response = self._client().get_object(Bucket=self.bucket, Key=key)
        body = response["Body"].read().decode("utf-8")
        json.loads(body)
        return S3Document(key=key, etag=response.get("ETag"), content=body)

    def sync_to_directory(self, directory: str | Path) -> dict[str, int]:
        target = Path(directory).resolve()
        target.mkdir(parents=True, exist_ok=True)
        written = 0
        keys = self.list_json_keys()
        for key in keys:
            relative_key = key.removeprefix(self.prefix)
            relative = Path(relative_key)
            if not relative_key or relative.is_absolute() or ".." in relative.parts:
                raise ValueError("S3 object key escapes the configured document directory")
            output = (target / relative).resolve()
            if output != target and target not in output.parents:
                raise ValueError("S3 object key escapes the configured document directory")
            document = self.fetch(key)
            output.parent.mkdir(parents=True, exist_ok=True)
            if not output.exists() or output.read_text(encoding="utf-8") != document.content:
                output.write_text(document.content, encoding="utf-8")
                written += 1
        return {"seen": len(keys), "written": written}


def classify_aws_error(exc: Exception) -> str:
    code = getattr(exc, "response", {}).get("Error", {}).get("Code", "")
    if code in {"AccessDenied", "AccessDeniedException", "UnauthorizedOperation"}:
        return "access_denied"
    if code in {"SlowDown", "ThrottlingException", "ServiceQuotaExceededException"}:
        return "throttled_or_quota"
    if code in {"NoSuchBucket", "NoSuchKey", "ResourceNotFoundException"}:
        return "resource_unavailable"
    return "aws_error"


def content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()
