---
title: "Agent工作流模式：顺序/并行/评估优化"
category: "concepts"
tags: ["Agent-Workflow", "Orchestration", "Sequential", "Parallel", "Evaluator-Optimizer"]
rating: 8.5
description: "Anthropic总结的三大Agent工作流模式（顺序、并行、评估-优化），覆盖生产环境90%以上的多Agent编排场景"
date: "2026-05-23"
---

# Agent工作流模式：顺序/并行/评估优化

> tags: #AgentWorkflow #Orchestration #Sequential #Parallel #EvaluatorOptimizer
> source: [Common workflow patterns for AI agents](https://claude.com/blog/common-workflow-patterns-for-ai-agents-and-when-to-use-them) | [2026-05-23-Claude博客](../../raw/inbox/2026-05-23-Claude博客.md)
> score: 技术深度8/10 | 实用价值9/10 | 时效性9/10 | 领域匹配10/10 | 综合 9.0/10

## 核心概念

Anthropic基于与数十个团队的合作经验，总结出生产环境中三种覆盖绝大多数用例的Agent工作流模式：**顺序（Sequential）、并行（Parallel）、评估-优化（Evaluator-Optimizer）**。工作流不替代Agent自主性，而是塑造Agent在哪里以及如何应用自主性——类似制造业流水线，每个工位有自主决策权，但整体流程预先设计。

## 设计原理

**工作流 vs 自主Agent的权衡**：
- **全自主Agent**：自行决定工具选择、执行顺序、停止时机。灵活性最高，但可预测性差。
- **工作流约束的Agent**：在预定义的流程框架内，每一步仍可利用Agent的推理和工具调用能力。牺牲部分灵活性，换取可调试性和可靠性。

这一思路与[Agent控制流设计](Agent-Control-Flow.md)的理念一致——**LLM是决策组件，确定性代码管流程**。

### 三种模式的Trade-off分析

| 模式 | 解决的问题 | 代价 | 收益 |
|------|-----------|------|------|
| **顺序** | 步骤间有依赖（B需要A的输出） | 延迟叠加（每步等待上一步） | 每个Agent专注一件事，准确率提升 |
| **并行** | 任务独立但串行太慢 | Token消耗翻倍+需要聚合策略 | 更快完成+关注点分离 |
| **评估-优化** | 初稿质量不够（需要迭代打磨） | Token用量倍增+迭代耗时 | 结构化反馈循环产出更高质量结果 |

## 关键实现

### 1. 顺序工作流（Sequential）
- **适用场景**：多阶段流程、数据管道、草稿-审核-润色循环
- **模式**：`Agent A → 输出 → Agent B → 输出 → Agent C`
- **要点**：每步Agent聚焦单一职责，错误可在步骤间捕获

### 2. 并行工作流（Parallel）
- **适用场景**：多维度评估、代码审查、文档分析
- **模式**：多个Agent同时执行 → 结果聚合器合并
- **要点**：需要设计聚合策略（投票、加权、串联）

### 3. 评估-优化工作流（Evaluator-Optimizer）
- **适用场景**：技术文档、客户沟通、针对特定标准的代码生成
- **模式**：`生成Agent → 评估Agent → 反馈 → 生成Agent（迭代）`
- **要点**：评估器需要明确的评价标准和量化指标

### 组合与嵌套
三种模式是构建块而非死板模板。实践中常见嵌套组合：并行评估后接顺序优化，或顺序管道中嵌入评估-优化循环。

## 关联分析

- [Agent控制流设计](Agent-Control-Flow.md)：互补视角，本文是Anthropic官方总结的三种实践模式，后者是工程化的状态机方法
- [Multi-Agent-Systems-Design](Multi-Agent-Systems-Design.md)：多Agent系统设计的更广泛讨论
- [Weak-Model-Orchestration](Weak-Model-Orchestration.md)：弱模型编排同样强调用代码逻辑管理LLM调用
- [EfficientAgent](EfficientAgent.md)：高效Agent执行中的流程优化

## 可执行建议

1. **选型决策树**：任务有依赖→顺序；任务独立→并行；质量要求高且可量化→评估-优化
2. **从顺序开始**：最简单可靠，确认单Agent步骤有效后再考虑并行或迭代优化
3. **评估器设计是关键**：评估-优化模式的效果完全取决于评估标准的明确性和可量化性
4. **Token成本意识**：并行和评估-优化都会倍增Token消耗，需在质量和成本间权衡

## 自评

| 维度 | 分数 | 权重 | 加权 |
|------|------|------|------|
| 摘要质量 | 8.5 | 0.25 | 2.13 |
| 技术深度 | 8.0 | 0.25 | 2.00 |
| 相关性 | 9.5 | 0.20 | 1.90 |
| 原创性 | 7.5 | 0.15 | 1.13 |
| 格式规范 | 9.0 | 0.15 | 1.35 |
| **加权总分** | | | **8.50** |