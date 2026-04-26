-- SMS Reactivation Campaign — Audience Segmentation
-- Idempotent: CURRENT_DATE() and CURRENT_TIMESTAMP() are stable within a single query execution.
-- Running this query twice on the same calendar day produces the same result set.

WITH recent_searches AS (
  SELECT
    renter_id,
    COUNT(*) AS search_count
  FROM renter_activity
  WHERE
    event_type = 'search'
    AND event_timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 90 DAY)
  GROUP BY renter_id
  HAVING COUNT(*) >= 3  -- Criterion 3: at least 3 searches in past 90 days
)

SELECT
  p.renter_id,
  p.email,
  p.phone,
  p.last_login,
  rs.search_count,
  DATE_DIFF(CURRENT_DATE(), DATE(p.last_login), DAY) AS days_since_login
FROM renter_profiles p
INNER JOIN recent_searches rs
  ON p.renter_id = rs.renter_id
LEFT JOIN suppression_list sl
  ON p.renter_id = sl.renter_id
WHERE
  -- Criterion 1: last login more than 30 days ago
  p.last_login < TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)

  -- Criterion 2: churned subscribers only
  AND p.subscription_status = 'churned'

  -- Criterion 4: must have a phone number on file
  AND p.phone IS NOT NULL
  AND p.phone != ''

  -- Criterion 5: SMS consent required
  AND p.sms_consent = TRUE

  -- Criterion 6: exclude suppressed renters (LEFT JOIN + IS NULL is NULL-safe; NOT IN breaks with NULLs)
  AND sl.renter_id IS NULL

  -- Criterion 7: not in a do-not-disturb window (NULL means no restriction)
  AND (p.dnd_until IS NULL OR p.dnd_until < CURRENT_TIMESTAMP())
