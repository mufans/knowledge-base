---
title: "Advisor策略：高智能低成本Agent架构"
category: "concepts"
tags: ["Agent-Architecture", "Cost-Optimization", "Claude-API", "Multi-Model"]
rating: 8.5
description: "通过Opus顾问+Sonnet执行者配对，以接近Sonnet的成本获得接近Opus的智能，一行API调用即可实现"
date: "2026-06-02"
---

# Advisor策略：高智能低成本Agent架构

> tags: #Agent-Architecture #Cost-Optimization #Claude-API #Multi-Model
> source: [The advisor strategy: Give agents an intelligence boost](https://claude.com/blog/the-advisor-strategy)
> score: 技术深度8/10 | 实用价值9/10 | 时效性9/10 | 领域匹配9/10 | 综合 8.5/10

## 核心概念

Advisor策略是一种**多模型协作架构**：将高智能模型（如Opus 4.6）作为"顾问"（Advisor），低成本低延迟模型（如Sonnet 4.6或Haiku 4.5）作为"执行者"（Executor）。顾问负责规划和决策，执行者负责具体实现，从而在Agent系统中以接近Sonnet的成本获得接近Opus的智能水平。

## 设计原理

核心洞察：Agent任务中，**关键决策点**（选择工具、判断方向、审核结果）需要高智能，但**大部分执行步骤**（代码编写、文件操作、API调用）用中等模型即可完成。将这两个角色解耦，成本可降低数倍而质量损失极小。

Anthropic在Claude Platform上原生支持了这一模式，通过`advisor_20260301`工具，只需一行配置即可启用：
- 请求头添加：`anthropic-beta: advisor-tool-2026-03-01`
- 工具列表中添加：`advisor_20260301`
- 执行者模型（如Sonnet 4.6）在需要时会自动调用顾问模型（Opus 4.6）

## 关键实现

### 基准测试数据（Anthropic官方）

**SWE-bench Multilingual**（9种语言，每种300题，5次平均）：
- Sonnet 4.6 solo：基准分
- Sonnet 4.6 + Advisor：显著高于solo（接近Opus solo水平）
- 条件：adaptive thinking关闭，high effort，bash+文件编辑工具

**BrowseComp**（1,266题，单次尝试）：
- Sonnet 4.6 solo vs Sonnet 4.6 + Advisor：Advisor版本在web搜索+fetch场景下表现显著提升
- Haiku 4.5 + Advisor：轻量执行者也能从Advisor中获益

**Terminal-Bench 2.0**（89个任务，5次尝试）：
- 每任务独立pod，3x资源分配
- Advisor策略在终端任务中同样有效

### 成本分析
- Opus 4.6 API价格约为Sonnet 4.6的**5-10倍**
- Advisor模式下，Opus仅在关键决策点被调用，实际token消耗远低于全程使用Opus
- 总成本接近Sonnet全流程，但智能输出接近Opus全流程

## 关联分析

- [Anthropic-Agent-API](../entities/Anthropic-Agent-API.md) — Advisor工具是API层原生支持的能力
- [Claude-Ecosystem-Tools](Claude-Ecosystem-Tools.md) — Advisor属于Claude生态工具链
- [Agent-Workflow-Patterns](Agent-Workflow-Patterns.md) — Advisor是多模型协作的典型模式
- [Weak-Model-Orchestration](Weak-Model-Orchestration.md) — 弱模型编排的另一种实现
- [Agent-Cost-Crisis-2026](../sources/Agent-Cost-Crisis-2026.md) — 成本优化是2026年Agent领域的核心议题

## 可执行建议

1. **立即尝试**：在现有Agent项目中，添加`advisor_20260301`工具，对比solo和advisor模式的输出质量和成本
2. **评估场景**：最适合需要复杂推理但执行步骤多的任务（编码、调研、数据分析）
3. **监控调用比例**：观察Advisor被调用的频率，如果过低说明Sonnet已经够用，如果过高说明任务本身需要Opus
4. **作为架构参考**：即使不用Claude API，这个"顾问+执行者"的分层思路也适用于其他多模型场景

## 自评

| 维度 | 分数 | 权重 | 加权 |
|------|------|------|------|
| 摘要质量 | 8.5 | 0.25 | 2.13 |
| 技术深度 | 8.0 | 0.25 | 2.00 |
| 相关性 | 9.0 | 0.20 | 1.80 |
| 原创性 | 8.0 | 0.15 | 1.20 |
| 格式规范 | 9.0 | 0.15 | 1.35 |
| **加权总分** | | | **8.48** |

> 评分说明：摘要包含了具体的API配置、基准测试数据；技术深度分析了成本效益的量化权衡；相关性极高（直接解决Agent成本问题）；原创性体现在架构选择的分析视角