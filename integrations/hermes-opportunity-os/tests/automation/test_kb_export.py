import json
import math
import os
import re
import socket
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from opportunity_os.automation.kb_export import KnowledgeExporter
from opportunity_os.errors import BoundaryError, ValidationError


NOW = datetime(2026, 7, 19, 10, 0, tzinfo=timezone.utc)
ENTITY_ID = "entity:550e8400-e29b-41d4-a716-446655440000"
EXPERIMENT_ID = "experiment:123e4567-e89b-42d3-a456-426614174000"


def valid_bridge_payload(name: str) -> dict[str, object]:
    if name == "openclaw-handoff.json":
        return {"operation": "add_handoff_refs", "entity_ids": [ENTITY_ID]}
    if name == "source-feedback.json":
        return {"operation": "add_targeted_searches"}
    return {"operation": "add_evidence_queries", "experiment_ids": [EXPERIMENT_ID]}


def knowledge_fixture(tmp_path: Path) -> Path:
    root = tmp_path / "knowledge"
    (root / "raw" / "inbox").mkdir(parents=True)
    (root / "raw" / "inbox" / "source.md").write_text("只读原文\n", encoding="utf-8")
    (root / "wiki" / "syntheses").mkdir(parents=True)
    (root / "wiki" / "syntheses" / "index.md").write_text("# 综合分析\n\n", encoding="utf-8")
    (root / "AGENTS.md").write_text(
        "# rules\nraw/ 只读；wiki/syntheses 可写；更新 log.md。\n"
        "## 核心概念\n## 设计原理\n## 关键实现\n## 关联分析\n## 可执行建议\n## 自评\n",
        encoding="utf-8",
    )
    (root / "purpose.md").write_text("# purpose\n## 目标\n技术知识图谱\n## 研究范围\nAI Agent\n", encoding="utf-8")
    (root / "log.md").write_text("2026-07-18 | baseline | fixture | 初始\n", encoding="utf-8")
    return root


def valid_report(**overrides) -> dict:
    report = {
        "title": "个人机会发现周报",
        "tags": ["#AIAgent", "#RAG", "#CareerTech"],
        "source_links": [{"name": "官方文档", "url": "https://example.com/docs"}],
        "score": {"技术深度": 8, "实用价值": 8, "时效性": 9, "领域匹配": 8, "综合": 8.3},
        "sections": {
            "核心概念": "本周对 5 个广域信号进行聚类，保留 1 个跨领域意外发现。",
            "设计原理": "采用 broad-first，定向检索只补充反对证据，不减少广域来源。",
            "关键实现": "广域输入占比至少 80%，定向补充不超过 20%，并记录 observed_at。",
            "关联分析": "证据同时包含支持与反对两种 stance，结论标记 Fact 或 Inference。",
            "可执行建议": "建议用户先审核一个 7 天可停止实验，不执行发布、联系或付费。",
        },
        "self_evaluation": {"摘要质量": 8, "技术深度": 8, "相关性": 8, "原创性": 7, "格式规范": 9},
    }
    report.update(overrides)
    return report


def make_exporter(tmp_path: Path) -> tuple[KnowledgeExporter, Path, Path]:
    root = knowledge_fixture(tmp_path)
    private = tmp_path / "hermes-private"
    return KnowledgeExporter(root, private_home=private, now=lambda: NOW), root, private


def test_render_is_agents_compliant_chinese_linked_and_self_scored(tmp_path: Path) -> None:
    exporter, _, _ = make_exporter(tmp_path)
    rendered = exporter.render(valid_report())

    assert rendered.startswith("# 个人机会发现周报\n")
    assert "> tags: #AIAgent #RAG #CareerTech" in rendered
    assert "> source: [官方文档](https://example.com/docs)" in rendered
    assert "> score: 技术深度8/10 | 实用价值8/10 | 时效性9/10 | 领域匹配8/10 | 综合 8.3/10" in rendered
    for heading in ("核心概念", "设计原理", "关键实现", "关联分析", "可执行建议", "自评"):
        assert f"## {heading}" in rendered
    assert "**加权总分**" in rendered
    assert re.search(r"[\u4e00-\u9fff]", rendered)
    assert not re.search(r"(?<!\()https?://", rendered)


