# Take-Home Project Prompt

# Overview

This challenge evaluates the core skills required for a Senior Lifecycle Platform Engineer: **Python pipeline engineering, BigQuery/SQL audience segmentation, ESP API integration, Airflow orchestration, and observability design**.

There are 5 parts. Candidates are expected to use AI coding assistants (Cursor, Copilot, Claude, etc.) — this is explicitly allowed and encouraged. What matters is the quality of the final output and the reasoning behind design decisions, not whether the candidate typed every line by hand.

**Estimated time:** 4–6 hours of focused work. Candidates have 48 hours from the moment the challenge is sent.

---

# Submission Instructions

1. Create a **public GitHub repository** named `lifecycle-platform-challenge` (or similar)
2. Include a `README.md` that explains:
    - How to run the code locally
    - Any assumptions made
    - Design decisions and tradeoffs
    - What you would do differently with more time
3. **AI Usage Log (required)** — Include an `ai-session/` directory in your
repository with exported logs from the AI tool(s) you used:
    - **Claude Code:** run `/export ai-session/claude-log.md` before submitting
    - **Cursor / Copilot / other tools:** copy-paste your full chat session(s)
    into `ai-session/<tool-name>-log.md`
    
    We review these to evaluate **AI Fluency** — how you prompt, iterate, and guide the tool toward good solutions. This is a scored dimension, not a penalty.
    
4. Share the repository link with your **Qualitara recruiter** via the same WhatsApp or email thread the challenge was sent through
5. **Do not open a pull request or send code via email** — the GitHub link is sufficient

> The recruiter will forward the submission to the Technical Vetting team.
> 

---

# Challenge Context

You work at a large residential rental marketplace. The lifecycle marketing team currently runs SMS reactivation campaigns manually — an analyst runs a series of Ruby scripts to query the data warehouse, generates an audience list, applies suppression rules, and triggers sends through the ESP. This process takes ~9 hours per run and happens 3–4 times per week.

Your job: **build the core of an automated pipeline** that replaces this manual workflow.

---

# Part 1 — Audience Segmentation Query (SQL)

## Schema

```sql
CREATE TABLE renter_activity (
  renter_id STRING,
  event_type STRING,        -- 'page_view', 'search', 'application_start', 'application_complete', 'lease_signed'
  event_timestamp TIMESTAMP,
  property_id STRING,
  channel STRING,           -- 'web', 'ios', 'android'
  utm_source STRING
);

CREATE TABLE renter_profiles (
  renter_id STRING,
  email STRING,
  phone STRING,
  last_login TIMESTAMP,
  subscription_status STRING,  -- 'active', 'churned', 'never_subscribed'
  sms_consent BOOLEAN,
  email_consent BOOLEAN,
  dnd_until TIMESTAMP,         -- Do Not Disturb until this date (NULL = no restriction)
  created_at TIMESTAMP
);

CREATE TABLE suppression_list (
  renter_id STRING,
  suppression_reason STRING,  -- 'unsubscribed', 'bounced', 'complained', 'dnc_registry'
  suppressed_at TIMESTAMP
);
```

## Task

Write a BigQuery query that builds the audience for an **SMS reactivation campaign** with the following criteria:

1. Last login was more than 30 days ago
2. Subscription status is `'churned'`
3. Renter has performed **at least 3 searches** in the past 90 days (showing latent intent)
4. Renter has a phone number on file
5. Renter has `sms_consent = TRUE`
6. Renter is NOT in the suppression list
7. Renter's `dnd_until` is either NULL or in the past
8. The query must be **idempotent** — running it twice on the same day produces the same result

Return: `renter_id`, `email`, `phone`, `last_login`, `search_count`, `days_since_login`

## Evaluation Criteria

- Correct joins and filtering logic
- Proper NULL handling (`phone`, `dnd_until`)
- Use of `CURRENT_TIMESTAMP()` or parameterized date for idempotency
- Suppression list exclusion (`LEFT JOIN + IS NULL` or `NOT EXISTS`)
- Clean, readable SQL

---

# Part 2 — Pipeline Orchestration (Python)

Write a Python module that processes the audience query result and sends it to an ESP API.

## Requirements

