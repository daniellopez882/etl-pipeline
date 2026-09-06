# ADR 0002 — Destinations and credentials are configuration; the default chain is the default

**Status:** accepted

## Context

```python
s3_bucket = 'waia-data-dump'
key = 'bootcamp2/etl/daniellopez882_online_trans_cleaned.csv'
```

Everyone who ran the job wrote to one bucket under one person's name. The
AWS secret was read from a variable called `aws_secret_access_key_id` —
neither the AWS name nor what it holds — and both credential values were
passed to `boto3.client` even when unset, which boto3 treats as "use the
default chain": a machine with any AWS credentials at all would have
uploaded with them, silently.

## Decision

`S3_BUCKET` is required for a live run and `S3_KEY` has a neutral default.
Redshift settings use `REDSHIFT_*`; AWS settings use the names AWS uses. The
old lowercase names, including the misnamed secret, are accepted as aliases
so an existing `.env` keeps working.

Explicit AWS credentials are used only when both halves are set. Otherwise
the client is built with no credentials and boto3's default chain applies —
the right behaviour for a container running under an instance role, and now
a documented choice rather than an accident of `None`.

`Settings.problems()` names every missing value; `main` reports them all at
once and exits 78 before any connection.

## Consequences

A test asserts no bucket or personal name remains in the source. A
misconfigured run fails in milliseconds with a list, not minutes in with a
traceback.
