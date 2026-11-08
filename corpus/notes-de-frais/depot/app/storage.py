import uuid

import boto3

from .config import settings

_s3 = boto3.client("s3", endpoint_url=settings.s3_endpoint)


def save_receipt(content: bytes, content_type: str) -> str:
    key = f"receipts/{uuid.uuid4()}"
    _s3.put_object(Bucket=settings.s3_bucket, Key=key, Body=content, ContentType=content_type)
    return key


def load_receipt(key: str) -> tuple[bytes, str]:
    obj = _s3.get_object(Bucket=settings.s3_bucket, Key=key)
    return obj["Body"].read(), obj["ContentType"]
