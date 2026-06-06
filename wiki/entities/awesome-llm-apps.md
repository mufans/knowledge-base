---
title: "awesome llm apps"
category: "entities"
tags: ["GitHub", "工具", "框架"]
rating: 8.0
description: "tags: #LLMApps #AgentExamples #RAG #Python #ReferenceCollection"
date: "2026-05-07"
---

# awesome-llm-apps

> tags: #LLMApps #AgentExamples #RAG #Python #ReferenceCollection
> source: [ai-knowledge-base/articles/2026-04-29-shubhamsabooawesome-llm-apps.json](https://github.com/Shubhamsaboo/awesome-llm-apps)
> project: [awesome-llm-apps](https://github.com/Shubhamsaboo/awesome-llm-apps)
> score: 技术深度6/10 | 实用价值9/10 | 时效性8/10 | 领域匹配8/10 | 综合 7.75/10

## 核心概念

awesome-llm-apps 是一个收录 100+ 可运行的 AI Agent 和 RAG 应用的开源合集（108k+ GitHub stars），每个应用都提供完整代码、数据集和部署说明。它不是框架或工具，而是一个实践参考库，覆盖了 LLM 应用的主要场景：RAG、Agent、多模态、代码生成、数据分析等。

## 设计原理

**可复现性优先**：每个应用都包含完整的数据处理流程、模型调用代码和部署配置，可以直接 clone 运行。这种"可运行"的标准比大多数 awesome-list 的"仅链接"更有实际价值。

**场景覆盖广度**：从简单的 PDF RAG 到复杂的多 Agent 协作系统，从文本到多模态，覆盖了 LLM 应用开发的主要模式。适合作为学习路线图和实现参考。

## 关键实现

- **RAG 应用**：PDF/网页/数据库 RAG，含多种分块和检索策略
- **Agent 应用**：单 Agent 工具调用、多 Agent 协作、AutoGen/LangGraph 集成
- **多模态**：图像理解、视频分析、语音交互
- **代码生成**：代码补全、代码审查、自动化测试
- **数据分析**：自然语言查询数据库、自动生成报表

## 关联分析

- 与 [Dify](Dify.md) 的关系：Dify 可以作为这些应用的可视化编排平台
- 与 [browser-use](browser-use.md) 的关系：部分应用使用 browser-use 实现 Web 自动化
- 与 [Self-RAG](../concepts/Self-RAG.md) 的关系：部分 RAG 应用的检索策略可参考 Self-RAG

## 可执行建议

1. **按需学习**：根据当前项目需求，找到对应场景的参考实现，快速上手
2. **RAG 实现参考**：如果要构建 RAG 系统，这里的多种分块和检索策略实现是最佳参考
3. **多 Agent 参考架构**：学习不同多 Agent 框架的使用模式和最佳实践

## 自评
| 维度 | 分数 | 权重 | 加权 |
|------|------|------|------|
| 摘要质量 | 7 | 0.25 | 1.75 |
| 技术深度 | 6 | 0.25 | 1.50 |
| 相关性 | 8 | 0.20 | 1.60 |
| 原创性 | 7 | 0.15 | 1.05 |
| 格式规范 | 8 | 0.15 | 1.20 |
| **加权总分** | | | **7.10** |