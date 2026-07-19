# Operating rhythm

- 每日：3–5 项重要变化，至少一项意外发现。
- 每周：3–5 张机会卡、正反证据、方向热度和一个最小实验建议。
- 每两周：完成一个真实验并记录支持或反对证据。
- 每六周：更新方向组合，允许没有 active 方向。
- 每季度：清零式复核方向假设、来源效果和 Stable 基线。

这些是调用模板，不代表安装任何 Hermes Cron；生产调度仍由 OpenClaw 单独负责。

## 非交互运行约束

- 每次运行先读取未经个人目标过滤的广域输入；广域输入不少于 80%，定向补充不超过 20%，且定向反馈只能增加检索，不能移除或减少广域来源。
- Bridge 只接受 typed additive operation：`openclaw-handoff.json` 使用 `add_handoff_refs`，`source-feedback.json` 使用 `add_targeted_searches`，`experiment-evidence-request.json` 使用 `add_evidence_queries`。payload 不接受 `request`、`action`、`instructions` 或任意自由文本；服务端生成 `policy: {mode: add_only, broad_sources_locked: true}`，调用方不得提交或覆盖该策略。
- 每次分析主动寻找反对证据并保留跨领域意外发现；时间紧张时也不得只看当前主轴、已有项目或历史偏好。
- 非交互运行不得修改 Memory 或 Skill。发现流程、记忆或 Skill 可以改进时，只生成独立的改进建议草案，等待用户审核。
- 不得执行任何外部行动，包括发布、投递、联系、发送消息、付费、删除、推送或修改 OpenClaw；即使用户要求赶时间，也只能给出待审核草案。
