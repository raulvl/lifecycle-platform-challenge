# Part 4 — Value Model Integration

## 1. Modifying the BigQuery query

Add an `INNER JOIN` against the scoring table, filtering by today's date and a
configurable threshold. Using `INNER JOIN` (rather than `LEFT JOIN + WHERE`) means
renters with no score are excluded from the audience automatically.

```sql
INNER JOIN ml_predictions.renter_send_scores scores
  ON  p.renter_id = scores.renter_id
  AND DATE(scores.scored_at) = CURRENT_DATE()
  AND scores.predicted_conversion_probability >= @score_threshold
```

`@score_threshold` is a BigQuery query parameter passed from the DAG, so the
threshold can be changed per campaign without touching SQL. To support multiple
models and segments without rearchitecting, store model config in a small lookup
table (`segment`, `model_table`, `score_col`, `score_threshold`) and have the
query task read its row at runtime — adding a second model is just an INSERT.

## 2. Adding a model freshness dependency to the DAG

Add a `BigQueryTablePartitionExistenceSensor` before `run_audience_query` that
blocks until today's partition exists in the scoring table. This makes the data
dependency explicit and prevents the pipeline from running on stale scores.

```python
wait_for_scores = BigQueryTablePartitionExistenceSensor(
    task_id="wait_for_scores",
    dataset_id="ml_predictions",
    table_id="renter_send_scores",
    partition_id="{{ ds_nodash }}",  # YYYYMMDD
    timeout=7200,       # wait up to 2 hours
    poke_interval=300,  # check every 5 minutes
)

wait_for_scores >> run_audience_query >> validate_audience >> execute_send >> log_and_notify
```

## 3. Handling model pipeline delays

If scores are not ready within the 2-hour window, the sensor times out, the task
fails, and Airflow's standard retries fire. If all retries are exhausted, the SLA
miss alert pages on-call, who decides whether to skip the day or manually trigger
with prior-day scores.

Sending without scores is not the right default: an unfiltered audience is
roughly 3–5× larger, increasing opt-out and complaint rates, which degrades
sender domain reputation over time. One missed day costs less than a poorly
targeted bulk send. If the business requires a same-day send regardless, the
sensor can be replaced with a custom operator that falls back to the most recent
available scores and records a `used_stale_scores=true` flag in the reporting
table so the fallback is auditable.
