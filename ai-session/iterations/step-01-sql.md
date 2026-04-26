# Step 1 — SQL: Audience Segmentation Query

**File:** `sql/audience_segmentation.sql`

## What was built

BigQuery query that segments the SMS reactivation audience from three tables:
`renter_activity`, `renter_profiles`, `suppression_list`.

## Criteria implemented

1. Last login > 30 days ago
2. `subscription_status = 'churned'`
3. At least 3 `search` events in the past 90 days (CTE pre-aggregation)
4. `phone IS NOT NULL AND phone != ''`
5. `sms_consent = TRUE`
6. Not in suppression list (`LEFT JOIN + IS NULL`)
7. `dnd_until IS NULL OR dnd_until < CURRENT_TIMESTAMP()`
8. Idempotent — uses `CURRENT_TIMESTAMP()` / `CURRENT_DATE()`, never `NOW()`

## Key decisions

- **CTE for search count** — pre-aggregates search events before joining, keeping the main SELECT clean and avoiding a subquery in WHERE.
- **INNER JOIN on `recent_searches`** — deliberate: renters with fewer than 3 searches are excluded early, before any profile filters run. More efficient than a LEFT JOIN + HAVING.
- **LEFT JOIN + IS NULL for suppression** — `NOT IN` is unsafe when the subquery can return NULLs; this pattern is explicit and NULL-safe.
- **`phone != ''`** — defensive check beyond IS NOT NULL; BigQuery can hold empty strings from upstream ingestion.
- **No LIMIT clause** — production query; a LIMIT would silently truncate the audience.
