# Step 2 — Pipeline: Dedup Module

**File:** `pipeline/dedup.py`, `tests/test_dedup.py`

## What was built

File-based deduplication layer. Tracks which `(campaign_id, renter_id)` pairs have
already been sent, so re-running the pipeline never double-sends.

## Three functions

- `load_sent_set(path)` — reads the JSON log; returns empty set if file doesn't exist (safe first run)
- `save_sent_set(path, sent)` — serializes the full set back to disk
- `make_dedup_key(campaign_id, renter_id)` — produces a stable `"campaign_id:renter_id"` key

## Key decisions

- **Full overwrite on save** — `save_sent_set` rewrites the entire file each time rather than appending. Simpler to reason about (no partial-write corruption, no need to deduplicate the log itself), and sufficient at this scale. The tradeoff is that for very large sent sets the write gets heavier; an append-only log would be more efficient at scale but adds complexity (compaction, duplicate entries).
- **Set not list** — in-memory representation is a `set` for O(1) membership checks during dedup filtering.
- **Key format is stable** — `f"{campaign_id}:{renter_id}"` must not change between runs or retries; changing the format would invalidate existing logs and cause double-sends.

## Tests

Four cases: missing file → empty set, existing file round-trip, save persists correctly, key format contract.
