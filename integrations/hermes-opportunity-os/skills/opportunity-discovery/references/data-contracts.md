# Data contracts

- Signal：`id/title/relative_path/collected_at/category/excerpt/source_urls`。
- Evidence：`kind/stance/claim/source_name/source_url/observed_at/source_tier`。`kind` 只能是 `fact`、`inference`、`hypothesis`；`stance` 只能是 `support` 或 `oppose`；`source_tier` 只使用四个精确值：`official`（官方发布或文档）、`primary`（原始代码、论文或数据）、`secondary`（二手分析）、`community`（媒体、社区或热度）。这三组字段不可互换。
- Opportunity：类型、摘要、呈现桶、正反证据、失效条件、经验组合、最小实验、继续/停止标准、七维评分。
- Direction：`observe|validate|active`，容量分别为 5/2/1。
- Review：周期、摘要、机会 ID、意外发现、40/40/20 计数、Fact/Inference/Hypothesis。
- TechState：`known_latest/recommended_stable/maturity/official_sources/observed_at/review_due_at/stable_gates/rollback_path`。

七维评分权重：市场需求 25%、经验优势 20%、增长空间 15%、低成本验证 15%、长期资产 10%、现金流可能 10%、兴趣信号 5%。
