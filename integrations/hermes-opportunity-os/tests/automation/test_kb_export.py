import json
import math
import os
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from opportunity_os.automation.kb_export import KnowledgeExporter
from opportunity_os.errors import BoundaryError, ValidationError


NOW = datetime(2026, 7, 19, 10, 0, tzinfo=timezone.utc)


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
        {"request": "补充端侧 Agent 反证"},
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
            {"request": "过度定向"},
            broad_sources=["official", "paper", "github"],
            targeted_searches=["targeted"],
        )
    with pytest.raises(ValidationError):
        exporter.write_bridge(
            "source-feedback.json",
            {"policy": {"sources_to_remove": ["community"]}},
            broad_sources=["official", "paper", "github", "community"],
            targeted_searches=[],
        )


def test_bridge_rejects_secrets_in_source_lists(tmp_path: Path) -> None:
    exporter, _, _ = make_exporter(tmp_path)
    with pytest.raises(ValidationError):
        exporter.write_bridge(
            "openclaw-handoff.json",
            {"request": "补充证据"},
            broad_sources=["official", "paper", "github", "token=abcdefghijklmnop"],
            targeted_searches=[],
        )


def test_expired_bridge_is_not_returned(tmp_path: Path) -> None:
    exporter, _, _ = make_exporter(tmp_path)
    exporter.write_bridge(
        "openclaw-handoff.json", {"request": "test"}, broad_sources=["a", "b", "c", "d"], targeted_searches=[]
    )
    future = KnowledgeExporter(exporter.knowledge_root, private_home=exporter.private_home, now=lambda: NOW + timedelta(days=15))
    assert future.read_bridge("openclaw-handoff.json") is None
