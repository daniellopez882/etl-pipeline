# Threat model

Scope: a one-shot job with read access to a Redshift database and write
access to one S3 key. No network surface of its own.

## What it holds

| Asset | Where | Why it matters |
|---|---|---|
| Redshift credentials | `.env` / environment | Read access to the transactions data |
| AWS credentials (optional) | `.env` / environment / instance role | Write access to the bucket |
| The extracted data | memory, then S3 (or `./out/` in a dry run) | Customer ids and purchase records |

`.env` is gitignored and CI fails if one is ever tracked; `out/` is
gitignored so a dry-run CSV of customer data is not committed by accident.

## Threats

### T1 — Data written to the wrong place *(was open)*

The destination was a hardcoded bucket. It is configuration now, required
for a live run, and a test asserts the old bucket and name are gone.

### T2 — Ambient credentials used without intent *(was open)*

Unset credentials were passed as `None` and boto3 fell back to the default
chain silently. The fallback is now explicit and documented; explicit
credentials are used only when both halves are set.

### T3 — Secrets in the image or the log

The old image copied the whole tree; a local `.env` would have been baked
in. The image copies `main.py` and `src/` only and runs as uid 10001.
Nothing logs credential values.

### T4 — Supply chain

Three unpinned packages on an end-of-life Python. Everything is pinned;
`pip-audit`, `bandit` and gitleaks run in CI.

## Not addressed

- The job holds the whole result set in memory.
- No integrity check on the uploaded object (no checksum recorded).
- The data it moves is personal (customer ids); retention and access on the
  bucket are outside this repository.
