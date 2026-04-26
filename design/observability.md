# Part 5 — Observability Design

## 1. Datadog Metrics & Alerts

**Metrics emitted from `log_and_notify` and `campaign_sender.py`:**

| Metric | Type | Tags | Purpose |
|---|---|---|---|
| `lifecycle.campaign.audience_size` | gauge | `campaign_type` | Track reach over time |
| `lifecycle.campaign.total_sent` | gauge | `campaign_type` | Delivery volume |
| `lifecycle.campaign.total_failed` | gauge | `campaign_type` | ESP error volume |
| `lifecycle.campaign.total_skipped` | gauge | `campaign_type` | Dedup effectiveness |
| `lifecycle.campaign.elapsed_seconds` | histogram | `campaign_type` | Pipeline duration |
| `lifecycle.esp.batch_error` | count | `status_code` | Per-status error tracking |
| `lifecycle.dag.sla_missed` | count | `dag_id` | SLA breach signal |

**Alerts:**

- **Audience size anomaly:** composite monitor — warn if today's `audience_size` < 10% of 7-day avg or > 2×. Either extreme signals a data pipeline upstream issue.
- **High ESP failure rate:** alert if `total_failed / (total_sent + total_failed) > 5%` — likely ESP degradation.
- **DAG SLA miss:** Airflow's `sla_miss_callback` fires a Datadog event; page on-call immediately since SLA window is only 3 hours.
- **Pipeline duration:** p95 of `elapsed_seconds` > 9000s (2.5 hours) triggers a warning before the SLA deadline.
- **Zero sends:** if `total_sent == 0` and `total_skipped == 0`, something went wrong in validation or the query — page on-call.

---

## 2. Double-Send Prevention

Defense is layered — each layer catches a different failure mode:

**Layer 1 — File-based dedup in pipeline code.**  
`execute_campaign_send` loads `sent_renters.json` before processing. Any `campaign_id:renter_id` already in the log is skipped. This handles Airflow task retries within the same day.

**Layer 2 — Idempotent campaign ID.**  
The campaign ID is `sms_reactivation_YYYYMMDD`. A manual re-trigger on the same day reuses the same ID, so Layer 1 catches all previously-sent renters automatically.

**Layer 3 — `CREATE OR REPLACE TABLE` in BigQuery.**  
The staging table is named with the run date. Re-running `run_audience_query` overwrites the same table rather than appending — the audience snapshot is always current-day, never stale.

**Layer 4 — Reporting table unique constraint.**  
`lifecycle.campaign_runs` has a `UNIQUE(run_date, campaign_type)` constraint. A duplicate insert raises an error, which fails the `log_and_notify` task before a second send could be logged — alerting on-call to investigate.

---

## 3. ESP Outage Recovery — Circuit Breaker Strategy

**Per-batch handling (already in code):**  
`_send_with_backoff` retries individual batches up to 5 times with exponential backoff and jitter. One failed batch is logged with full renter IDs and does not abort the run. The pipeline finishes; failed renter IDs are NOT written to `sent_renters.json`, so they're retried on the next run.

**Sustained outage — circuit breaker:**  
After `N` consecutive batch failures (default 3), the sender halts early and raises `ESPCircuitOpenError`. This prevents hammering a down service and makes the failure explicit in Airflow logs.

```python
CIRCUIT_OPEN_THRESHOLD = 3
consecutive_failures = 0

for batch in _chunks(to_send, _batch_size):
    success, error = _send_with_backoff(...)
    if success:
        consecutive_failures = 0
        # ... update sent_set
    else:
        consecutive_failures += 1
        # ... log failed batch
        if consecutive_failures >= CIRCUIT_OPEN_THRESHOLD:
            save_sent_set(sent_log_path, sent_set)  # persist progress first
            raise ESPCircuitOpenError(
                f"Circuit open after {consecutive_failures} consecutive failures. "
                f"Resume when ESP recovers — unprocessed renters are NOT in sent log."
            )
```

**Recovery path:**  
1. Airflow retries the `execute_send` task (up to 2 retries per `default_args`).  
2. On retry, `execute_campaign_send` reloads `sent_renters.json` — only the renters that were NOT sent will be in the batch, so there's no duplication risk.  
3. If all retries are exhausted, Airflow pages on-call via the SLA miss callback; the failed renter IDs are in the task logs for manual retry.

**Key invariant:** The sent log is only updated on *successful* sends, never on failures. This guarantees safe re-runs at any point without double-sends.
