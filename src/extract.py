"""
Extract online transactions from Redshift, with the cleaning done in SQL.

The connection used to be opened and never closed, and the query was run
through ``pd.read_sql`` on a raw DBAPI connection, which pandas warns about.
The connection is a context manager now and the cursor is read directly.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pandas as pd

from src.config import Settings

logger = logging.getLogger("etl.extract")

QUERY = """
SELECT ot.invoice,
       ot.stock_code,
       CASE WHEN s.description IS NULL THEN 'Unknown' ELSE s.description END AS description,
       ot.price,
       ot.quantity,
       ot.price * ot.quantity AS total_order_value,
       CAST(ot.invoice_date AS TIMESTAMP) AS invoice_date,
       ot.customer_id,
       ot.country
FROM bootcamp.online_transactions ot
LEFT JOIN (
    SELECT * FROM bootcamp.stock_description WHERE description <> '?'
) AS s ON ot.stock_code = s.stock_code
WHERE ot.customer_id <> ''
  AND ot.stock_code NOT IN ('BANK CHARGES', 'POST', 'D', 'M', 'CRUK')
"""

COLUMNS = [
    "invoice",
    "stock_code",
    "description",
    "price",
    "quantity",
    "total_order_value",
    "invoice_date",
    "customer_id",
    "country",
]


@contextmanager
def redshift_connection(settings: Settings) -> Iterator[Any]:
    import psycopg2

    conn = psycopg2.connect(
        dbname=settings.REDSHIFT_DB,
        host=settings.REDSHIFT_HOST,
        port=settings.REDSHIFT_PORT,
        user=settings.REDSHIFT_USER,
        password=settings.REDSHIFT_PASSWORD,
        connect_timeout=settings.CONNECT_TIMEOUT_SECONDS,
    )
    try:
        yield conn
    finally:
        conn.close()


def rows_to_frame(rows: list[tuple], columns: list[str]) -> pd.DataFrame:
    frame = pd.DataFrame.from_records(rows, columns=columns)
    if "invoice_date" in frame.columns:
        frame["invoice_date"] = pd.to_datetime(frame["invoice_date"])
    return frame


def extract_transaction_data(settings: Settings, *, limit: int | None = None) -> pd.DataFrame:
    """Run the extraction query. ``limit`` caps the rows, for a sample run."""
    sql = QUERY.strip()
    if limit is not None:
        sql = f"{sql}\nLIMIT {int(limit)}"
    with redshift_connection(settings) as conn, conn.cursor() as cursor:
        cursor.execute(sql)
        rows = cursor.fetchall()
        columns = [col[0] for col in cursor.description]
    frame = rows_to_frame(rows, columns)
    logger.info("extracted %d rows, %d columns", *frame.shape)
    return frame
