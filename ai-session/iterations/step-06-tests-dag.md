# Step 6 — Tests: DAG

**Files:** `tests/test_dag.py`, `tests/conftest.py`

## What was tested

Seven structural tests — no task logic executes, only DAG shape is verified:

- DAG imports without error
- Schedule is `"0 5 * * *"`
- Exactly 4 tasks registered
- Task IDs match the expected set
- Every task inherits `retries=2` and `retry_delay=timedelta(minutes=5)`
- `catchup=False` (production safeguard — see below)
- Linear dependency chain: `run_audience_query` → `validate_audience` → `execute_send` → `log_and_notify`

## Change made this step

`_FakeDAG` in `conftest.py` accepted `catchup` as a constructor argument but never
stored it as an instance attribute. Added `self.catchup = catchup` so the value is
accessible to tests.

Added `test_dag_no_catchup`: asserts `dag.catchup is False`. The comment in the
test explains the production risk: `start_date=2024-01-01` with `catchup=True`
would trigger a backfill run for every day since that date on first deploy, sending
SMS to the full reactivation audience hundreds of times.

## Notable points

- `_load_dag()` force-reimports the module each test call — prevents stale mock
  state from one test affecting the next.
- `conftest.py` stubs Airflow, GCP, and Slack provider imports at session scope
  so tests run without any external dependencies installed.

All 7 tests pass.