1. **Batching** — The ESP API accepts a maximum of 100 recipients per request
2. **Rate Limiting** — The ESP returns HTTP 429 when rate-limited; implement exponential backoff with jitter (max 5 retries)
3. **Deduplication** — Ensure no renter receives the same campaign twice if the pipeline is re-run; use a simple file-based approach
4. **Error Handling** — Log failed batches with enough context to retry manually; do not let one failed batch stop the entire pipeline
5. **Metrics** — Track and return a summary: total sent, total failed, total skipped (deduped), total time

## Provided Interface (do not modify)

```python
class ESPClient:
    def send_batch(self, campaign_id: str, recipients: list[dict]) -> Response:
        """Sends a batch of recipients to the ESP.
        Returns a Response with .status_code and .json()"""
        pass
```

## Deliverable

```python
def execute_campaign_send(
    campaign_id: str,
    audience: list[dict],
    esp_client: ESPClient,
    sent_log_path: str = "sent_renters.json"
) -> dict:
    """Returns {'total_sent': int, 'total_failed': int, 'total_skipped': int, 'elapsed_seconds': float}"""
```

## Evaluation Criteria

- Clean batching logic
- Correct exponential backoff with jitter
- Idempotency mechanism (checks previously sent `renter_id`s)
- Graceful error handling (no single batch failure aborts the run)
- Logging quality (structured, actionable)
- Code readability and structure

---

# Part 3 — Airflow DAG Skeleton (Python)

Write an Airflow DAG definition that orchestrates the full campaign pipeline:

1. **Task 1** — Run the BigQuery audience query and export results to a staging table
2. **Task 2** — Validate the audience (count > 0, no obvious anomalies like audience > 2× historical average)
3. **Task 3** — Execute the campaign send (using the function from Part 2)
4. **Task 4** — Log results to a reporting table and send a Slack notification with the summary

## Requirements

- Schedule: Daily at 5:00 AM UTC
- Retries: 2 per task, 5-minute delay between retries
- Task dependencies: linear (1 → 2 → 3 → 4)
- SLA: Alert if the DAG hasn't completed by 8:00 AM UTC
- Use `@task` decorator or `PythonOperator` — either is fine

## Evaluation Criteria

- Correct DAG structure and task dependencies
- Proper retry and SLA configuration
- Validation step (not blindly sending)
- Clean separation of concerns between tasks
- Understanding of Airflow patterns (XComs, task flow, etc.)

---

# Part 4 — Value Model Integration (Design)

The data science team has built a predictive model that scores each renter on their likelihood to convert. The model outputs a daily BigQuery table:

```sql
CREATE TABLE ml_predictions.renter_send_scores (
  renter_id STRING,
  predicted_conversion_probability FLOAT64,  -- 0.0 to 1.0
  model_version STRING,
  scored_at TIMESTAMP
);
```

**Requirement:** Only send the reactivation SMS to renters whose predicted conversion probability exceeds a configurable threshold (e.g., 0.3).

**Additional context:** A second predictive model for a different user segment is expected in approximately 6 weeks. Your design should support multiple models with different thresholds per segment without requiring rearchitecture.

## Task

Describe (in writing or pseudocode) how you would modify:

1. The **BigQuery query** from Part 1 to incorporate model scores
2. The **Airflow DAG** from Part 3 to add a dependency on the model scoring table being fresh (scored today)
3. How you would handle the case where the **model scoring job hasn't completed** by the time the campaign DAG runs

## Evaluation Criteria

- Clean integration of model scores into the audience query (JOIN pattern, threshold parameterization)
- DAG dependency management (sensor or external task dependency for model freshness)
- Graceful handling of model pipeline delays (wait vs. skip vs. fallback)
- Shows understanding of the business tradeoff: sending without model scores wastes volume, not sending at all loses revenue

---

# Part 5 — Observability Design (Written)

In 1–2 paragraphs per question, describe:

1. **What Datadog metrics and alerts would you set up** for this pipeline? Think about: DAG latency, audience size anomalies, ESP error rates, send completion rates.
2. **How would you detect and prevent double-sends** if the pipeline runs twice due to an Airflow retry or manual re-trigger?
3. **What happens if the ESP goes down mid-send?** Describe your circuit-breaker or recovery strategy.