@pytest.mark.parametrize(
    ("kind", "period_key", "filename"),
    [
        ("dashboard", None, "个人机会发现仪表盘.md"),
        ("weekly", "2026-07-19", "个人机会发现周报-2026-07-19.md"),
        ("freshness", None, "技术新鲜度观察.md"),
        ("experiment", "2026-W29", "方向实验复盘-2026-W29.md"),
    ],
)
def test_export_owns_only_four_exact_public_page_names(
    tmp_path: Path, kind: str, period_key: str | None, filename: str
) -> None:
    exporter, root, _ = make_exporter(tmp_path)
    path = exporter.export(kind, valid_report(), period_key=period_key)

    assert path == root / "wiki" / "syntheses" / filename
    assert path.is_file()


@pytest.mark.parametrize(
    ("kind", "period_key"),
    [("daily", "2026-07-19"), ("weekly", "../escape"), ("weekly", "2026-W29"), ("experiment", "2026-07-19")],
)
def test_export_rejects_unknown_kind_or_invalid_period_key(
    tmp_path: Path, kind: str, period_key: str | None
) -> None:
    exporter, _, _ = make_exporter(tmp_path)
    with pytest.raises(ValidationError):
        exporter.export(kind, valid_report(), period_key=period_key)


def test_export_updates_only_syntheses_index_and_append_only_root_log(tmp_path: Path) -> None:
    exporter, root, _ = make_exporter(tmp_path)
    raw = root / "raw" / "inbox" / "source.md"
    raw_before = (raw.read_bytes(), raw.stat().st_mtime_ns)
    log_before = (root / "log.md").read_text(encoding="utf-8")

    page = exporter.export("weekly", valid_report(), period_key="2026-07-19")

    assert raw_before == (raw.read_bytes(), raw.stat().st_mtime_ns)
    assert not (root / "docs").exists()
    assert "[个人机会发现周报](个人机会发现周报-2026-07-19.md)" in (
        root / "wiki" / "syntheses" / "index.md"
    ).read_text(encoding="utf-8")
    log_after = (root / "log.md").read_text(encoding="utf-8")
    assert log_after.startswith(log_before)
    assert f"{page.relative_to(root)}" in log_after


def test_export_fails_closed_when_repository_agents_contract_is_missing(tmp_path: Path) -> None:
    exporter, root, _ = make_exporter(tmp_path)
    (root / "AGENTS.md").write_text("# unrelated rules\n", encoding="utf-8")

    with pytest.raises(ValidationError):
        exporter.export("dashboard", valid_report())
    assert not (root / "wiki" / "syntheses" / "个人机会发现仪表盘.md").exists()


@pytest.mark.parametrize(
    "report",
    [
        valid_report(self_evaluation={"摘要质量": 6, "技术深度": 6, "相关性": 6, "原创性": 6, "格式规范": 6}),
        valid_report(tags=["#only"]),
        valid_report(title="ASCII only"),
        valid_report(source_links=[{"name": "bad", "url": "file:///private/data"}]),
        valid_report(sections={"核心概念": "Authorization: Bearer abcdefghijklmnop"}),
        valid_report(sections={"核心概念": "private file /Users/person/.hermes/state.db"}),
    ],
)
def test_render_rejects_low_quality_invalid_format_secret_and_private_paths(
    tmp_path: Path, report: dict
) -> None:
    exporter, _, _ = make_exporter(tmp_path)
    with pytest.raises(ValidationError):
        exporter.render(report)


@pytest.mark.parametrize(
    "report",
    [
        valid_report(unused_private_note="/Users/person/.hermes/private.json"),
        valid_report(score={"技术深度": math.nan, "实用价值": 8, "时效性": 8, "领域匹配": 8, "综合": 8}),
    ],
)
def test_render_rejects_private_data_in_unused_fields_and_nonfinite_scores(tmp_path: Path, report: dict) -> None:
    exporter, _, _ = make_exporter(tmp_path)
    with pytest.raises(ValidationError):
        exporter.render(report)


