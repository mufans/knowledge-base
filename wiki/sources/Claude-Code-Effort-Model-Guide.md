---
title: "Claude Code模型选择与Effort Level配置指南"
category: "sources"
tags: ["Claude-Code", "Model-Selection", "Effort-Level", "Agentic-Coding", "Anthropic"]
rating: 9.0
description: "Anthropic官方解读Claude Code的两个调节旋钮：Model=能力范围（Fable/Opus/Sonnet选型），Effort=工作深度（控制读取文件数、验证步骤、多步推进程度）"
date: "2026-07-19"
---

# Claude Code模型选择与Effort Level配置指南

> tags: #Claude-Code #Model-Selection #Effort-Level #Agentic-Coding #Anthropic
> source: [Choosing a Claude model and effort level in Claude Code](https://claude.com/blog/claude-model-and-effort-level-in-claude-code)
> score: 技术深度7/10 | 实用价值8/10 | 时效性9/10 | 领域匹配8/10 | 综合 8.0/10

## 核心概念

Claude Code的两个配置旋钮——**模型（model）**和**Effort Level（努力级别）**——看似"让答案更好"，实际上控制的是不同维度。Model决定模型的能力范围（固定权重和整体知识），Effort决定工作的深度（读取文件数、验证步骤、多步推进程度）。**Effort不只是"思考时间"**，而是整体工作量的控制参数。

## 设计原理

### Model ≠ Effort：两个正交的调节维度

**模型选择 = 能力边界**
- 更大的模型（Claude Fable 5、Opus 4.8）在行业基准上表现更好，知识和推理能力更强
- 模型的能力是固定的（权重不变），可通过上下文和提示引导但不能提升基本能力

**Effort Level = 工作深度**
Effort控制的不只是思考时间，还包括：
- 读取多少文件
- 做多少验证（跑测试、检查结果）
- 多步任务中推进多远才回来汇报

### 选择策略

| 场景 | 模型选择 | Effort级别 |
|------|---------|-----------|
| 例行的简单任务 | 小模型（Sonnet） | 默认 |
| 复杂/模糊任务 | 大模型（Fable/Opus） | 默认 |
| Claude有完整上下文但答错 | 升级到更强大的模型 | 保持默认 |
| Claude跳过文件/未跑测试/中途放弃 | 保持模型 | **提高Effort** |

> **核心诊断原则**：如果Claude有所有相关上下文、明显努力过、仍然出错 → 选更强的模型。如果Claude跳过了文件、没跑测试、中途放弃 → 提高Effort。

### 实际建议

- 不要逐任务调整Effort，而是**基于你通常做的工作类型**设一个全局偏好
- 从默认Effort开始，逐步微调
- 调优前先问自己：问题出在能力（需要更强模型）还是工作深度（需要更高Effort）？

## 关键实现

### 模型选择的工作机制

用户按下回车时，Claude Code将以下内容打包发送给API：
- 系统提示（system prompt）
- 工具定义（tool definitions）
- CLAUDE.md（项目配置）
- 对话历史
- 上下文中的文件
- 当前用户消息

这些全部作为一次API请求发送。模型选择决定了处理这个请求的"大脑"能力上限。

### Effort Level的实践效果

| Effort级别 | 行为表现 | 最佳场景 |
|-----------|---------|---------|
| Low | 快速响应，少读文件，频繁询问确认 | 简单脚本、快速修改 |
| Medium | 平衡模式（默认） | 大多数开发任务 |
| High | 多读文件，跑测试，深入验证后才回复 | 复杂重构、跨文件变更 |
| Max | 最大工作深度，推进最远才回来汇报 | 大规模迁移、深层重构 |

## 关联分析

- 与 [Claude-Code-Source-Analysis](../../entities/Claude-Code-Source-Analysis.md) 关联：了解Claude Code的架构有助于理解Effort Level的实现机制
- 与 [learn-claude-code](../../entities/learn-claude-code.md) 关联：Effort Level是Claude Code核心配置之一
- 与 [Anthropic-AI-Code-Migration](Anthropic-AI-Code-Migration.md) 关联：大规模迁移中，模型选择可能使用Fable/Opus搭配高Effort，而routine重构可能用Sonnet+默认Effort
- Token成本优化参考 [GitHub-Token-Cost-Optimization](GitHub-Token-Cost-Optimization.md)：高Effort会增加token消耗，需要在效果和成本间权衡

## 可执行建议

1. **诊断优先于调整**：当Claude Code答错时，先判断是"能力不足"（升级模型）还是"工作没做够"（提高Effort）。这是最实用的调试技巧
2. **Effort不是万能药**：如果模型本身能力不足以理解问题，提高Effort只会浪费更多token。先选对模型再调Effort
3. **设为全局偏好**：除非某个任务特别特殊，否则不要逐任务调整Effort。找一种适合你日常工作的设置保持下去
4. **低成本试错**：简单任务用Sonnet+低Effort可以显著降低成本，将复杂任务留给Fable/Opus+高Effort

## 自评

| 维度 | 分数 | 权重 | 加权 |
|------|------|------|------|
| 摘要质量 | 8 | 0.25 | 2.00 |
| 技术深度 | 7 | 0.25 | 1.75 |
| 相关性 | 8 | 0.20 | 1.60 |
| 原创性 | 7 | 0.15 | 1.05 |
| 格式规范 | 9 | 0.15 | 1.35 |
| **加权总分** | | | **7.75** |