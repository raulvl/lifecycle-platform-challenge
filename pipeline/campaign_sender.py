import logging
import random
import time
from typing import Iterator

from pipeline.dedup import load_sent_set, make_dedup_key, save_sent_set
from pipeline.esp_client import ESPClient

logger = logging.getLogger(__name__)

BATCH_SIZE = 100
# HTTP status codes that warrant a retry
_RETRYABLE = {429, 500, 502, 503, 504}


def _chunks(lst: list, size: int) -> Iterator[list]:
    for i in range(0, len(lst), size):
        yield lst[i : i + size]


def _send_with_backoff(
    esp_client: ESPClient,
    campaign_id: str,
    batch: list[dict],
    max_retries: int,
) -> tuple[bool, str | None]:
    """Attempt to send one batch with exponential backoff + jitter on retryable errors.

    Returns (success, error_message).
    A failed batch is reported but does NOT raise — callers decide whether to abort.
    """
    for attempt in range(max_retries + 1):
        try:
            response = esp_client.send_batch(campaign_id, batch)
            if response.status_code < 400:
                return True, None
            if response.status_code in _RETRYABLE:
                if attempt == max_retries:
                    return False, f"status_{response.status_code}_exhausted_after_{max_retries}_retries"
                delay = (2**attempt) + random.uniform(0, 1)
                logger.warning(
                    "esp_retryable_error status=%d attempt=%d/%d delay=%.2fs",
                    response.status_code,
                    attempt + 1,
                    max_retries,
                    delay,
                )
                time.sleep(delay)
                continue
            # 4xx client errors are not retryable
            return False, f"client_error_status_{response.status_code}"
        except Exception as exc:
            if attempt == max_retries:
                return False, f"exception:{exc}"
            delay = (2**attempt) + random.uniform(0, 1)
            logger.warning("esp_exception attempt=%d/%d error=%s", attempt + 1, max_retries, exc)
            time.sleep(delay)

    return False, "max_retries_exceeded"


def execute_campaign_send(
    campaign_id: str,
    audience: list[dict],
    esp_client: ESPClient,
    sent_log_path: str = "sent_renters.json",
    max_retries: int = 5,
    _batch_size: int = BATCH_SIZE,
) -> dict:
    """Process audience and send in batches to the ESP.

    Returns {'total_sent': int, 'total_failed': int, 'total_skipped': int, 'elapsed_seconds': float}
    """
    start = time.monotonic()
    sent_set = load_sent_set(sent_log_path)

    total_sent = 0
    total_failed = 0
    total_skipped = 0

    # Filter out already-sent renters before batching
    to_send = []
    for renter in audience:
        key = make_dedup_key(campaign_id, renter["renter_id"])
        if key in sent_set:
            total_skipped += 1
        else:
            to_send.append(renter)

    for batch in _chunks(to_send, _batch_size):
        success, error = _send_with_backoff(esp_client, campaign_id, batch, max_retries)
        if success:
            for renter in batch:
                sent_set.add(make_dedup_key(campaign_id, renter["renter_id"]))
            total_sent += len(batch)
            logger.info("batch_sent campaign=%s count=%d", campaign_id, len(batch))
        else:
            total_failed += len(batch)
            logger.error(
                "batch_failed campaign=%s count=%d error=%s renter_ids=%s",
                campaign_id,
                len(batch),
                error,
                [r["renter_id"] for r in batch],
            )

    save_sent_set(sent_log_path, sent_set)

    summary = {
        "total_sent": total_sent,
        "total_failed": total_failed,
        "total_skipped": total_skipped,
        "elapsed_seconds": round(time.monotonic() - start, 3),
    }
    logger.info("campaign_complete campaign=%s %s", campaign_id, summary)
    return summary
