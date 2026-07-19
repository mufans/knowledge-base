import json
import tarfile
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from opportunity_os.cli import main
from opportunity_os.dashboard.auth import SessionStore
from opportunity_os.models import Review
from opportunity_os.store import PrivateStore


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "knowledge"


def test_init_and_doctor_validate_private_boundary(tmp_path: Path, capsys) -> None:
    home = tmp_path / "private"

    assert main(["init", "--home", str(home), "--knowledge-root", str(FIXTURE_ROOT)]) == 0
    capsys.readouterr()
    assert main(["doctor", "--home", str(home), "--knowledge-root", str(FIXTURE_ROOT), "--format", "json"]) == 0
    report = json.loads(capsys.readouterr().out)

    assert report["ok"] is True
    assert report["knowledge_read_only_source"] is True
    assert report["private_home_outside_knowledge"] is True


def test_signals_command_returns_broad_json(tmp_path: Path, capsys) -> None:
    result = main([
        "signals", "--knowledge-root", str(FIXTURE_ROOT), "--days", "2", "--limit", "10",
        "--today", "2026-07-19", "--format", "json",
    ])
    payload = json.loads(capsys.readouterr().out)

    assert result == 0
    assert len(payload) == 3
    assert {item["category"] for item in payload} == {"technology", "cross_domain"}


def test_status_reports_invariants_without_private_content(tmp_path: Path, capsys) -> None:
    home = tmp_path / "private"
    store = PrivateStore(home)
    store.initialize()

    assert main(["status", "--home", str(home), "--format", "json"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["opportunity_count"] == 0
    assert payload["portfolio"]["capacity"] == {"observe": 5, "validate": 2, "active": 1}
    assert "records" not in payload


def test_render_review_latest_and_snapshot(tmp_path: Path, capsys) -> None:
    home = tmp_path / "private"
    store = PrivateStore(home)
    store.initialize()
    store.save_review(Review(
        id="daily-2026-07-19", period="daily", title="每日扫描", summary="摘要", opportunity_ids=[],
        surprise_signal="数据库生态出现新变化。", presentation_counts={"strength": 0, "broad": 0, "surprise": 0},
        proposed_experiment_ids=[], facts=["事实"], inferences=["推断"], hypotheses=["假设"],
        created_at="2026-07-19T10:00:00+08:00",
    ))

    assert main(["render-review", "--home", str(home), "--latest"]) == 0
    assert "每日扫描" in capsys.readouterr().out
    assert main(["snapshot", "--home", str(home), "--format", "json"]) == 0
    snapshot = Path(json.loads(capsys.readouterr().out)["snapshot"])

    assert snapshot.is_file()
    with tarfile.open(snapshot) as archive:
        names = archive.getnames()
    assert any(name.endswith("portfolio.json") for name in names)
    assert not any(".env" in name or "/snapshots/" in name for name in names)


def test_dashboard_serve_builds_app_and_binds_only_loopback(tmp_path: Path, monkeypatch) -> None:
    captured = {}

    def fake_run(app, *, host, port):
        captured.update(app=app, host=host, port=port)

    monkeypatch.setattr("uvicorn.run", fake_run)

    result = main([
        "dashboard", "serve", "--home", str(tmp_path / "private"),
        "--host", "127.0.0.1", "--port", "8765",
    ])

    assert result == 0
    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 8765
    assert captured["app"].docs_url is None


@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.20", "assigned.ngrok-free.app"])
def test_dashboard_serve_rejects_non_loopback_bind(tmp_path: Path, host: str, capsys) -> None:
    result = main([
        "dashboard", "serve", "--home", str(tmp_path / "private"), "--host", host,
    ])

    assert result == 2
    assert "loopback" in json.loads(capsys.readouterr().out)["error"]


def test_dashboard_open_persists_bootstrap_without_printing_token(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    opened = []
    monkeypatch.setattr("webbrowser.open", lambda url: opened.append(url) or True)
    home = tmp_path / "private"

    result = main([
        "dashboard", "open", "--home", str(home), "--url", "http://127.0.0.1:8765",
    ])
    output = capsys.readouterr().out

    assert result == 0
    assert len(opened) == 1
    fragment = urlsplit(opened[0]).fragment
    assert fragment.startswith("bootstrap=")
    token = fragment.removeprefix("bootstrap=")
    assert token not in output
    assert SessionStore(home / "dashboard").exchange_bootstrap(token) is not None
