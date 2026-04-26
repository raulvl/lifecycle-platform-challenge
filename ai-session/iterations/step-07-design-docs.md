# Step 7 — Design Docs

**Files:** `design/model_integration.md`, `design/observability.md`

## What was written

Written responses to the five design questions in Parts 4 and 5 of the challenge.
Each answer is 1–2 paragraphs with pseudocode where the challenge asks for it.

## Scope decision

The initial drafts were over-engineered — detailed tables, multi-layer breakdowns,
and extended rationale beyond what the prompt asked for. Trimmed to match the
challenge requirement: describe in writing or pseudocode, 1–2 paragraphs per question.

## Part 4 — Model Integration

1. `INNER JOIN` on the scoring table with `@score_threshold` as a query parameter;
   model config table pattern for multi-segment support without rearchitecting.
2. `BigQueryTablePartitionExistenceSensor` before `run_audience_query`, 2-hour
   timeout, 5-minute poke interval.
3. Default: sensor timeout → Airflow retries → SLA alert → on-call decides.
   Optional: custom operator with stale-score fallback flagged in reporting table.
   Rationale: unfiltered sends degrade sender reputation more than one skipped day.

## Part 5 — Observability

1. Seven metrics covering audience size, send outcomes, duration, and ESP errors.
   Four alerts: audience anomaly, ESP failure rate, SLA miss, zero sends.
2. File-based sent log keyed on `campaign_id:renter_id`; date-stamped campaign ID
   makes retries and re-triggers automatically safe; sent log only updated on success.
3. Per-batch backoff already in code. Circuit breaker halts after 3 consecutive
   failures, persists progress, raises — Airflow retries pick up where it left off.
