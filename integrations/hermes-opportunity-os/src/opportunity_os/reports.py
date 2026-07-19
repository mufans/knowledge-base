from opportunity_os.models import Evidence
from opportunity_os.store import PrivateStore


def _bullet(items: list[str]) -> list[str]:
    return [f"- {item}" for item in items]


def _evidence_line(evidence: Evidence) -> str:
    label = evidence.kind.capitalize()
    return f"- **{label}**：{evidence.claim}（[{evidence.source_name}]({evidence.source_url})，{evidence.observed_at}）"


def render_review(store: PrivateStore, review_id: str | None = None, *, latest: bool = False) -> str:
    review = store.get_review(review_id, latest=latest)
    lines = [
        f"# {review['title']}",
        "",
        f"> period: {review['period']}",
        f"> created_at: {review['created_at']}",
        "",
        review["summary"],
        "",
        "## 意外发现",
        "",
        review["surprise_signal"] or "本期不适用。",
        "",
        "## Fact",
        "",
        *_bullet(review["facts"]),
        "",
        "## Inference",
        "",
        *_bullet(review["inferences"]),
        "",
        "## Hypothesis",
        "",
        *_bullet(review["hypotheses"]),
        "",
        "## 机会卡",
        "",
    ]
    for opportunity_id in review["opportunity_ids"]:
        card = store.get_opportunity(opportunity_id)
        lines.extend(
            [
                f"### {card['title']}（{card['total_score']}/10）",
                "",
                card["summary"],
                "",
                "### 支持证据",
                "",
                *[_evidence_line(Evidence.from_dict(item)) for item in card["supporting_evidence"]],
                "",
                "### 反对证据",
                "",
                *[_evidence_line(Evidence.from_dict(item)) for item in card["opposing_evidence"]],
                "",
                "### 最小实验",
                "",
                f"- 动作：{card['minimum_experiment']['action']}",
                f"- 时间：{card['minimum_experiment']['starts_at']} 至 {card['minimum_experiment']['ends_at']}",
                f"- 成功指标：{card['minimum_experiment']['success_metric']}",
                f"- 失效条件：{'；'.join(card['invalidation_conditions'])}",
                "",
            ]
        )
    lines.extend(
        [
            "## 新鲜度与稳定性",
            "",
            "- 最新信号仅表示 `known_latest`；采用建议以 `recommended_stable` 为准。",
            "- 超过 `review_due_at` 触发复核，不自动使既有结论失效。",
            "",
        ]
    )
    return "\n".join(lines)
