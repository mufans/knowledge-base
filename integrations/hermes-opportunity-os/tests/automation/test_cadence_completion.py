import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from opportunity_os.automation.cadence_completion import CadenceCompletionStore
from opportunity_os.errors import BoundaryError, ValidationError


NOW = datetime(2026, 7, 19, 10, 0, tzinfo=timezone.utc)
RUN_ID = "a" * 32


def _artifact(home: Path, kind: str, identifier: str, **extra) -> None:
    directory = home / f"{kind}s"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{identifier}.json").write_text(
        json.dumps({"id": identifier, **extra}), encoding="utf-8"
    )


def test_completion_marker_binds_run_period_and_existing_required_artifact(tmp_path: Path) -> None:
    home = tmp_path / "private"
    store = CadenceCompletionStore(home, now=lambda: NOW)
    store.begin("daily", "2026-07-19", RUN_ID)
    _artifact(home, "review", "daily-review", period="daily")

    marker = store.complete("daily", "2026-07-19", RUN_ID, ["review:daily-review"])

    assert store.read("daily", "2026-07-19", RUN_ID) == marker
    marker_path = home / "cadence" / "completions" / "daily" / f"2026-07-19-{RUN_ID}.json"
    assert marker_path.stat().st_mode & 0o777 == 0o600
    assert marker["artifact_refs"] == ["review:daily-review"]


@pytest.mark.parametrize(
    ("cadence", "kind", "extra"),
    [
        ("weekly", "review", {"period": "weekly"}),
        ("six-week", "review", {"period": "six_week"}),
        ("quarterly", "review", {"period": "quarterly"}),
        ("biweekly", "experiment", {}),
    ],
)
def test_each_cadence_requires_its_domain_artifact(
    tmp_path: Path, cadence: str, kind: str, extra: dict
) -> None:
    home = tmp_path / "private"
    store = CadenceCompletionStore(home)
    store.begin(cadence, "2026-P1", RUN_ID)
    _artifact(home, kind, "artifact-1", **extra)
    marker = store.complete(
        cadence, "2026-P1", RUN_ID, [f"{kind}:artifact-1"]
    )
    assert marker["cadence"] == cadence


def test_completion_rejects_missing_wrong_or_old_period_artifacts(tmp_path: Path) -> None:
    home = tmp_path / "private"
    store = CadenceCompletionStore(home)
    store.begin("daily", "2026-07-19", RUN_ID)
    _artifact(home, "review", "weekly-review", period="weekly")

    with pytest.raises(ValidationError):
        store.complete("daily", "2026-07-19", RUN_ID, ["review:missing"])
    with pytest.raises(ValidationError):
        store.complete("daily", "2026-07-19", RUN_ID, ["review:weekly-review"])
    with pytest.raises(ValidationError):
        store.complete("biweekly", "2026-W29", RUN_ID, ["review:weekly-review"])


@pytest.mark.parametrize("component", ["home", "cadence", "completions", "cadence_name", "marker"])
def test_completion_rejects_symlink_components(tmp_path: Path, component: str) -> None:
    external = tmp_path / "external"
    external.mkdir()
    sentinel = external / "sentinel"
    sentinel.write_text("unchanged")
    home = tmp_path / "private"
    if component == "home":
        home.symlink_to(external, target_is_directory=True)
    else:
        home.mkdir()
        cadence = home / "cadence"
        cadence.mkdir(exist_ok=True)
        if component == "cadence":
            cadence.rmdir()
            cadence.symlink_to(external, target_is_directory=True)
        else:
            CadenceCompletionStore(home).begin("daily", "2026-07-19", RUN_ID)
            _artifact(home, "review", "daily-review", period="daily")
            completions = cadence / "completions"
            completions.mkdir()
            if component == "completions":
                completions.rmdir()
                completions.symlink_to(external, target_is_directory=True)
            else:
                cadence_name = completions / "daily"
                cadence_name.mkdir()
                if component == "cadence_name":
                    cadence_name.rmdir()
                    cadence_name.symlink_to(external, target_is_directory=True)
                else:
                    (cadence_name / f"2026-07-19-{RUN_ID}.json").symlink_to(sentinel)

    if component in {"home", "cadence"}:
        with pytest.raises(BoundaryError):
            CadenceCompletionStore(home).begin("daily", "2026-07-19", RUN_ID)
    elif component == "marker":
        CadenceCompletionStore(home).complete(
            "daily", "2026-07-19", RUN_ID, ["review:daily-review"]
        )
    else:
        with pytest.raises(BoundaryError):
            CadenceCompletionStore(home).complete(
                "daily", "2026-07-19", RUN_ID, ["review:daily-review"]
            )
    assert sentinel.read_text() == "unchanged"


def test_completion_rejects_artifact_that_predates_invocation(tmp_path: Path) -> None:
    home = tmp_path / "private"
    _artifact(home, "review", "old-review", period="daily")
    store = CadenceCompletionStore(home)
    store.begin("daily", "2026-07-19", RUN_ID)

    with pytest.raises(ValidationError, match="old artifact"):
        store.complete("daily", "2026-07-19", RUN_ID, ["review:old-review"])
