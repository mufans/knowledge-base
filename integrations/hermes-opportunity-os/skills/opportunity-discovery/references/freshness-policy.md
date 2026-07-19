# Freshness policy

观察开放，采用保守：

- `known_latest` 记录官方已知最新状态；`recommended_stable` 记录本地建议采用状态。
- 新版本先标记 Frontier。
- Stable 晋升要求：官方正式发布、文档完整、最小兼容测试通过、无严重已知问题、回滚路径已准备。
- `review_due_at` 到期只触发复核，不自动使既有结论失效。
- 官方来源不可用时保留 Stable，报告本次未复核；来源冲突时保留冲突，不自动覆盖。
