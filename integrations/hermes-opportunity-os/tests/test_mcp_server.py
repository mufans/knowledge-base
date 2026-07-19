import importlib.util
import sys
from pathlib import Path


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "knowledge"
SERVER_PATH = Path(__file__).parents[1] / "mcp_server.py"


def load_server(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("KNOWLEDGE_BASE_PATH", str(FIXTURE_ROOT))
    monkeypatch.setenv("OPPORTUNITY_OS_HOME", str(tmp_path / "private"))
    sys.modules.pop("opportunity_mcp_server", None)
    spec = importlib.util.spec_from_file_location("opportunity_mcp_server", SERVER_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_mcp_server_registers_expected_name_and_reads_signals(monkeypatch, tmp_path: Path) -> None:
    server = load_server(monkeypatch, tmp_path)

    assert server.mcp.name == "opportunity-discovery-os"
    signals = server.list_signals(days=2, limit=10, offset=0, query=None, today="2026-07-19")
    assert len(signals) == 3


def test_mcp_server_saves_a_typed_opportunity(monkeypatch, tmp_path: Path) -> None:
    server = load_server(monkeypatch, tmp_path)

    saved = server.save_opportunity(
        title="跨领域机会",
        opportunity_type="cross_domain",
        summary="验证移动端能力迁移。",
        presentation_bucket="surprise",
        supporting_evidence=[{"kind": "fact", "stance": "support", "claim": "官方发布。", "source_name": "官方", "source_url": "https://example.com/official", "observed_at": "2026-07-19", "source_tier": "official"}],
        opposing_evidence=[{"kind": "inference", "stance": "oppose", "claim": "需求未验证。", "source_name": "分析", "source_url": "https://example.com/analysis", "observed_at": "2026-07-19", "source_tier": "secondary"}],
        invalidation_conditions=["两轮无反馈"],
        experience_fit="工程经验可迁移。",
        experiment={"title": "访谈", "hypothesis": "存在需求", "starts_at": "2026-07-20", "ends_at": "2026-07-27", "cost_level": "low", "action": "访谈三人", "success_metric": "两人确认", "continue_criteria": ["两人确认"], "stop_criteria": ["无人确认"]},
        continue_criteria=["获得需求证据"],
        stop_criteria=["无人确认"],
        scores={"market_demand": 7, "experience_advantage": 6, "growth_potential": 8, "low_cost_validation": 8, "long_term_asset": 7, "cashflow_potential": 5, "interest_signal": 4},
    )

    assert saved["id"].startswith("opp-")
    assert server.system_status()["opportunity_count"] == 1


def test_mcp_server_exposes_all_state_transition_tools(monkeypatch, tmp_path: Path) -> None:
    server = load_server(monkeypatch, tmp_path)

    for tool_name in (
        "record_experiment", "set_direction", "get_portfolio", "record_tech_state", "save_review"
    ):
        assert callable(getattr(server, tool_name))


def test_save_opportunity_tool_description_names_evidence_source_tiers() -> None:
    spec = importlib.util.spec_from_file_location("opportunity_mcp_doc", SERVER_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    description = module.save_opportunity.__doc__ or ""

    for value in ("official", "primary", "secondary", "community", "Fact"):
        assert value in description
