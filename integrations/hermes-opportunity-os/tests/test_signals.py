from hashlib import sha256
from pathlib import Path

import pytest

from opportunity_os.errors import BoundaryError
from opportunity_os.signals import SignalReader


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "knowledge"


def digest_tree(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_default_listing_is_broad_newest_first_and_traceable() -> None:
    reader = SignalReader(FIXTURE_ROOT)

    signals = reader.list_signals(days=2, limit=10, today="2026-07-19")

    assert [signal.collected_at for signal in signals] == ["2026-07-19", "2026-07-18", "2026-07-18"]
    assert {signal.category for signal in signals} == {"cross_domain", "technology"}
    assert all(signal.relative_path.startswith("raw/inbox/") for signal in signals)
    assert any("数据库" in signal.title for signal in signals)
    assert any(signal.source_urls for signal in signals)


def test_default_listing_does_not_require_a_personal_goal_filter() -> None:
    reader = SignalReader(FIXTURE_ROOT)

    titles = [item.title for item in reader.list_signals(days=2, limit=10, today="2026-07-19")]

    assert "工业质检中的轻量模型" in titles
    assert "数据库查询优化" in titles


def test_query_is_explicit_and_pagination_is_stable() -> None:
    reader = SignalReader(FIXTURE_ROOT)

    filtered = reader.list_signals(days=2, limit=10, query="Android", today="2026-07-19")
    first_page = reader.list_signals(days=2, limit=2, offset=0, today="2026-07-19")
    second_page = reader.list_signals(days=2, limit=2, offset=2, today="2026-07-19")

    assert [item.title for item in filtered] == ["Android 端侧模型工具链"]
    assert {item.id for item in first_page}.isdisjoint({item.id for item in second_page})


def test_signal_reads_do_not_mutate_raw_files() -> None:
    before = digest_tree(FIXTURE_ROOT / "raw")
    reader = SignalReader(FIXTURE_ROOT)

    reader.list_signals(days=2, limit=10, today="2026-07-19")
    reader.get_signal("raw/inbox/2026-07-18-技术动态.md")

    assert digest_tree(FIXTURE_ROOT / "raw") == before


@pytest.mark.parametrize(
    "bad_path",
    ["../purpose.md", "raw/../purpose.md", "wiki/entities/Anything.md", "/etc/passwd"],
)
def test_get_signal_rejects_paths_outside_raw_inbox(bad_path: str) -> None:
    with pytest.raises(BoundaryError, match="raw/inbox"):
        SignalReader(FIXTURE_ROOT).get_signal(bad_path)
