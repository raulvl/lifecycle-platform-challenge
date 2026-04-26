# Step 3 — Pipeline: Campaign Sender

**File:** `pipeline/campaign_sender.py`

## What was built

`execute_campaign_send()` — the main pipeline function. Filters the audience through
dedup, chunks into batches of 100, sends each batch with retry logic, and returns
a summary dict.

## Key decisions

- **Dedup filter before batching** — already-sent renters are excluded upfront, so no ESP calls are wasted on them.
- **Incremental sent log save (per successful batch)** — `save_sent_set` is called immediately after each successful batch, not once at the end. If the process is killed mid-run, the log reflects exactly which batches completed. Previously-sent renters won't be double-sent on resume; only the in-flight batch at crash time may need retry.
- **Sent set updated only on success** — a failed batch is never added to the sent log, keeping it eligible for manual retry without any extra tooling.
- **`time.monotonic()` for elapsed** — wall clock (`time.time()`) can drift if the system clock is adjusted mid-run; monotonic is safe for measuring durations.
- **`_batch_size` param** — not part of the public interface; exists only to keep tests fast without hitting the 100-item limit.

## Retry logic (`_send_with_backoff`)

- Retries on 429 and 5xx (`{429, 500, 502, 503, 504}`)
- Fail fast on 4xx (client errors are not transient)
- Exponential backoff: `2^attempt + random.uniform(0, 1)` (jitter avoids thundering herd)
- Max 5 retries; returns `(False, error_message)` on exhaustion — never raises
- Network exceptions are also retried with the same backoff

## Logging

Structured `key=value` lines at each stage: retryable warning per attempt,
error with full renter ID list on batch failure, info on batch success,
info summary on campaign complete.
