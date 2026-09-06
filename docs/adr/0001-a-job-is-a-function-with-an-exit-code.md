# ADR 0001 — A job is a function with an exit code, not a script that runs on import

**Status:** accepted

## Context

`main.py` had no `main()`. Reading the environment, connecting to Redshift,
running the query, deduplicating and uploading to S3 were module-level
statements. Reproduced on the original: `import main` with a fake `.env`
attempted the Redshift connection.

Consequences of that shape: nothing could be imported for a test; a linter
plugin or an IDE that imports modules would have run the job; every step
`print`ed and nothing returned, so a scheduler could tell success from
failure only by reading stdout; a missing setting surfaced as a
`psycopg2` traceback several steps in.

## Decision

`run(settings, ...) -> RunSummary` is the pipeline: extract, dedupe, load,
returning the counts and the destination. `main(argv) -> int` parses
arguments, builds settings, reports configuration problems and returns
**78** (`EX_CONFIG`) before touching a network, returns **1** on a logged
failure, **0** on success. The `__main__` guard calls `sys.exit(main())`.

The extractor and the S3 client factory are parameters of `run`, resolved at
call time, so the tests drive the whole pipeline with an in-memory frame and
a recording client. A test walks `main.py`'s AST and fails if any statement
at module level is a call.

`--dry-run` writes the CSV locally and needs no bucket; `--limit` caps the
extraction for a sample run.

## Consequences

CI imports `main` and requires nothing to happen, then runs it unconfigured
and requires exit 78. The container's exit code is the job's result.
