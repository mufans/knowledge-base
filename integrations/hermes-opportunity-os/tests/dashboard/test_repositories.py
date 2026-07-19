import json
from pathlib import Path

from opportunity_os.dashboard.repositories import PrivateStateReadRepository
from opportunity_os.store import PrivateStore


def test_repository_read_has_no_write_side_effect(tmp_path: Path) -> None:
    store = PrivateStore(tmp_path / "private")
    store.initialize()
    before = {path: path.stat().st_mtime_ns for path in store.home.rglob("*") if path.is_file()}

    PrivateStateReadRepository(store.home).snapshot()

    after = {path: path.stat().st_mtime_ns for path in store.home.rglob("*") if path.is_file()}
    assert after == before


def test_repository_snapshot_exposes_only_aggregate_private_state(tmp_path: Path) -> None:
    store = PrivateStore(tmp_path / "private")
    store.initialize()
    store.portfolio_path.write_text(json.dumps({
        "directions": [{
            "id": "active-dashboard",
            "title": "私有方向标题",
            "status": "active",
            "opportunity_ids": [],
            "rationale": "私有方向依据",
            "next_review_at": "2026-08-30",
        }]
    }), encoding="utf-8")
    (store.home / "reviews" / "weekly-1.json").write_text(json.dumps({
        "id": "weekly-1",
        "period": "weekly",
        "title": "私有复盘标题",
        "summary": "私有复盘摘要",
        "created_at": "2026-07-19T10:00:00+08:00",
    }), encoding="utf-8")
    (store.home / "tech_states" / "overdue.json").write_text(json.dumps({
        "review_due_at": "2000-01-01",
    }), encoding="utf-8")
    (store.home / "events.jsonl").write_text('{"action": "one"}\n{"action": "two"}\n', encoding="utf-8")

    snapshot = PrivateStateReadRepository(store.home).snapshot()

    assert snapshot.opportunity_count == 0
    assert snapshot.experiment_count == 0
    assert snapshot.review_count == 1
    assert snapshot.tech_state_count == 1
    assert snapshot.portfolio_counts == {"observe": 0, "validate": 0, "active": 1}
    assert snapshot.portfolio_capacity == {"observe": 5, "validate": 2, "active": 1}
    assert snapshot.latest_review_id == "weekly-1"
    assert snapshot.latest_review_period == "weekly"
    assert snapshot.latest_review_at.isoformat() == "2026-07-19T10:00:00+08:00"
    assert snapshot.overdue_tech_states == 1
    assert snapshot.event_cursor == 2
    rendered = repr(snapshot)
    assert "私有方向标题" not in rendered
    assert "私有方向依据" not in rendered
    assert "私有复盘标题" not in rendered
    assert "私有复盘摘要" not in rendered
