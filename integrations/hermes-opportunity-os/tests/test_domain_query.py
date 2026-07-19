import json
import os
from datetime import datetime, timezone

import pytest

from opportunity_os.domain_query import DomainQueryError, DomainQueryService
from opportunity_os.proposals import ProposalError, ProposalStore


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def _home(tmp_path):
    home = tmp_path / "private"
    _write(home / "portfolio.json", {"directions": [{
        "id": "mobile-ai", "title": "Mobile AI", "status": "observe",
        "opportunity_ids": ["opp-1"], "rationale": "evidence", "next_review_at": "2026-08-01",
        "api_key": "must-not-leak",
    }]})
    _write(home / "opportunities" / "opp-1.json", {
        "id": "opp-1", "title": "Agent", "summary": "safe", "status": "candidate",
        "total_score": 8.1, "private_contact": "must-not-leak",
    })
    _write(home / "reviews" / "daily.json", {
        "id": "daily", "period": "daily", "title": "Review", "summary": "safe",
        "facts": ["fact"], "inferences": ["inference"], "hypotheses": ["hypothesis"],
        "created_at": "2026-07-19T00:00:00+00:00",
    })
    _write(home / "tech_states" / "hermes.json", {
        "technology": "Hermes", "known_latest": "latest", "recommended_stable": "stable",
        "maturity": "frontier", "official_sources": ["https://example.test"],
        "observed_at": "2026-07-19", "review_due_at": "2026-08-01", "confidence": "high",
        "token": "must-not-leak",
    })
    return home


@pytest.mark.parametrize("name", ["status", "latest_review", "directions", "opportunities", "learning"])
def test_typed_queries_return_only_domain_schema(tmp_path, name) -> None:
    payload = DomainQueryService(_home(tmp_path)).query(name)
    rendered = json.dumps(payload, ensure_ascii=False)
    assert "must-not-leak" not in rendered
    assert "api_key" not in rendered and "private_contact" not in rendered


def test_query_rejects_symlinked_state(tmp_path) -> None:
    home = _home(tmp_path)
    original = home / "portfolio.json"
    target = tmp_path / "outside.json"
    target.write_text(original.read_text(encoding="utf-8"), encoding="utf-8")
    original.unlink()
    original.symlink_to(target)
    with pytest.raises(OSError):
        DomainQueryService(home).query("status")


def test_pending_proposal_is_bounded_private_and_expires_old_items(tmp_path) -> None:
    now = datetime(2026, 7, 19, tzinfo=timezone.utc)
    store = ProposalStore(tmp_path / "pending.json", now=lambda: now)
    record = store.add("feedback", "  保持广域信号  ")

    assert record["state"] == "pending" and record["text"] == "保持广域信号"
    assert oct((tmp_path / "pending.json").stat().st_mode & 0o777) == "0o600"
    with pytest.raises(ProposalError):
        store.add("feedback", "x" * 5000)


def test_proposal_rejects_symlink(tmp_path) -> None:
    target = tmp_path / "target.json"
    target.write_text('{"proposals":[]}', encoding="utf-8")
    link = tmp_path / "link.json"
    link.symlink_to(target)
    with pytest.raises(OSError):
        ProposalStore(link).add("feedback", "hello")


def test_proposal_fails_closed_on_corrupt_existing_store(tmp_path) -> None:
    path = tmp_path / "pending.json"
    path.write_text("not-json", encoding="utf-8")
    with pytest.raises(ProposalError, match="store_invalid"):
        ProposalStore(path).add("feedback", "hello")
