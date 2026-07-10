---
title: "Context Engineering：从Carta Healthcare到YC Startups的实践"
category: "concepts"
tags: ["Context-Engineering", "Prompt-Design", "Production-AI", "Agent-Architecture"]
rating: 8.5
description: "从Carta Healthcare 99%准确率和YC startup工作流中提炼的context engineering核心方法论：喂给模型什么比模型本身更重要"
date: "2026-05-18"
---

# Context Engineering：从Carta Healthcare到YC Startups的实践

> tags: #Context-Engineering #Prompt-Design #Production-AI #Agent-Architecture
> source: [Carta Healthcare](https://claude.com/blog/carta-healthcare-clinical-abstractor) | [YC Startups](https://claude.com/blog/building-companies-with-claude-code)
> score: 技术深度8/10 | 实用价值9/10 | 时效性9/10 | 领域匹配8/10 | 综合 8.5/10

## 核心概念

Context Engineering是指**系统性地设计输入给LLM的上下文内容、顺序和范围**，使其性能最大化。这不是简单的prompt技巧，而是一整套工程化流程：决定包含什么、排除什么、以什么顺序呈现。核心洞察：**最好的prompt配错误的context = 错误的输出；简单的prompt配正确的context = 正确的输出**。

## 设计原理

### Carta Healthcare：上下文精度决定准确率

Carta Healthcare的Lighthouse平台处理22,000+手术病例/年，达到 **98-99% inter-rater reliability**（行业标准的抽象准确率）。核心不是模型选择，而是context构建：

- **时间边界精确化**：不是"找一个体重值"，而是"找到在特定手术开始时间之前记录的体重值"。手术后两天的体重是无效数据
- **运行时动态组装**：每个数据点需要不同的源文档、不同的时间窗口、不同的上下文量
- **可追溯性**：每个提取结果都展示支持证据和推理过程，临床专家可验证

> "The hardest problems we solved weren't about building a perfect prompt, they were about context construction." — Matthew Mazzanti, Carta Healthcare

关键工程决策：**评估框架先行**，粒度化设计以隔离变量。当输出不理想时，可追溯到具体是哪个prompt、哪个context issue、哪个retrieval gap。

### YC Startups：三层分离工作流

三家YC公司共同验证的工作流模式：

**1. Research → Planning → Implementation 三阶段分离**
- Ambral的Stettner：Opus 4.1做研究和规划，Sonnet 4.5做实现。"不要让Claude同时做研究、规划和实现"
- 每个阶段用独立的Claude Code session，只传递精炼结论而非全部上下文
- 子Agent并行研究代码库的不同区域

**2. 上下文管理是成败关键**
- Stettner："当我看到意外或低质量的输出，通常是因为prompt中存在矛盾"
- Jones："审视思维链，手指放在中断键上"
- 核心原则：避免上下文矛盾，明确选择何时开始新对话

**3. 非技术创始人的语言优势**
- Vulcan的Jones（高中后没写过代码）用Claude Code赢了政府合同，4个月融了$11M
- 洞察：语言能力和批判性思维比编程技能更重要——"如果你擅长组织有序列表、嵌套要点和清晰流程，你的prompt可能执行得更好"

## 关键实现

```python
# Carta Healthcare的context精确化模式
# 不是简单的 "find glucose value"
# 而是：
prompt = f"""
Find the most recent glucose reading documented BEFORE 
procedure start time: {procedure_start_time}.
Include source document reference and exact timestamp.
"""
```

```python
# Ambral的研究-规划-实现分离
# Phase 1: Research (Opus 4.1)
research_doc = opus.research(feature)  # 长文档，多角度
# Phase 2: Planning (Opus 4.1) 
plan = opus.plan(research_doc)  # 离散步进计划
# Phase 3: Implementation (Sonnet 4.5)
for phase in plan.phases:
    sonnet.implement(phase)  # 每步独立执行
```

## 关联分析

- [Multi-Agent-Systems-Design](Multi-Agent-Systems-Design.md) — 多Agent系统中的上下文隔离
- [Context-Window-Optimization](Context-Window-Optimization.md) — 上下文窗口优化技术
- [Claude-Code-Source-Analysis](../entities/Claude-Code-Source-Analysis.md) — Claude Code的上下文管理
- [Prompt-Caching-Pitfalls](Prompt-Caching-Pitfalls.md) — Prompt缓存陷阱
- [Agent-Control-Flow](Agent-Control-Flow.md) — Agent流程控制模式

## 可执行建议

1. **在写prompt前先设计context管道**：确定需要什么信息、从哪来、如何过滤、以什么顺序组织
2. **建立粒度化评估框架**：能区分是prompt问题、context问题还是retrieval问题
3. **采用三阶段分离工作流**：研究→规划→实现，每阶段独立session
4. **消除上下文矛盾**：使用前检查prompt中是否存在冲突信息
5. **非技术人员也能高效使用AI**：重点训练结构化表达能力而非编程技能

## 自评

| 维度 | 分数 | 权重 | 加权 |
|------|------|------|------|
| 摘要质量 | 9 | 0.25 | 2.25 |
| 技术深度 | 8 | 0.25 | 2.00 |
| 相关性 | 9 | 0.20 | 1.80 |
| 原创性 | 8 | 0.15 | 1.20 |
| 格式规范 | 9 | 0.15 | 1.35 |
| **加权总分** | | | **8.60** |