def test_render_requires_top_level_composite_score_at_least_seven(tmp_path: Path) -> None:
    exporter, _, _ = make_exporter(tmp_path)
    report = valid_report(
        score={"技术深度": 8, "实用价值": 8, "时效性": 8, "领域匹配": 8, "综合": 6.9}
    )
    with pytest.raises(ValidationError):
        exporter.render(report)


def test_symlinked_syntheses_or_owned_page_is_rejected(tmp_path: Path) -> None:
    exporter, root, _ = make_exporter(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    syntheses = root / "wiki" / "syntheses"
    for child in syntheses.iterdir():
        child.unlink()
    syntheses.rmdir()
    syntheses.symlink_to(outside, target_is_directory=True)

    with pytest.raises(BoundaryError):
        exporter.export("dashboard", valid_report())
    assert list(outside.iterdir()) == []


def test_private_home_symlink_is_rejected_before_lock_or_bridge_write(tmp_path: Path) -> None:
    root = knowledge_fixture(tmp_path)
    outside = tmp_path / "outside-private"
    outside.mkdir()
    private_link = tmp_path / "private-link"
    private_link.symlink_to(outside, target_is_directory=True)

    with pytest.raises(BoundaryError):
        KnowledgeExporter(root, private_home=private_link, now=lambda: NOW)
    assert list(outside.iterdir()) == []


def test_symlinked_private_locks_directory_is_rejected_without_touching_target(tmp_path: Path) -> None:
    exporter, _, private = make_exporter(tmp_path)
    private.mkdir()
    outside = tmp_path / "outside-locks"
    outside.mkdir()
    sentinel = outside / "sentinel"
    sentinel.write_text("unchanged", encoding="utf-8")
    (private / "locks").symlink_to(outside, target_is_directory=True)

    with pytest.raises(BoundaryError):
        exporter.export("dashboard", valid_report())
    assert sentinel.read_text(encoding="utf-8") == "unchanged"
    assert {path.name for path in outside.iterdir()} == {"sentinel"}


def write_export_lock(private: Path, *, pid: int, started_at: str, token: str = "owner") -> Path:
    lock = private / "locks" / "kb-export.lock"
    lock.mkdir(parents=True)
    owner = {"token": token, "pid": pid, "host": socket.gethostname(), "started_at": started_at}
    owner_path = lock / "owner.json"
    owner_path.write_text(json.dumps(owner), encoding="utf-8")
    owner_path.chmod(0o600)
    return lock


def test_export_live_owner_lock_is_never_reclaimed(tmp_path: Path) -> None:
    exporter, _, private = make_exporter(tmp_path)
    lock = write_export_lock(private, pid=os.getpid(), started_at="2020-01-01T00:00:00+00:00")
    exporter = KnowledgeExporter(
        exporter.knowledge_root,
        private_home=private,
        now=lambda: NOW,
        lock_stale_after_seconds=0.01,
        lock_wait_seconds=0.05,
    )

    with pytest.raises(ValidationError):
        exporter.export("dashboard", valid_report())
    assert lock.is_dir()
    assert json.loads((lock / "owner.json").read_text())["pid"] == os.getpid()


def test_export_stale_dead_owner_lock_is_atomically_reclaimed(tmp_path: Path) -> None:
    exporter, root, private = make_exporter(tmp_path)
    write_export_lock(private, pid=999_999_999, started_at="2020-01-01T00:00:00+00:00")
    exporter = KnowledgeExporter(
        root,
        private_home=private,
        now=lambda: NOW,
        lock_stale_after_seconds=0.01,
        lock_wait_seconds=0.2,
    )

    page = exporter.export("dashboard", valid_report())

    assert page.is_file()
    assert not (private / "locks" / "kb-export.lock").exists()
    assert not list((private / "locks").glob(".kb-export.stale.*"))


def test_export_arbitration_file_is_permanent_nofollow_and_0600(tmp_path: Path) -> None:
    exporter, _, private = make_exporter(tmp_path)
    exporter.export("dashboard", valid_report())
    arbitration = private / "locks" / ".kb-export-arbitration.lock"

    assert arbitration.is_file() and not arbitration.is_symlink()
    assert arbitration.stat().st_mode & 0o777 == 0o600


def test_two_export_contenders_serialize_stale_takeover_without_stealing_new_lock(tmp_path: Path) -> None:
    exporter, root, private = make_exporter(tmp_path)
    write_export_lock(private, pid=999_999_999, started_at="2020-01-01T00:00:00+00:00")
    exporter = KnowledgeExporter(
        root,
        private_home=private,
        now=lambda: NOW,
        lock_stale_after_seconds=1,
        lock_wait_seconds=2,
    )

    with ThreadPoolExecutor(max_workers=2) as pool:
        pages = list(
            pool.map(
                lambda _: exporter.export("weekly", valid_report(), period_key="2026-07-19"),
                range(2),
            )
        )

    assert pages[0] == pages[1]
    assert not (private / "locks" / "kb-export.lock").exists()
    assert not list((private / "locks").glob(".kb-export.stale.*"))


def test_concurrent_exports_do_not_duplicate_index_or_truncate_log(tmp_path: Path) -> None:
    exporter, root, _ = make_exporter(tmp_path)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: exporter.export("weekly", valid_report(), period_key="2026-07-19"), range(2)))

    assert results[0] == results[1]
    index = (root / "wiki" / "syntheses" / "index.md").read_text(encoding="utf-8")
    assert index.count("个人机会发现周报-2026-07-19.md") == 1
    log_lines = (root / "log.md").read_text(encoding="utf-8").splitlines()
    assert sum("个人机会发现周报-2026-07-19.md" in line for line in log_lines) == 2


