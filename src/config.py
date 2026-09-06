"""
Settings.

The previous ``main.py`` read seven lowercase environment variables at
import, including one named ``aws_secret_access_key_id`` -- a name that is
neither the AWS one (``AWS_SECRET_ACCESS_KEY``) nor what it holds. The S3
destination -- a bucket and a key with a person's name in it -- was hardcoded.

Standard names now, with the old lowercase ones accepted so an existing
``.env`` keeps working. AWS credentials are optional: when unset, boto3's
default chain (instance role, profile, environment) applies, which is what a
container on AWS wants.
"""

from __future__ import annotations

import os

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

LEGACY = {
    "REDSHIFT_DB": "dbname",
    "REDSHIFT_HOST": "host",
    "REDSHIFT_PORT": "port",
    "REDSHIFT_USER": "user",
    "REDSHIFT_PASSWORD": "password",
    "AWS_ACCESS_KEY_ID": "aws_access_key_id",
    "AWS_SECRET_ACCESS_KEY": "aws_secret_access_key_id",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    REDSHIFT_DB: str = ""
    REDSHIFT_HOST: str = ""
    REDSHIFT_PORT: int = 5439
    REDSHIFT_USER: str = ""
    REDSHIFT_PASSWORD: str = ""
    CONNECT_TIMEOUT_SECONDS: int = Field(default=30, ge=1)

    S3_BUCKET: str = ""
    S3_KEY: str = "etl/online_transactions_cleaned.csv"

    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_DEFAULT_REGION: str = "us-east-1"

    LOG_LEVEL: str = "INFO"

    @model_validator(mode="after")
    def _accept_legacy_names(self) -> Settings:
        for new, old in LEGACY.items():
            current = getattr(self, new)
            if (current == "" or (new == "REDSHIFT_PORT" and current == 5439)) and os.getenv(old):
                value = os.getenv(old, "")
                object.__setattr__(self, new, int(value) if new == "REDSHIFT_PORT" else value)
        return self

    @property
    def has_explicit_aws_credentials(self) -> bool:
        return bool(self.AWS_ACCESS_KEY_ID.strip() and self.AWS_SECRET_ACCESS_KEY.strip())

    def problems(self, *, need_s3: bool = True) -> list[str]:
        found = [
            f"{name} is not set."
            for name in ("REDSHIFT_DB", "REDSHIFT_HOST", "REDSHIFT_USER", "REDSHIFT_PASSWORD")
            if not getattr(self, name).strip()
        ]
        if need_s3 and not self.S3_BUCKET.strip():
            found.append("S3_BUCKET is not set (the destination used to be a hardcoded bucket).")
        return found
