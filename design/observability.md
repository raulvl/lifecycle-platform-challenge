# Part 5 — Observability Design

## 1. Datadog metrics and alerts

Emit the following metrics from `campaign_sender.py` and `log_and_notify`:
`lifecycle.campaign.audience_size`, `total_sent`, `total_failed`, `total_skipped`,
and `elapsed_seconds` — all tagged with `campaign_type`. From the batch loop, emit
`lifecycle.esp.batch_error` counted by status code.

Key alerts to set up:

- **Audience anomaly:** warn if today's audience is below 10% or above 200% of the
  7-day rolling average — either extreme signals an upstream data issue.
- **High ESP failure rate:** alert if `total_failed / (total_sent + total_failed) > 5%`.
- **DAG SLA miss:** wire Airflow's `sla_miss_callback` to post a Datadog event and
  page on-call immediately — the window is only 3 hours.
- **Zero sends:** if `total_sent == 0` and `total_skipped == 0`, something failed
  silently in validation or the query.

## 2. Detecting and preventing double-sends

The primary mechanism is the file-based sent log in `execute_campaign_send`. Before
batching, every renter is checked against `sent_renters.json`; those already present
are skipped. The campaign ID is `sms_reactivation_YYYYMMDD`, so a manual re-trigger
or Airflow retry on the same day reuses the same ID and the same dedup keys —
no renter can slip through. The sent log is only updated on successful sends, so
failed batches are retried cleanly without risk of double-send.

At the DAG level, the staging table uses `CREATE OR REPLACE TABLE` with a date-stamped
name, so re-running the query task overwrites the snapshot rather than appending to it.

## 3. ESP outage and circuit-breaker recovery

Individual batch failures are already handled: `_send_with_backoff` retries up to
5 times with exponential backoff and jitter. A failed batch is logged with its renter
IDs and does not abort the run; those renters are absent from the sent log and will be
retried on the next pipeline run.

For a sustained outage, a circuit breaker halts the pipeline early after N consecutive
batch failures rather than hammering a down service:

```python
CIRCUIT_OPEN_THRESHOLD = 3
consecutive_failures = 0

for batch in _chunks(to_send, _batch_size):
    success, error = _send_with_backoff(...)
    if success:
        consecutive_failures = 0
    else:
        consecutive_failures += 1
        if consecutive_failures >= CIRCUIT_OPEN_THRESHOLD:
            save_sent_set(sent_log_path, sent_set)  # persist progress before raising
            raise ESPCircuitOpenError("Circuit open — resume when ESP recovers.")
```

When Airflow retries the task, `execute_campaign_send` reloads the sent log and
only processes renters that were not previously sent — no duplication risk.
If all retries are exhausted, the SLA miss alert pages on-call with the failed
renter IDs available in the task logs for manual retry.
