from hashlib import sha256
from pathlib import Path

from opportunity_os.contracts import (
    Claim,
    EvidenceContract,
    WikiCandidateContract,
    content_hash,
)
from opportunity_os.knowledge_compiler import KnowledgeCompiler, QualityGate, REQUIRED_SECTIONS


def evidence(identifier: str, stance: str, claim: str) -> EvidenceContract:
    return EvidenceContract(
        id=identifier,
        source_url=f"https://example.com/{identifier}",
        collected_at="2026-07-29T00:00:00Z",
        content_hash=content_hash(claim),
        run_id="run-compiler-fixture",
        claim_type="fact" if stance == "support" else "inference",
        stance=stance,
        claim=claim,
        source_name=identifier,
        source_tier="official" if stance == "support" else "secondary",
    )


SUPPORT = evidence("evidence-support-fixture", "support", "Android 测试通过 100% 样本。")
OPPOSE = evidence("evidence-oppose-fixture", "oppose", "样本不足以证明生产成熟度。")


def candidate(
    *,
    page_type: str = "synthesis",
    action: str = "create",
    target_path: str = "wiki/syntheses/Agent-Mobile-Compiler.md",
    human_decision: str = "approved",
    claims: tuple[Claim, ...] | None = None,
    sections: dict[str, str] | None = None,
    novelty_score: float = 0.8,
) -> WikiCandidateContract:
    page_sections = sections or {
        name: f"Agent 与移动端的{name}包含可验证证据。"
        for name in REQUIRED_SECTIONS[page_type]
    }
    return WikiCandidateContract(
        id="candidate-compiler-fixture",
        source_url=SUPPORT.source_url,
        collected_at="2026-07-29T00:00:00Z",
        content_hash=content_hash(page_sections),
        run_id="run-compiler-fixture",
        page_type=page_type,
        action=action,
        title="Agent Mobile Compiler",
        tags=("Agent", "Mobile", "Evidence"),
        target_path=target_path,
        analysis_id="analysis-compiler-fixture",
        claims=claims or (
            Claim(
                id="claim-support-fixture",
                claim_type="fact",
                text="Android 测试通过 100% 样本。",
                evidence_ids=(SUPPORT.id,),
            ),
            Claim(
                id="claim-oppose-fixture",
                claim_type="inference",
                text="生产成熟度仍需验证。",
                evidence_ids=(OPPOSE.id,),
            ),
        ),
        evidence_ids=(SUPPORT.id, OPPOSE.id),
        opposing_evidence_ids=(OPPOSE.id,),
        sections=page_sections,
        novelty_summary="首次把 Agent 证据与移动端验证条件关联。",
        novelty_score=novelty_score,
        purpose_relevance=1,
        actionable_next_step="运行 Android 兼容性实验。",
        human_decision=human_decision,
    )


def roots(tmp_path: Path) -> tuple[Path, Path]:
    knowledge = tmp_path / "knowledge"
    private = tmp_path / "private"
    (knowledge / "raw").mkdir(parents=True)
    for name in ("concepts", "entities", "sources", "syntheses"):
        directory = knowledge / "wiki" / name
        directory.mkdir(parents=True)
        (directory / "index.md").write_text(f"# {name}\n", encoding="utf-8")
    (knowledge / "log.md").write_text("", encoding="utf-8")
    return knowledge, private


def raw_hashes(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file()
    }


def test_each_page_type_has_distinct_minimum_sections(tmp_path: Path) -> None:
    knowledge, _ = roots(tmp_path)
    gate = QualityGate(knowledge)

    for page_type, required in REQUIRED_SECTIONS.items():
        target = f"wiki/{ {'concept':'concepts','entity':'entities','source':'sources','synthesis':'syntheses'}[page_type] }/Agent-Mobile-{page_type}.md"
        result = gate.review(candidate(page_type=page_type, target_path=target), (SUPPORT, OPPOSE))
        assert result.decision == "publish"
        assert set(required).issubset(candidate(page_type=page_type, target_path=target).sections)


def test_numeric_version_performance_claim_without_citation_is_rejected(tmp_path: Path) -> None:
    knowledge, _ = roots(tmp_path)
    uncited = Claim(
        id="claim-uncited-fixture",
        claim_type="fact",
        text="API v2 improves latency by 30%.",
        evidence_ids=(),
    )

    result = QualityGate(knowledge).review(candidate(claims=(uncited,)), (SUPPORT, OPPOSE))

    assert result.decision == "reject"
    assert result.numeric_citation_coverage == 0
    assert "numeric_version_performance_api_coverage_below_100_percent" in result.validation_errors


def test_pending_human_decision_is_successful_non_publication(tmp_path: Path) -> None:
    knowledge, _ = roots(tmp_path)

    result = QualityGate(knowledge).review(
        candidate(human_decision="pending"),
        (SUPPORT, OPPOSE),
    )

    assert result.decision == "needs_human"
    assert result.validation_errors == ()


def test_duplicate_create_is_rejected_in_favor_of_update(tmp_path: Path) -> None:
    knowledge, _ = roots(tmp_path)
    target = knowledge / "wiki" / "syntheses" / "Existing.md"
    target.write_text("# Agent Mobile Compiler\n", encoding="utf-8")

    result = QualityGate(knowledge).review(
        candidate(target_path="wiki/syntheses/New-Name.md"),
        (SUPPORT, OPPOSE),
    )

    assert result.decision == "reject"
    assert result.duplicate_target == "wiki/syntheses/Existing.md"


def test_broken_local_link_blocks_publication(tmp_path: Path) -> None:
    knowledge, _ = roots(tmp_path)
    sections = dict(candidate().sections)
    sections["行动建议"] = "参考[缺失页面](Missing.md)后运行 Android 实验。"

    result = QualityGate(knowledge).review(candidate(sections=sections), (SUPPORT, OPPOSE))

    assert result.decision == "reject"
    assert result.broken_links == ("Missing.md",)


def test_publish_updates_wiki_index_and_log_without_touching_raw(tmp_path: Path) -> None:
    knowledge, private = roots(tmp_path)
    raw_file = knowledge / "raw" / "fixture.md"
    raw_file.write_text("immutable", encoding="utf-8")
    before = raw_hashes(knowledge / "raw")

    outcome = KnowledgeCompiler(knowledge, private).run(candidate(), (SUPPORT, OPPOSE))

    page = knowledge / "wiki" / "syntheses" / "Agent-Mobile-Compiler.md"
    assert outcome.status == "success"
    assert outcome.published_path == "wiki/syntheses/Agent-Mobile-Compiler.md"
    assert "**Fact**" in page.read_text(encoding="utf-8")
    assert "(https://example.com/evidence-support-fixture)" in page.read_text(encoding="utf-8")
    assert "[Agent Mobile Compiler](Agent-Mobile-Compiler.md)" in (
        knowledge / "wiki" / "syntheses" / "index.md"
    ).read_text(encoding="utf-8")
    assert "Knowledge Compiler" in (knowledge / "log.md").read_text(encoding="utf-8")
    assert raw_hashes(knowledge / "raw") == before
