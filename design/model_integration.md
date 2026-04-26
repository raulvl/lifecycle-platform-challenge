# Part 4 — Value Model Integration Design

## 1. BigQuery Query Modification

Add an `INNER JOIN` against the scoring table inside the existing CTE structure.
The threshold and model version are BigQuery query parameters — set as Airflow DAG params so they can be changed per run without touching SQL.

```sql
-- Add after the suppression LEFT JOIN in audience_segmentation.sql:
INNER JOIN ml_predictions.renter_send_scores scores
  ON  p.renter_id = scores.renter_id
  AND DATE(scores.scored_at) = CURRENT_DATE()
  AND scores.predicted_conversion_probability >= @score_threshold
  AND scores.model_version = @model_version
```

Corresponding DAG params:

```python
# dags/sms_reactivation_dag.py
with DAG(
    dag_id="sms_reactivation",
    params={
        "score_threshold": 0.3,
        "model_version": "sms_reactivation_v1",
    },
    ...
)
```

**Supporting multiple models / segments (6-week horizon):**

Rather than duplicating DAG logic, store model config in a small lookup table:

```sql
CREATE TABLE lifecycle.model_config (
  segment        STRING,    -- e.g. 'sms_reactivation', 'email_winback'
  model_table    STRING,    -- fully-qualified BQ table
  score_col      STRING,    -- column name for the probability score
  score_threshold FLOAT64,
  is_active      BOOLEAN
);
```

The `run_audience_query` task reads its row from `model_config` at runtime.
Adding a second model requires only an `INSERT` into this table — no DAG or SQL code changes.

---

## 2. DAG Modification — Model Freshness Dependency

Add a sensor before `run_audience_query` that blocks until today's scores exist:

```python
from airflow.providers.google.cloud.sensors.bigquery import BigQueryTablePartitionExistenceSensor

wait_for_scores = BigQueryTablePartitionExistenceSensor(
    task_id="wait_for_scores",
    project_id="{{ var.value.gcp_project }}",
    dataset_id="ml_predictions",
    table_id="renter_send_scores",
    partition_id="{{ ds_nodash }}",  # YYYYMMDD — matches scored_at date partition
    timeout=7200,        # wait up to 2 hours (5 AM → 7 AM max)
    poke_interval=300,   # check every 5 minutes
    retries=0,           # sensor failure is handled by timeout, not retries
)

# Updated dependency chain:
wait_for_scores >> run_audience_query() >> validate_audience() >> execute_send() >> log_and_notify()
```

---

## 3. Handling Model Pipeline Delays

**Design principle:** Sending to unscored renters wastes volume and degrades deliverability metrics — one missed day is less costly than a poorly-targeted bulk send.

| Scenario | Behaviour |
|---|---|
| Scores arrive within 2-hour window | Pipeline runs normally |
| Scores arrive after 2 hours | Sensor times out → task fails → Airflow's 2 retries fire → SLA miss alert pages on-call |
| Scores never arrive | On-call decides: skip today or manually trigger with prior-day scores |

**Optional graceful fallback** (if business requires same-day send regardless):

The sensor can be replaced with a custom operator that first checks today's partition;
if missing, it falls back to the most recent partition within the last 25 hours and logs a `used_stale_scores=true` flag in the `campaign_runs` reporting table.
This makes the fallback explicit and auditable rather than silent.

**Why not just send without scores?**  
Without score filtering the audience is roughly 3–5× larger. Sending to low-intent renters increases opt-out rates and ESP complaint rates, which degrades the sender domain reputation — a cost that compounds over weeks.
