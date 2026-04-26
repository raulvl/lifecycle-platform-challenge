# lifecycle-platform-challenge

Automated SMS reactivation pipeline for a residential rental marketplace.
Replaces a manual ~9 hr/run Ruby workflow with a daily Airflow pipeline that segments an audience, validates it, sends via an ESP, and reports results.

---

## How to Run

### Prerequisites

- Python 3.11+
- `gcloud auth application-default login` (for BQ calls in production)

### Setup

```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Run Tests

```bash
pytest tests/ -v
```

All 16 tests should pass. Airflow imports are mocked in `tests/conftest.py` so no Airflow installation is needed for the test suite.

### Run the SQL Query

```bash
bq query --use_legacy_sql=false < sql/audience_segmentation.sql
```

Or paste `sql/audience_segmentation.sql` directly into the BigQuery console.

---

## Project Structure

```
sql/              # Part 1 — BigQuery audience segmentation
pipeline/         # Part 2 — campaign sender, dedup, ESP interface
dags/             # Part 3 — Airflow DAG
design/           # Parts 4 & 5 — design write-ups
tests/            # Unit tests (no Airflow install required)
ai-session/       # AI session logs (see submission requirements)
```

---

## Assumptions

1. **ESPClient is provided externally** — I implemented a stub in `pipeline/esp_client.py` for testing. In production this would be replaced by the real client library.
2. **Deduplication is single-worker** — `sent_renters.json` is file-based. This is appropriate for a single Airflow worker. At scale it would move to a `campaign_sends` database table with a unique constraint.
3. **BigQuery schema matches the spec exactly** — no additional normalization or partitioning assumed beyond what the challenge defines.
4. **GCP credentials available in the Airflow worker** — the DAG uses `google.cloud.bigquery` with application default credentials.
5. **`renter_send_scores` is date-partitioned on `scored_at`** — required for the `BigQueryTablePartitionExistenceSensor` in the Part 4 design.

---

## Design Decisions & Tradeoffs

**Deduplication via JSON file.**
Keeps the implementation zero-infra and fully auditable — the file is human-readable and the log persists across retries. Tradeoff: doesn't scale to parallel workers. Production alternative: a `campaign_sends` table with `UNIQUE(campaign_id, renter_id)`.

**Manual exponential backoff instead of `tenacity`.**
Keeps the core algorithm visible for reviewers and avoids an extra dependency. The pattern is identical to `tenacity`'s `wait_random_exponential`. I'd use `tenacity` in a shared library where the retry logic is reused across multiple services.

**Airflow TaskFlow API (`@task` decorator).**
Cleaner than `PythonOperator` — data flows between tasks via return values (XComs), dependencies are inferred automatically, and the DAG reads like regular Python. Requires Airflow 2.0+, which is standard.

**Lightweight test setup for DAG structure.**
`tests/conftest.py` mocks the Airflow SDK so the 16-test suite runs in ~2 seconds without a full Airflow install. This is a common pattern for CI pipelines. The tradeoff is the mocks need to stay in sync if Airflow's internal API changes.

**`CREATE OR REPLACE TABLE` in `run_audience_query`.**
Makes the task safely idempotent on re-runs — re-triggering the DAG overwrites the same staging table rather than appending duplicate rows.

---

## What I'd Do Differently With More Time

1. **Replace file-based dedup** with a `campaign_sends` BigQuery table — unlocks parallel workers and gives an audit trail queryable by the reporting team.
2. **Parameterize the SQL run date** using `@run_date` query parameter instead of `CURRENT_DATE()` — enables historical backfills without touching the query logic.
3. **Implement the circuit breaker** from `design/observability.md` as production code in `campaign_sender.py`.
4. **Add integration tests** using a mock BigQuery client (`google-cloud-testutils`) to test the full query-to-send flow end-to-end.
5. **Dockerize** the Airflow environment with `docker-compose.yml` for one-command local development.
6. **Emit Datadog custom metrics** from `log_and_notify` using the `datadog` Python SDK (outlined in `design/observability.md`).

---

## AI Usage

AI tools (Claude Code) were used throughout this challenge. Session logs are in `ai-session/`. The challenge explicitly allows and scores AI usage — see the `ai-session/` directory for exported logs.