@pytest.mark.parametrize(
    "name",
    ["openclaw-handoff.json", "source-feedback.json", "experiment-evidence-request.json"],
)
def test_private_bridge_files_are_0600_and_expire_in_fourteen_days(tmp_path: Path, name: str) -> None:
    exporter, _, private = make_exporter(tmp_path)
    path = exporter.write_bridge(
        name,
        valid_bridge_payload(name),
        broad_sources=["official", "paper", "github", "community"],
        targeted_searches=["端侧 Agent 失败案例"],
    )
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert path == private / "bridge" / name
    assert path.stat().st_mode & 0o777 == 0o600
    assert datetime.fromisoformat(payload["expires_at"]) - datetime.fromisoformat(payload["created_at"]) == timedelta(days=14)
    assert payload["broad_sources"] == ["official", "paper", "github", "community"]
    assert payload["targeted_searches"] == ["端侧 Agent 失败案例"]


def test_bridge_targeted_searches_never_exceed_twenty_percent_or_remove_broad_sources(tmp_path: Path) -> None:
    exporter, _, _ = make_exporter(tmp_path)
    with pytest.raises(ValidationError):
        exporter.write_bridge(
            "source-feedback.json",
            valid_bridge_payload("source-feedback.json"),
            broad_sources=["official", "paper", "github"],
            targeted_searches=["targeted"],
        )

def test_bridge_rejects_secrets_in_source_lists(tmp_path: Path) -> None:
    exporter, _, _ = make_exporter(tmp_path)
    with pytest.raises(ValidationError):
        exporter.write_bridge(
            "openclaw-handoff.json",
            valid_bridge_payload("openclaw-handoff.json"),
            broad_sources=["official", "paper", "github", "token=abcdefghijklmnop"],
            targeted_searches=[],
        )


@pytest.mark.parametrize(
    "invalid",
    [float("nan"), float("inf"), b"bytes", object(), {"nested": [float("-inf")] }],
)
def test_bridge_recursively_rejects_non_json_and_nonfinite_values(tmp_path: Path, invalid: object) -> None:
    exporter, _, _ = make_exporter(tmp_path)
    with pytest.raises(ValidationError):
        exporter.write_bridge(
            "openclaw-handoff.json",
            {"operation": invalid},
            broad_sources=["official", "paper", "github", "community"],
            targeted_searches=[],
        )


