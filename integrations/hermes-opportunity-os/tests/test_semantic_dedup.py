from dataclasses import replace
from pathlib import Path

import pytest

from opportunity_os.errors import ValidationError
from opportunity_os.semantic_dedup import (
    is_semantic_duplicate,
    normalize_text,
    semantic_similarity,
)
from opportunity_os.store import PrivateStore
from test_store import sample_opportunity


def test_normalize_text_strips_noise_and_case() -> None:
    assert normalize_text("移动 Agent：工具调用") == normalize_text("移动agent工具调用")


def test_semantic_similarity_high_for_near_duplicate_low_for_distinct() -> None:
    left = sample_opportunity("mobile-agent-service").to_dict()
    near = sample_opportunity("mobile-agent-service-2").to_dict()
    distinct = sample_opportunity("quant-trading-bot").to_dict()

    assert semantic_similarity(left, near) >= 0.85
    assert semantic_similarity(left, distinct) < 0.85
    assert is_semantic_duplicate(left, near)


def test_find_duplicate_returns_closest_card(tmp_path: Path) -> None:
    store = PrivateStore(tmp_path / "private")
    store.initialize()
    store.save_opportunity(sample_opportunity("mobile-agent-service"))

    duplicate = store.find_duplicate(sample_opportunity("mobile-agent-service-2"))

    assert duplicate is not None
    assert duplicate[0] == "mobile-agent-service"
    assert duplicate[1] >= 0.85


def test_save_rejects_semantic_duplicate(tmp_path: Path) -> None:
    store = PrivateStore(tmp_path / "private")
    store.initialize()
    store.save_opportunity(sample_opportunity("mobile-agent-service"))

    with pytest.raises(ValidationError, match="语义重复"):
        store.save_opportunity(sample_opportunity("mobile-agent-service-2"))


def test_merge_duplicates_keeps_winner_and_archives_loser(tmp_path: Path) -> None:
    store = PrivateStore(tmp_path / "private")
    store.initialize()
    store._write_json(
        store.home / "opportunities" / "mobile-agent-service.json",
        sample_opportunity("mobile-agent-service").to_dict(),
    )
    store._write_json(
        store.home / "opportunities" / "mobile-agent-service-2.json",
        replace(sample_opportunity("mobile-agent-service-2"), status="researched").to_dict(),
    )

    report = store.merge_duplicates(apply=True, run_id="run-merge-test")

    assert len(report["groups"]) == 1
    assert report["groups"][0]["keep"] == "mobile-agent-service"
    assert report["groups"][0]["archived"] == ["mobile-agent-service-2"]
    assert report["archived"] == ["mobile-agent-service-2"]
    assert store.get_opportunity("mobile-agent-service-2")["status"] == "archived"
    history = (store.home / "state_transitions" / "mobile-agent-service-2.jsonl").read_text()
    assert "semantic_duplicate_merge" in history
