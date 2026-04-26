# lifecycle-platform-challenge

Automated SMS reactivation pipeline for a residential rental marketplace.
Replaces a manual ~9 hr/run Ruby workflow with a daily Airflow pipeline.

## Quick Start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest tests/ -v
```

## Architecture

| Directory | What's inside |
|---|---|
| `sql/` | BigQuery audience segmentation query (Part 1) |
| `pipeline/` | ESP send logic: dedup, batching, exponential backoff (Part 2) |
| `dags/` | Airflow DAG — 4-task linear pipeline (Part 3) |
| `design/` | Model integration + observability write-ups (Parts 4 & 5) |
| `tests/` | Unit tests; `conftest.py` mocks Airflow for lightweight CI |

## Conventions

- Type hints on all function signatures
- `logging` module only — no `print()`; log with `key=value` pairs
- Always `except Exception as e` in batch loops — never swallow silently
- f-strings, 4-space indent

## Part 1 (SQL)

- Use `CURRENT_TIMESTAMP()` / `CURRENT_DATE()` — **never `NOW()`** (non-deterministic in BigQuery)
- Suppression exclusion uses `LEFT JOIN + IS NULL` — not `NOT IN` (breaks with NULLs)
- `dnd_until IS NULL` means no restriction; always OR with the timestamp check

## Part 2 (Pipeline)

- `ESPClient.send_batch()` is the provided interface — **do not change its signature**
- Dedup key format: `"{campaign_id}:{renter_id}"` — must stay stable across retries
- Batch size is 100 (ESP hard limit); use `_batch_size` param only in tests
- Retry on 429 and 5xx; fail fast on 4xx client errors
- One failed batch must NOT raise — catch, log with renter IDs, continue

## Part 3 (DAG)

- TaskFlow API (`@task` decorator inside a `with DAG(...)` block)
- Pass data between tasks via return values (XCom) — no module-level globals
- `sla=timedelta(hours=3)` in `default_args` — 5 AM start must finish by 8 AM
- The validation task raises `ValueError` to abort on empty or anomalous audiences

## Parts 4 & 5 (Design)

Design docs only — see `design/model_integration.md` and `design/observability.md`.
The circuit breaker pattern from `observability.md` is pseudocode; integrate into
`campaign_sender.py` if implementing in production.
