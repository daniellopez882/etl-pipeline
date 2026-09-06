"""Remove exact duplicate rows and say how many there were."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import pandas as pd

logger = logging.getLogger("etl.transform")


@dataclass(frozen=True)
class DedupeResult:
    frame: pd.DataFrame
    rows_before: int
    rows_after: int

    @property
    def removed(self) -> int:
        return self.rows_before - self.rows_after


def remove_duplicates(frame: pd.DataFrame) -> DedupeResult:
    """Drop exact duplicate rows, keeping the first. Returns the frame and the counts."""
    before = len(frame)
    cleaned = frame.drop_duplicates(keep="first").reset_index(drop=True)
    result = DedupeResult(cleaned, before, len(cleaned))
    if result.removed:
        logger.info("removed %d duplicate row(s): %d -> %d", result.removed, before, result.rows_after)
    else:
        logger.info("no duplicate rows in %d", before)
    return result


# Kept for callers of the old name.
def identify_and_remove_duplicated_data(frame: pd.DataFrame) -> pd.DataFrame:
    return remove_duplicates(frame).frame
