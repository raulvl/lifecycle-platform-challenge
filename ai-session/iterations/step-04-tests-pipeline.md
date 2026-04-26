# Step 4 — Tests: Pipeline

**Files:** `tests/test_dedup.py`, `tests/test_campaign_sender.py`, `tests/conftest.py`

## What was tested

### Dedup (4 tests)
- Missing file → returns empty set (safe first run)
- Existing file → loads keys correctly
- Save round-trips the full set to disk
- Key format contract: `"campaign_id:renter_id"`

### Campaign sender (6 tests)
- Summary dict has all four expected keys
- 250 renters → 3 `send_batch` calls (100 + 100 + 50)
- Already-sent renter is skipped; new renter is sent
- Failed batch does not abort — pipeline continues and reports both outcomes
- Sent log is persisted on disk after a successful send
- `elapsed_seconds` is non-negative

## Notable points

- `make_esp()` helper wraps `MagicMock(spec=ESPClient)` — keeps test setup concise
- `_batch_size=1` used in the abort test so each renter is its own batch; avoids needing 200+ audience entries to exercise partial failure
- `max_retries=1` in the abort test keeps the test fast (no real sleeps — backoff calls `time.sleep` which is not mocked here, but retries=1 means only one retry)
- `conftest.py` stubs out Airflow and Google Cloud imports at session scope — DAG tests run without a full Airflow install

## Change made this step

`save_sent_set` was moved from after the batch loop to inside the success branch of the loop (incremental save per successful batch). Tests confirmed the behavior is unchanged — `test_dedup_log_updated_after_send` still passes.

All 10 tests pass.
