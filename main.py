"""
Extract online transactions from Redshift, drop duplicates, load to S3.

The previous ``main.py`` had no ``main()``: the pipeline ran at import. Any
``import main`` -- a test, a linter's plugin, an IDE -- connected to Redshift
and uploaded to S3. Every step printed; nothing returned a result or an exit
code; the destination was a hardcoded bucket and a key with a person's name.

    python main.py                 # Redshift -> dedupe -> s3://$S3_BUCKET/$S3_KEY
    python main.py --dry-run       # Redshift -> dedupe -> ./out/online_transactions_cleaned.csv
    python main.py --limit 1000    # a sample
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass

import pandas as pd

from src.config import Settings
from src.extract import extract_transaction_data
from src.load import s3_client, upload_frame, write_local
from src.transform import remove_duplicates

logger = logging.getLogger("etl")

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_CONFIG = 78


@dataclass(frozen=True)
class RunSummary:
    rows_extracted: int
    duplicates_removed: int
    rows_loaded: int
    destination: str
    seconds: float


def run(
    settings: Settings,
    *,
    dry_run: bool = False,
    limit: int | None = None,
    output: str = "out/online_transactions_cleaned.csv",
    extract: Callable[..., pd.DataFrame] | None = None,
    client_factory: Callable[[Settings], object] | None = None,
) -> RunSummary:
    """The pipeline. ``extract`` and ``client_factory`` are injectable for tests."""
    extract = extract or extract_transaction_data
    client_factory = client_factory or s3_client
    started = time.monotonic()
    frame = extract(settings, limit=limit)
    deduped = remove_duplicates(frame)
    if dry_run:
        destination = str(write_local(deduped.frame, output))
    else:
        destination = upload_frame(deduped.frame, settings.S3_BUCKET, settings.S3_KEY, client_factory(settings))
    return RunSummary(
        rows_extracted=deduped.rows_before,
        duplicates_removed=deduped.removed,
        rows_loaded=deduped.rows_after,
        destination=destination,
        seconds=round(time.monotonic() - started, 3),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Redshift -> dedupe -> S3")
    parser.add_argument("--dry-run", action="store_true", help="write a local CSV instead of uploading")
    parser.add_argument("--limit", type=int, default=None, help="extract at most this many rows")
    parser.add_argument("--output", default="out/online_transactions_cleaned.csv", help="dry-run destination")
    args = parser.parse_args(argv)

    settings = Settings()
    logging.basicConfig(level=settings.LOG_LEVEL, format="%(asctime)s %(levelname)-8s %(name)s %(message)s")

    problems = settings.problems(need_s3=not args.dry_run)
    if problems:
        for problem in problems:
            logger.error("configuration: %s", problem)
        return EXIT_CONFIG

    try:
        summary = run(settings, dry_run=args.dry_run, limit=args.limit, output=args.output)
    except Exception:
        logger.exception("pipeline failed")
        return EXIT_FAILED

    logger.info(
        "done: %d extracted, %d duplicates removed, %d loaded to %s in %.1fs",
        summary.rows_extracted,
        summary.duplicates_removed,
        summary.rows_loaded,
        summary.destination,
        summary.seconds,
    )
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
