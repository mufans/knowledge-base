from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
DASHBOARD = ROOT / "integrations/hermes-opportunity-os/src/opportunity_os/dashboard"


def test_control_center_has_required_metrics_and_no_inline_styles() -> None:
    source = (DASHBOARD / "static/app.js").read_text(encoding="utf-8")

    for label in (
        "PIPELINE HEALTH",
        "引用",
        "Broken links",
        "重复候选",
        "拒绝",
        "转化率",
        "用户结果",
        "Timeout",
        "投递失败",
        "最小实验",
    ):
        assert label in source
    assert "style=" not in source
    assert "total_score" not in source


def test_public_home_is_paginated_and_never_sorts_by_self_score() -> None:
    generator = (ROOT / "scripts/generate_dashboard.py").read_text(encoding="utf-8")
    frontend = (ROOT / "site_assets/knowledge-home.js").read_text(encoding="utf-8")
    config = (ROOT / "mkdocs.yml").read_text(encoding="utf-8")

    assert "wiki_files_modified=0" in generator
    assert "rating" not in generator
    assert "pageSize = 12" in frontend
    assert "Agent × Mobile" in frontend
    assert "Related Knowledge" in frontend
    assert "assets/dashboard-data.js" in config
    assert "assets/knowledge-home.js" in config