def test_bridge_rejects_private_paths_anywhere_in_payload_or_lists(tmp_path: Path) -> None:
    exporter, _, _ = make_exporter(tmp_path)
    with pytest.raises(ValidationError):
        exporter.write_bridge(
            "openclaw-handoff.json",
            {"nested": {"request": "/Users/person/private"}},
            broad_sources=["official", "paper", "github", "community"],
            targeted_searches=[],
        )
    with pytest.raises(ValidationError):
        exporter.write_bridge(
            "openclaw-handoff.json",
            valid_bridge_payload("openclaw-handoff.json"),
            broad_sources=["official", "paper", "github", "community"],
            targeted_searches=["/Users/person/query"],
        )
    with pytest.raises(ValidationError):
        exporter.write_bridge(
            "openclaw-handoff.json",
            {"/Users/person/key": "value"},
            broad_sources=["official", "paper", "github", "community"],
            targeted_searches=[],
        )


def test_targeted_ratio_accepts_exact_twenty_percent_and_rejects_above(tmp_path: Path) -> None:
    exporter, _, _ = make_exporter(tmp_path)
    assert exporter.write_bridge(
        "source-feedback.json",
        valid_bridge_payload("source-feedback.json"),
        broad_sources=["a", "b", "c", "d"],
        targeted_searches=["target"],
    ).is_file()
    with pytest.raises(ValidationError):
        exporter.write_bridge(
            "source-feedback.json",
            valid_bridge_payload("source-feedback.json"),
            broad_sources=["a", "b", "c", "d"],
            targeted_searches=["target-1", "target-2"],
        )


@pytest.mark.parametrize("bad_sources", ["official", b"official", {"official": True}, iter(["official"])])
def test_bridge_source_collections_must_be_supported_non_string_arrays(tmp_path: Path, bad_sources) -> None:
    exporter, _, _ = make_exporter(tmp_path)
    with pytest.raises(ValidationError):
        exporter.write_bridge(
            "source-feedback.json",
            valid_bridge_payload("source-feedback.json"),
            broad_sources=bad_sources,
            targeted_searches=[],
        )


@pytest.mark.parametrize(
    ("broad", "targeted"),
    [
        (["official", " official "], []),
        (["Official", "official"], []),
        (["ＯＦＦＩＣＩＡＬ", "official"], []),
        (["official", "paper", "github", "community"], ["Target", " target "]),
        (["Official", "paper", "github", "community"], [" official "]),
    ],
)
def test_bridge_sources_reject_normalized_duplicates_and_broad_target_overlap(
    tmp_path: Path, broad: list[str], targeted: list[str]
) -> None:
    exporter, _, _ = make_exporter(tmp_path)
    with pytest.raises(ValidationError):
        exporter.write_bridge(
            "source-feedback.json",
            valid_bridge_payload("source-feedback.json"),
            broad_sources=broad,
            targeted_searches=targeted,
        )


def test_bridge_accepts_supported_tuple_sources_and_preserves_exact_ratio_boundary(tmp_path: Path) -> None:
    exporter, _, _ = make_exporter(tmp_path)
    path = exporter.write_bridge(
        "source-feedback.json",
        valid_bridge_payload("source-feedback.json"),
        broad_sources=("official", "paper", "github", "community"),
        targeted_searches=("target",),
    )
    assert path.is_file()


def test_expired_bridge_is_not_returned(tmp_path: Path) -> None:
    exporter, _, _ = make_exporter(tmp_path)
    exporter.write_bridge(
        "openclaw-handoff.json",
        valid_bridge_payload("openclaw-handoff.json"),
        broad_sources=["a", "b", "c", "d"],
        targeted_searches=[],
    )
    future = KnowledgeExporter(exporter.knowledge_root, private_home=exporter.private_home, now=lambda: NOW + timedelta(days=15))
    assert future.read_bridge("openclaw-handoff.json") is None
    assert not (exporter.private_home / "bridge" / "openclaw-handoff.json").exists()


