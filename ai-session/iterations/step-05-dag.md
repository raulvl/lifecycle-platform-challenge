# Step 5 — Airflow DAG

**File:** `dags/sms_reactivation_dag.py`

## What was built

Four-task linear DAG using the TaskFlow API:
`run_audience_query` → `validate_audience` → `execute_send` → `log_and_notify`

## Configuration

- Schedule: `"0 5 * * *"` (daily at 05:00 UTC)
- `catchup=False` — no backfill on first deploy
- `retries=2`, `retry_delay=timedelta(minutes=5)` in `default_args`
- `sla=timedelta(hours=3)` — 5 AM start must finish by 8 AM

## Key decisions

- **`CREATE OR REPLACE TABLE` for staging** — makes `run_audience_query` safely re-runnable; retrying the task won't leave orphan tables or duplicate rows.
- **`context["ds"]` for run date** — Airflow's logical date, stable across retries for the same DAG run. Used to name the staging table and construct the `campaign_id`.
- **`campaign_id` encodes run date** — `sms_reactivation_YYYYMMDD` ensures dedup keys in the sent log are scoped to the logical run date, not wall time. Task 3 retries safely.
- **`validate_audience` raises `ValueError`** — Airflow marks the task failed and halts the DAG before any sends happen. Two guards: empty audience and >2× 7-day rolling average (data anomaly detection).
- **Slack stub** — `SlackWebhookNotifier` is commented out with wiring instructions. Keeps the skeleton runnable without a Slack connection configured.
- **Data passing via XCom return values** — no module-level globals; each task receives its upstream result as a typed function argument.

## Change made this step

`log_and_notify` originally used f-string interpolation to build the INSERT statement.
Replaced with BigQuery parameterized queries (`bigquery.QueryJobConfig` +
`bigquery.ScalarQueryParameter`). The values are internal and typed, so there was
no real injection risk — but parameterized queries enforce type coercion at the
driver level, prevent accidental format issues (e.g. floats with locale-specific
decimal separators), and establish the correct pattern for any future queries in
this task that might take less controlled input.

All 6 DAG tests pass.
