import json
from pathlib import Path

import pytest

from opportunity_os.contracts import CONTRACT_TYPES, EvidenceContract, SignalContract, load_contract
from opportunity_os.errors import ValidationError


FIXTURE = Path(__file__).parent / "fixtures" / "contracts" / "v1-golden.json"


def test_v1_golden_contracts_round_trip_without_field_loss() -> None:
    payloads = json.loads(FIXTURE.read_text(encoding="utf-8"))

    assert set(payloads) == set(CONTRACT_TYPES)
    for kind, payload in payloads.items():
        record = load_contract(kind, payload)
        rendered = record.model_dump(mode="json")
        assert rendered["schema_version"] == 1
        assert rendered["id"] == payload["id"]
        assert rendered["source_url"] == payload["source_url"]
        assert rendered["content_hash"] == payload["content_hash"]
        assert rendered["run_id"] == payload["run_id"]


@pytest.mark.parametrize("required", ("id", "source_url", "collected_at", "content_hash", "run_id"))
def test_missing_cross_component_metadata_is_observable_validation_error(required: str) -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))["signal"]
    payload.pop(required)

    with pytest.raises(ValidationError, match="signal validation failed"):
        load_contract("signal", payload)


def test_unknown_schema_version_fails_closed() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))["evidence"]
    payload["schema_version"] = 99

    with pytest.raises(ValidationError, match="unsupported evidence schema_version"):
        load_contract("evidence", payload)


def test_legacy_evidence_migration_maps_real_hermes_fields_without_blank_output() -> None:
    record = load_contract(
        "evidence",
        {
            "kind": "fact",
            "stance": "support",
            "claim": "Hermes uses claim, not fact.",
            "source_name": "Official",
            "source_url": "https://example.com/official",
            "observed_at": "2026-07-29",
            "source_tier": "official",
        },
    )

    assert isinstance(record, EvidenceContract)
    assert record.claim == "Hermes uses claim, not fact."
    assert record.source_url == "https://example.com/official"
    assert record.content_hash


def test_legacy_evidence_with_missing_required_field_is_not_silently_rendered() -> None:
    with pytest.raises(ValidationError, match="missing claim, source_url or observed_at"):
        load_contract("evidence", {"kind": "fact", "source_url": "https://example.com"})


def test_legacy_signal_migration_adds_versioned_metadata() -> None:
    record = load_contract(
        "signal",
        {
            "id": "signal-legacy-fixture",
            "title": "Legacy",
            "relative_path": "raw/inbox/2026-07-29-技术动态.md",
            "collected_at": "2026-07-29",
            "category": "technology",
            "excerpt": "A legacy signal.",
            "source_urls": ["https://example.com/legacy"],
        },
    )

    assert isinstance(record, SignalContract)
    assert record.schema_version == 1
    assert record.source_url == "https://example.com/legacy"
