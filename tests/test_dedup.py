import json

from pipeline.dedup import load_sent_set, make_dedup_key, save_sent_set


def test_load_returns_empty_set_when_file_missing(tmp_path):
    path = str(tmp_path / "sent.json")
    assert load_sent_set(path) == set()


def test_load_returns_existing_keys(tmp_path):
    path = str(tmp_path / "sent.json")
    with open(path, "w") as f:
        json.dump(["campaign1:renter_001", "campaign1:renter_002"], f)
    assert load_sent_set(path) == {"campaign1:renter_001", "campaign1:renter_002"}


def test_save_persists_set(tmp_path):
    path = str(tmp_path / "sent.json")
    keys = {"campaign1:renter_001", "campaign1:renter_002"}
    save_sent_set(path, keys)
    with open(path) as f:
        assert set(json.load(f)) == keys


def test_make_dedup_key_format():
    assert make_dedup_key("campaign_abc", "renter_123") == "campaign_abc:renter_123"
