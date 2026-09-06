"""
Write a frame to S3 as CSV, or to a local file.

The previous loader built a boto3 client with whatever ``aws_access_key_id``
and ``aws_secret_access_key_id`` (sic) held -- ``None`` when unset, which
boto3 silently treats as "use the default credential chain" -- and uploaded
to a hardcoded bucket. The client is injectable so the upload is testable
without AWS, and the destination is configuration.
"""

from __future__ import annotations

import logging
from io import StringIO
from pathlib import Path
from typing import Any

import pandas as pd

from src.config import Settings

logger = logging.getLogger("etl.load")


def frame_to_csv_bytes(frame: pd.DataFrame) -> bytes:
    buffer = StringIO()
    frame.to_csv(buffer, index=False)
    return buffer.getvalue().encode("utf-8")


def s3_client(settings: Settings) -> Any:
    import boto3

    if settings.has_explicit_aws_credentials:
        return boto3.client(
            "s3",
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_DEFAULT_REGION,
        )
    return boto3.client("s3", region_name=settings.AWS_DEFAULT_REGION)


def upload_frame(frame: pd.DataFrame, bucket: str, key: str, client: Any) -> str:
    """Upload ``frame`` as CSV and return its ``s3://`` URI."""
    body = frame_to_csv_bytes(frame)
    client.put_object(Bucket=bucket, Key=key, Body=body, ContentType="text/csv")
    uri = f"s3://{bucket}/{key}"
    logger.info("uploaded %d bytes (%d rows) to %s", len(body), len(frame), uri)
    return uri


def write_local(frame: pd.DataFrame, path: str | Path) -> Path:
    """Write the CSV locally instead of uploading -- the dry-run destination."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(frame_to_csv_bytes(frame))
    logger.info("wrote %d rows to %s", len(frame), target)
    return target
