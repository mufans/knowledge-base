---
title: "MetaGPT"
category: "entities"
tags: ["GPT", "GitHub", "OpenAI", "框架"]
rating: 8.0
description: "tags: #MultiAgent #SoftwareDevelopment #SOP #Python"
date: "2026-05-07"
---

# MetaGPT

> tags: #MultiAgent #SoftwareDevelopment #SOP #Python
> source: [ai-knowledge-base/articles/2026-04-29-foundationagentsmetagpt.json](https://github.com/FoundationAgents/MetaGPT)
> project: [MetaGPT](https://github.com/FoundationAgents/MetaGPT)
> score: 技术深度8/10 | 实用价值7/10 | 时效性7/10 | 领域匹配8/10 | 综合 7.55/10

## 核心概念

MetaGPT 是一个多 Agent 协作框架（67k+ GitHub stars），核心理念是将软件开发公司的 SOP（标准操作流程）编码为 Agent 协作规范。每个 Agent 扮演特定角色（产品经理、架构师、工程师、QA），通过结构化输出（PRD、设计文档、代码）进行协作，模拟真实软件团队的工作流。

## 设计原理

**SOP 驱动的 Agent 协作**：MetaGPT 的核心创新不是多 Agent 本身（AutoGen 等已有多 Agent 框架），而是将人类软件开发的 SOP 作为 Agent 交互协议。每个 Agent 的输入/输出格式由 SOP 定义（如 PM 输出 PRD、架构师输出系统设计），避免了自由对话导致的混乱。Trade-off 是灵活性降低，但在软件开发这类结构化任务中效率显著提升。

**结构化输出作为 Agent 间通信协议**：Agent 之间不传递自然语言，而是传递结构化文档（Markdown 格式的 PRD、设计文档等）。这使得每一步的输出可审计、可回溯，也便于人类介入检查。

**角色专业化**：每个 Agent 有明确的职责边界和能力范围，通过 prompt 定义角色行为。这比"通用 Agent"更可靠，因为角色收敛了搜索空间。

## 关键实现

- **角色系统**：ProductManager → Architect → ProjectManager → Engineer → QA，完整的软件开发生命周期
- **结构化输出**：每个角色输出标准化文档（PRD.md、system_design.md、*.py）
- **Human-in-the-loop**：支持在关键节点暂停等待人类审批
- **研究模式**：Researcher + Engineer 协作进行技术调研
- **数据分析和网页爬虫**：支持 Data Analyst、Web Crawler 等非开发角色

```python
from metagpt.software_company import SoftwareCompany
from metagpt.roles import ProductManager, Architect, Engineer

company = SoftwareCompany()
company.hire([ProductManager(), Architect(), Engineer()])
company.invest(investment=5.0)
company.start_project("Write a CLI snake game")
```

## 关联分析

- 与 [Dify](Dify.md) 对比：MetaGPT 代码驱动、SOP 约束、多角色协作；Dify 可视化驱动、灵活编排、单 Agent 为主
- 与 [browser-use](browser-use.md) 的关系：browser-use 可作为 MetaGPT Engineer 角色的工具，实现网页自动化
- 相关概念：[AI-Agent-Self-Improving](../concepts/AI-Agent-Self-Improving.md)（Agent 自我迭代）

## 可执行建议

1. **参考 SOP 设计理念**：在构建自己的多 Agent 系统时，借鉴 MetaGPT 的角色专业化 + 结构化输出模式
2. **作为多 Agent 研究基线**：评估其他多 Agent 框架时，MetaGPT 是重要的对比基准
3. **PRD/设计文档生成**：可用于快速生成项目文档，但需人工审核质量

## 自评
| 维度 | 分数 | 权重 | 加权 |
|------|------|------|------|
| 摘要质量 | 8 | 0.25 | 2.00 |
| 技术深度 | 8 | 0.25 | 2.00 |
| 相关性 | 8 | 0.20 | 1.60 |
| 原创性 | 7 | 0.15 | 1.05 |
| 格式规范 | 8 | 0.15 | 1.20 |
| **加权总分** | | | **7.85** |