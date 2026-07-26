---
title: "Context Engineering：从Carta Healthcare到YC Startups的实践"
category: "concepts"
tags: ["Context-Engineering", "Prompt-Design", "Production-AI", "Agent-Architecture"]
rating: 8.8
description: "从Carta Healthcare 99%准确率到YC startup工作流，再到Claude 5代模型的'少即是多'范式：Context Engineering从'加什么'到'删什么'的演进"
date: "2026-07-26"
---

# Context Engineering：从Carta Healthcare到YC Startups的实践

> tags: #Context-Engineering #Prompt-Design #Production-AI #Agent-Architecture
> source: [Carta Healthcare](https://claude.com/blog/carta-healthcare-clinical-abstractor) | [YC Startups](https://claude.com/blog/building-companies-with-claude-code) | [Claude Blog New Rules](https://claude.com/blog/the-new-rules-of-context-engineering-for-claude-5-generation-models)
> score: 技术深度8/10 | 实用价值9/10 | 时效性9/10 | 领域匹配9/10 | 综合 8.75/10

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

### 2026-07-26 更新：Claude 5代模型的Context Engineering新规则

Anthropic于2026年7月发布面向Claude 5代模型（Opus 5、Fable 5）的Context Engineering新规则，核心发现是：**对于更强大的模型，更少的约束反而带来更好的结果**。

**关键发现**

1. **删除80%+系统提示词**：Anthropic从Claude Code中删除了超过80%的系统提示词，在编码评估上没有任何可测量的性能损失。这与此前"提示词越详细越好"形成直接矛盾。

2. **"Unhobbling" Claude（解除束缚）**：团队在审查内部使用记录时发现，同一个请求中收到多条冲突指令——"适当写文档"来自系统提示，"不要加注释"来自用户请求，"遵循最佳实践"来自skills。多重约束相互矛盾，反而限制了模型的能力发挥。

3. **旧的最佳实践已成迷思**：为早期模型（Claude 3/4）设计的context engineering最佳实践，在Claude 5代模型上可能适得其反。模型能力的跃升要求重新审视每一条约束的必要性。

4. **`claude doctor` 自动调整**：新增`/doctor`命令，自动扫描并优化skills和CLAUDE.md文件，删除过时或冲突的约束。

**trade-off分析**：删减context的核心风险是失去行为控制（安全边界、品牌调性）。这不是简单的"全部删掉"，而是精准识别哪些约束对当前模型是必要的、哪些是历史遗留。对于企业级部署，需要在"充分信任模型能力"和"维持必要安全边界"之间找到新平衡。

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
- [Verification-Loops](Verification-Loops.md) — Agent编码验证闭环，与context engineering形成互补

## 可执行建议

1. **在写prompt前先设计context管道**：确定需要什么信息、从哪来、如何过滤、以什么顺序组织
2. **建立粒度化评估框架**：能区分是prompt问题、context问题还是retrieval问题
3. **采用三阶段分离工作流**：研究→规划→实现，每阶段独立session
4. **消除上下文矛盾**：使用前检查prompt中是否存在冲突信息
5. **非技术人员也能高效使用AI**：重点训练结构化表达能力而非编程技能
6. **定期审查context约束**：每次模型升级时，重新评估每条约束的必要性——如果删掉不影响质量就删掉
7. **运行 `claude doctor`**：使用新命令自动优化skills和CLAUDE.md配置

## 自评

| 维度 | 分数 | 权重 | 加权 |
|------|------|------|------|
| 摘要质量 | 9 | 0.25 | 2.25 |
| 技术深度 | 9 | 0.25 | 2.25 |
| 相关性 | 9 | 0.20 | 1.80 |
| 原创性 | 8 | 0.15 | 1.20 |
| 格式规范 | 9 | 0.15 | 1.35 |
| **加权总分** | | | **8.85** |
