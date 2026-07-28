import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
CALIBRATION = ROOT / "integrations/hermes-opportunity-os/calibration"


def test_blind_review_sample_is_separated_from_automatic_key() -> None:
    sample = json.loads((CALIBRATION / "blind-review-sample.json").read_text(encoding="utf-8"))
    key = json.loads((CALIBRATION / "blind-review-key.json").read_text(encoding="utf-8"))

    assert len(sample["samples"]) == 16
    assert len({item["sample_id"] for item in sample["samples"]}) == 16
    assert all(item["reviewer_scores"] == {} and item["decision"] == "" for item in sample["samples"])
    assert all("citation_count" not in item for item in sample["samples"])
    assert all(item["legacy_self_score_ignored"] is True for item in key["samples"])
