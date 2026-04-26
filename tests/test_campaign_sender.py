import json
from unittest.mock import MagicMock

import pytest

from pipeline.campaign_sender import execute_campaign_send
from pipeline.esp_client import ESPClient, Response


def make_esp(status_code=200, body=None):
    client = MagicMock(spec=ESPClient)
    client.send_batch.return_value = Response(status_code=status_code, _body=body or {})
    return client


def test_returns_all_metric_keys(tmp_path):
    esp = make_esp(200)
    result = execute_campaign_send(
        campaign_id="c1",
        audience=[{"renter_id": "r1", "phone": "555"}],
        esp_client=esp,
        sent_log_path=str(tmp_path / "sent.json"),
    )
    assert set(result.keys()) == {"total_sent", "total_failed", "total_skipped", "elapsed_seconds"}


def test_batches_into_chunks_of_100(tmp_path):
    esp = make_esp(200)
    audience = [{"renter_id": f"r{i}"} for i in range(250)]
    execute_campaign_send(
        campaign_id="c1",
        audience=audience,
        esp_client=esp,
        sent_log_path=str(tmp_path / "sent.json"),
    )
    # 250 renters → 3 batches: 100 + 100 + 50
    assert esp.send_batch.call_count == 3


def test_dedup_skips_already_sent(tmp_path):
    sent_path = str(tmp_path / "sent.json")
    with open(sent_path, "w") as f:
        json.dump(["c1:r1"], f)

    esp = make_esp(200)
    result = execute_campaign_send(
        campaign_id="c1",
        audience=[{"renter_id": "r1"}, {"renter_id": "r2"}],
        esp_client=esp,
        sent_log_path=sent_path,
    )
    assert result["total_skipped"] == 1
    assert result["total_sent"] == 1


def test_failed_batch_does_not_abort_pipeline(tmp_path):
    esp = MagicMock(spec=ESPClient)
    # With _batch_size=1, r1 is batch 1 (fails all retries), r2 is batch 2 (succeeds)
    esp.send_batch.side_effect = [
        Response(500, {}),  # r1 attempt 0
        Response(500, {}),  # r1 attempt 1 (max_retries=1 for speed)
        Response(200, {}),  # r2 succeeds
    ]
    audience = [{"renter_id": "r1"}, {"renter_id": "r2"}]
    result = execute_campaign_send(
        campaign_id="c1",
        audience=audience,
        esp_client=esp,
        sent_log_path=str(tmp_path / "sent.json"),
        max_retries=1,
        _batch_size=1,
    )
    # Pipeline must complete — not raise
    assert result["total_failed"] == 1
    assert result["total_sent"] == 1


def test_dedup_log_updated_after_send(tmp_path):
    sent_path = str(tmp_path / "sent.json")
    esp = make_esp(200)
    execute_campaign_send(
        campaign_id="c1",
        audience=[{"renter_id": "r1"}, {"renter_id": "r2"}],
        esp_client=esp,
        sent_log_path=sent_path,
    )
    with open(sent_path) as f:
        keys = set(json.load(f))
    assert keys == {"c1:r1", "c1:r2"}


def test_elapsed_seconds_is_non_negative(tmp_path):
    esp = make_esp(200)
    result = execute_campaign_send(
        campaign_id="c1",
        audience=[{"renter_id": "r1"}],
        esp_client=esp,
        sent_log_path=str(tmp_path / "sent.json"),
    )
    assert result["elapsed_seconds"] >= 0
