import json
import os


def load_sent_set(path: str) -> set[str]:
    if not os.path.exists(path):
        return set()
    with open(path) as f:
        return set(json.load(f))


def save_sent_set(path: str, sent: set[str]) -> None:
    with open(path, "w") as f:
        json.dump(list(sent), f)


def make_dedup_key(campaign_id: str, renter_id: str) -> str:
    return f"{campaign_id}:{renter_id}"