@pytest.mark.parametrize(
    ("name", "payload"),
    [
        ("openclaw-handoff.json", {"operation": "add_handoff_refs", "entity_ids": [ENTITY_ID]}),
        ("source-feedback.json", {"operation": "add_targeted_searches"}),
        (
            "experiment-evidence-request.json",
            {"operation": "add_evidence_queries", "experiment_ids": [EXPERIMENT_ID]},
        ),
    ],
)
def test_bridge_accepts_only_typed_additive_payloads_and_generates_locked_policy(
    tmp_path: Path, name: str, payload: dict
) -> None:
    exporter, _, _ = make_exporter(tmp_path)
    path = exporter.write_bridge(
        name,
        payload,
        broad_sources=["official", "paper", "github", "community"],
        targeted_searches=["端侧 Agent 失败案例"],
    )
    document = json.loads(path.read_text(encoding="utf-8"))

    assert document["payload"] == payload
    assert document["policy"] == {"mode": "add_only", "broad_sources_locked": True}


@pytest.mark.parametrize(
    ("name", "payload"),
    [
        ("source-feedback.json", {}),
        ("source-feedback.json", {"operation": "turn off"}),
        ("source-feedback.json", {"operation": "停用"}),
        ("source-feedback.json", {"operation": "关闭"}),
        ("source-feedback.json", {"action": "turn off"}),
        ("source-feedback.json", {"request": "关闭 broad sources"}),
        ("source-feedback.json", {"instructions": "disable collection"}),
        ("source-feedback.json", {"operation": "add_targeted_searches", "unknown": True}),
        ("source-feedback.json", {"operation": {"name": "add_targeted_searches"}}),
        ("openclaw-handoff.json", {"operation": "add_targeted_searches"}),
        ("openclaw-handoff.json", {"operation": "add_handoff_refs"}),
        ("openclaw-handoff.json", {"operation": "add_handoff_refs", "entity_ids": []}),
        (
            "openclaw-handoff.json",
            {"operation": "add_handoff_refs", "entity_ids": [ENTITY_ID], "extra": True},
        ),
        ("openclaw-handoff.json", {"operation": "add_handoff_refs", "entity_ids": ["../private"]}),
        ("openclaw-handoff.json", {"operation": "add_handoff_refs", "entity_ids": ["opp:not-a-uuid"]}),
        (
            "openclaw-handoff.json",
            {"operation": "add_handoff_refs", "entity_ids": [EXPERIMENT_ID]},
        ),
        (
            "openclaw-handoff.json",
            {"operation": "add_handoff_refs", "entity_ids": [ENTITY_ID.upper()]},
        ),
        (
            "openclaw-handoff.json",
            {"operation": "add_handoff_refs", "entity_ids": [ENTITY_ID, ENTITY_ID]},
        ),
        ("openclaw-handoff.json", {"operation": "add_handoff_refs", "entity_ids": ENTITY_ID}),
        ("experiment-evidence-request.json", {"operation": "add_evidence_queries"}),
        (
            "experiment-evidence-request.json",
            {"operation": "add_evidence_queries", "experiment_ids": []},
        ),
        (
            "experiment-evidence-request.json",
            {"operation": "add_evidence_queries", "experiment_ids": [ENTITY_ID]},
        ),
        (
            "experiment-evidence-request.json",
            {"operation": "add_evidence_queries", "experiment_ids": [EXPERIMENT_ID.upper()]},
        ),
        (
            "experiment-evidence-request.json",
            {"operation": "add_evidence_queries", "experiment_ids": [EXPERIMENT_ID, EXPERIMENT_ID]},
        ),
        (
            "experiment-evidence-request.json",
            {"operation": "add_evidence_queries", "experiment_ids": ["experiment:fake"]},
        ),
        (
            "experiment-evidence-request.json",
            {"operation": "add_evidence_queries", "experiment_ids": [{"id": EXPERIMENT_ID}]},
        ),
    ],
)
def test_bridge_rejects_legacy_free_text_wrong_enum_unknown_nested_and_fake_ids(
    tmp_path: Path, name: str, payload: dict
) -> None:
    exporter, _, _ = make_exporter(tmp_path)
    with pytest.raises(ValidationError):
        exporter.write_bridge(
            name,
            payload,
            broad_sources=["official", "paper", "github", "community"],
            targeted_searches=["target"],
        )
