# lifecycle-platform-challenge

Automated SMS reactivation pipeline for a residential rental marketplace.
Replaces a manual ~9 hr/run Ruby workflow with a daily Airflow pipeline.

---

## Project Goal

Build the core of an automated pipeline that:
- Segments a reactivation audience from BigQuery
- Sends batched SMS campaigns through an ESP API
- Orchestrates the full flow via an Airflow DAG
- Is observable, idempotent, and resilient to partial failures

---

## Parts Overview

| Part | Deliverable |
|---|---|
| 1 | BigQuery audience segmentation query |
| 2 | Python pipeline module (batching, dedup, retries, metrics) |
| 3 | Airflow DAG with 4 tasks (query → validate → send → report) |
| 4 | Written design: integrating a conversion probability ML model |
| 5 | Written design: observability, double-send prevention, ESP failure recovery |

---

## Key Constraints

**SQL (Part 1)**
- BigQuery only — use `CURRENT_TIMESTAMP()` / `CURRENT_DATE()`, never `NOW()`
- Query must be idempotent (same result if run twice on the same day)
- Suppression exclusion via `LEFT JOIN + IS NULL`, not `NOT IN`
- Handle NULLs explicitly: `phone`, `dnd_until`

**Pipeline (Part 2)**
- ESP accepts max 100 recipients per batch
- Retry on HTTP 429 and 5xx with exponential backoff + jitter (max 5 retries)
- Fail fast on 4xx client errors
- Deduplication must be stable across retries
- A single failed batch must not abort the full run — log and continue
- Return summary: `total_sent`, `total_failed`, `total_skipped`, `elapsed_seconds`

**DAG (Part 3)**
- Daily at 5:00 AM UTC; SLA deadline at 8:00 AM UTC
- 2 retries per task, 5-minute delay between retries
- Linear task dependencies: query → validate → send → report
- Validation task must raise on empty or anomalous audience (do not send blindly)
- Use TaskFlow API (`@task` decorator)

---

## Coding Conventions

- Type hints on all function signatures
- `logging` module only — no `print()`; structured `key=value` log lines
- `except Exception as e` in batch/retry loops — never swallow silently
- f-strings, 4-space indent
- No module-level globals — pass data explicitly between functions and tasks
