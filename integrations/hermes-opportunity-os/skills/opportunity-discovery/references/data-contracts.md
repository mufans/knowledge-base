# Data contracts

所有跨组件 v1 记录必须包含：`schema_version=1`、稳定 `id`、绝对 HTTP(S)
`source_url`、UTC `collected_at`、SHA-256 `content_hash` 和稳定 `run_id`。未知版本
fail closed；旧输入只允许经显式 migrator 进入。任何必填字段缺失必须产生可观察的
validation error，不得用空字符串替代。

- Signal：通用元数据加 `title/relative_path/category/excerpt/source_urls`。
- Evidence：通用元数据加 `claim_type/stance/claim/source_name/source_tier/locator`。`claim_type` 只能是 `fact`、`inference`、`hypothesis`；`stance` 只能是 `support` 或 `oppose`；`source_tier` 只使用四个精确值：`official`、`primary`、`secondary`、`community`。字段不可互换。
- 私有 Opportunity 卡片的兼容 Evidence DTO 仍使用 `kind`；`kind` 只能是 `fact`、`inference`、`hypothesis`，进入跨组件契约时显式迁移为 `claim_type`。
- Analysis：`signal_ids/claims/supporting_evidence_ids/opposing_evidence_ids/conflicts/knowledge_gaps/collection_questions`。
- WikiCandidate：`page_type/action/title/tags/target_path/analysis_id/claims/evidence_ids/opposing_evidence_ids/sections/novelty_summary/novelty_score/purpose_relevance/actionable_next_step/human_decision`。
- ReviewResult：`candidate_id/decision/reasons/validation_errors/fact_citation_coverage/numeric_citation_coverage/broken_links/duplicate_target`。
- Experiment v1：机会 ID、假设、动作、指标、1–14 天窗口、继续/停止标准和显式状态。
- UserOutcome：对象、对象类型、`adopted|ignored|rejected|revised`、理由与决定时间。
- Opportunity：类型、摘要、呈现桶、正反证据、失效条件、经验组合、最小实验、继续/停止标准、七维评分。
- Opportunity 生命周期：`candidate → researched → validated → active → completed/rejected/archived`；状态事件必须带原因、正反证据、实验/规则、时间和 run ID。
- Direction：`observe|validate|active`，容量分别为 5/2/1。
- Review：周期、摘要、机会 ID、意外发现、40/40/20 计数、Fact/Inference/Hypothesis。
- TechState：`known_latest/recommended_stable/maturity/official_sources/observed_at/review_due_at/stable_gates/rollback_path`。

七维评分权重：市场需求 25%、经验优势 20%、增长空间 15%、低成本验证 15%、长期资产 10%、现金流可能 10%、兴趣信号 5%。
