---
title: "ChatGPT Work：跨应用Agent平台"
category: "entities"
tags: ["Agent-Platform", "GPT", "OpenAI", "Auto-Agent", "Workflow"]
rating: 9.0
description: "ChatGPT Work是OpenAI发布的跨应用Agent平台，在sheets/slides/docs间执行任务，支持长期规划和后台调度，内置Codex技术"
date: "2026-07-10"
---

# ChatGPT Work：跨应用Agent平台

> tags: #Agent-Platform #GPT #OpenAI #Auto-Agent #Workflow
> source: [2026-07-10-社交媒体](../raw/inbox/2026-07-10-社交媒体.md)
> project: [OpenAI ChatGPT Work](https://openai.com/index/chatgpt-for-your-most-ambitious-work/)
> score: 技术深度7/10 | 实用价值9/10 | 时效性9/10 | 领域匹配8/10 | 综合 8.0/10

## 核心概念

ChatGPT Work 是 OpenAI 推出的跨应用 Agent 平台，基于 [GPT-5.6](GPT-5.5.md) 模型，支持在 Google Sheets/Slides/Docs 等多应用间自主执行任务。具备长期任务规划、Scheduled Tasks 后台执行能力，内置 Codex 技术。

## 设计原理

对标 Claude Cowork 的"随时待命 Agent"定位，但 OpenAI 的差异化在于**更低的使用门槛**：已有 500 万+ 周活跃用户，其中 100 万+ 为非开发者用户。核心设计是 Agent 在桌面应用层而非 API 层工作，通过观察和操作应用界面完成任务，而非通过集成接口。

Trade-off：应用层操作 (GUI-driven) vs API 层集成：GUI 操作更通用（跨所有应用），但速度慢、易出错；API 层更快更可靠，但需要应用支持集成。OpenAI 选择了通用性优先。

## 关键实现

- **Cross-app 操作**：在 Sheets/Slides/Docs 间自主读取和写入
- **长期任务规划**：支持分解多步骤任务，分阶段执行
- **Scheduled Tasks**：后台定时执行，类似 Cron Job 但用自然语言配置
- **内置 Codex**：500 万+ 周活用户，100 万+ 非开发者
- **企业实践**：
  - Zapier 营销团队：潜客评审系统
  - OpenAI 内部销售：POC 出单数周 → 24 小时
  - OpenAI 财务团队：月结数天 → 数小时

## 关联分析

- 直接影响 [GPT-5.5](GPT-5.5.md) 的评估：GPT-5.6 + ChatGPT Work 共同构成了完整的 Agent 产品形态
- 与 [Claude-Cowork](../entities/Claude-Cowork.md) 直接竞争：两者都是"随时待命 Agent"，但 ChatGPT Work 更侧重办公场景，Claude Cowork 更侧重编码场景
- 与 [AutoGPT](../entities/AutoGPT.md) 等开源 Agent 框架的差异：ChatGPT Work 是封闭平台但体验更无缝
- [Agent-Cost-Crisis-2026](../sources/Agent-Cost-Crisis-2026.md) 中分析的 Agent 成本问题：ChatGPT Work 通过长规划减少轮次来压低成本

## 可执行建议

1. **对比测试**：在自动化工作流场景（如知识库同步、文档生成）对比 ChatGPT Work vs Claude Cowork
2. **关注非开发者场景**：100 万+ 非开发者用户意味着 Agent 能力正在跨越"技术壁垒"，这是重要趋势信号
3. **API vs 应用层**：评估 AppSmartInspector 是否需要考虑"应用内 Agent"形态

## 自评

| 维度 | 分数 | 权重 | 加权 |
|------|------|------|------|
| 摘要质量 | 8 | 0.25 | 2.00 |
| 技术深度 | 7 | 0.25 | 1.75 |
| 相关性 | 9 | 0.20 | 1.80 |
| 原创性 | 7 | 0.15 | 1.05 |
| 格式规范 | 9 | 0.15 | 1.35 |
| **加权总分** | | | **7.95** |