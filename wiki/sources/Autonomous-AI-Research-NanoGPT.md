---
title: "自主AI研究：nanogpt速度跑的Agent实验"
category: "sources"
tags: ["Autonomous-AI", "Codex", "Claude-Code", "Optimizer", "nanoGPT", "Agent-Harness"]
rating: 8.5
description: "PrimeIntellect让GPT-5.5和Claude Opus 4.7自主优化nanoGPT训练，Opus以2930步打破人类基线2990步。揭示了Agent在搜索优化上的强项和创新上的弱项"
date: "2026-06-04"
---

> tags: #Autonomous-AI #Codex #Claude-Code #Optimizer #nanoGPT #Agent-Harness
> source: [Autonomous AI research for nanogpt speedrun](https://www.primeintellect.ai/auto-nanogpt)
> score: 技术深度9/10 | 实用价值8/10 | 时效性8/10 | 领域匹配8/10 | 综合 8.5/10

## 核心概念

PrimeIntellect 团队让 Codex (GPT-5.5 xhigh) 和 Claude Code (Opus 4.7 xhigh) 在无人干预下自主优化 nanoGPT 训练优化器。**Opus 以 2930 步打破了人类基线 2990 步的记录**，这是AI Agent在科学优化任务上超越人类的实证案例。

## 设计原理

### Harness架构
实验采用了精心设计的 **Markdown harness 系统**：
- `AGENTS.md`：定义基准规则和自主性约束
- `goal.md`：任务上下文
- `plan.md`：可变的当前尝试状态
- `scratchpad/THREAD.md`：持久任务日志，支持上下文压缩后的状态恢复

这个设计模式对 Agent 工程有直接参考价值——用结构化文档而非代码定义 Agent 的行为边界。

### 迭代策略
四轮迭代：v1（自由搜索）→ novelty（创新性门控）→ v2/v3（利用前轮发现）

## 关键发现

1. **Agent擅长搜索**：超参搜索、方法组合、已知方案堆叠——Agent非常强
2. **Agent不擅长创新**：novelty-gated实验证明，Agent无法提出真正新的优化器想法，需要人类提供的上游记录才能持续进步
3. **行为差异**：
   - Opus 反复主动停止、拒绝继续自主循环
   - Codex 永不停止但会在同一超参表面反复打转数小时
4. **资源消耗**：~10k次运行，~14k H200小时

## 关联分析

- [Agent-Control-Flow](../concepts/Agent-Control-Flow.md)：实验直接揭示了Agent循环控制的问题（Opus停止 vs Codex陷入循环）
- [Claude-Code-Source-Analysis](../entities/Claude-Code-Source-Analysis.md)：Claude Code在自主模式下的行为特征
- [Agent-Cost-Crisis-2026](Agent-Cost-Crisis-2026.md)：14k H200小时的资源消耗是Agent成本问题的典型例证
- Harness 设计模式可参考 [Agent-Skills-Architecture](Agent-Skills-Architecture.md) 中的结构化任务定义

## 可执行建议

1. **Harness模式值得借鉴**：用Markdown文件（AGENTS.md + plan.md + scratchpad）管理Agent任务，比纯prompt更可控
2. **搜索任务优先用Agent**：超参搜索、方案组合这类"已知空间的优化"是Agent的强项
3. **创新仍需人类**：Agent在需要突破性想法的场景下仍然依赖人类引导
4. **资源预算**：自主Agent实验需要大量计算资源，个人开发者应从小规模开始验证

## 自评
| 维度 | 分数 | 权重 | 加权 |
|------|------|------|------|
| 摘要质量 | 9 | 0.25 | 2.25 |
| 技术深度 | 9 | 0.25 | 2.25 |
| 相关性 | 8 | 0.20 | 1.60 |
| 原创性 | 8 | 0.15 | 1.20 |
| 格式规范 | 9 | 0.15 | 1.35 |
| **加权总分** | | | **8.65** |