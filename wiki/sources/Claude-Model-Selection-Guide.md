---
title: "Claude模型选择指南：Mythos/Fable/Opus/Sonnet/Haiku选型策略"
category: "sources"
tags: ["Claude", "Model-Selection", "Effort-Level", "Cost-Optimization", "Anthropic"]
rating: 9.0
description: "Anthropic官方Claude模型选择指南，涵盖Mythos/Fable/Opus/Sonnet/Haiku五类模型及Effort Level调优策略，以实际案例说明如何平衡质量、速度和成本"
date: "2026-07-25"
---

# Claude模型选择指南：Mythos/Fable/Opus/Sonnet/Haiku选型策略

> tags: #Claude #Model-Selection #Effort-Level #Cost-Optimization #Anthropic
> source: [Claude Blog - Claude models explained](https://claude.com/blog/claude-models-explained-choosing-the-best-model-for-your-use-case) | [raw/inbox/2026-07-25-Claude博客.md](../../raw/inbox/2026-07-25-Claude博客.md)
> score: 技术深度9/10 | 实用价值9/10 | 时效性8/10 | 领域匹配8/10 | 综合 8.5/10

## 核心概念

Anthropic官方发布的模型选择指南，系统介绍了Claude五类模型（Mythos、Fable、Opus、Sonnet、Haiku）的定位、差异化和选型策略。核心建议：**先以最强模型+低Effort Level起步，用实际效果决定是否降级**，而非先选便宜模型试探。因为单任务成本（cost-per-task）往往比单token成本（cost-per-token）更能反映真实经济性——更强模型用更少token和轮次完成任务。

## 设计原理

### 模型家族定位

| 模型 | 定位 | 适用场景 |
|------|------|---------|
| **Mythos** | 最强前沿（双轨制） | 双用网络安全/生物领域（受Project Glasswing限制），仅限受信任组织 |
| **Fable 5** | 公众版前沿 | 与Mythos同底层模型但加入额外安全防护，编码/长Agent/未解决难题 |
| **Opus** | 企业推理 | 推理密集型任务，GDPval-AA/Terminal-Bench 2.1领先，平衡性能与安全 |
| **Sonnet** | 通用全能 | 日常任务主模型，适合高吞吐sub-agent场景，性价比最佳 |
| **Haiku** | 低成本快速 | 高频率、低延迟需求的任务，如分类/提取/简单查询 |

### 关键设计观察

**Fable vs Opus 的选择模糊地带**：两者在编码、长Agent和知识工作上表现都强。实际经验表明——更大的模型（Fable）往往有更多"隐性智慧"（wisdom）、创造力和写作能力，即使benchmark分数相似。规则：Opus能达标就用Opus（更快更便宜），Opus吃力就上Fable。

**Effort Level 的杠杆效应**：Effort Level（推理投入级别）是影响质量、速度和成本的核心杠杆：
- 高强度Effort + 高级模型 = 最优性能
- 低强度Effort + 高级模型 > 高强度Effort + 低级模型（多数场景）
- 可动态调整，不改变模型本身

**"先大后小"策略**：官方推荐先用最强模型测试——如果当前任务简单，最强模型也能快速完成（低Effort模式），且更容易区分"模型能力不够"还是"配置不对"。

## 关键数据

### 选择决策树

1. **任务难度**：花时间多、多步骤、未解决→用更强模型
2. **延迟需求**：高频客户交互→Sonnet
3. **访问限制**：Mythos仅Project Glasswing开放
4. **单位经济学**：高产量→低成本模型+evals验证
5. **Effort Level调优**：先用中等Effort，根据质量决定升降

### 关键洞察

- **cost-per-task 常低于 cost-per-token 的直觉**：更强模型少走弯路，总token更少
- **降级试探陷阱**：从小模型开始可能导致"模型失败vs配置失败"难以区分
- **模型不是垂直专业化的**：Claude的模型不分区金融/科学/编程，而是按"问题的复杂度"分档

## 关联分析

- **[Claude-Fable-5](../entities/Claude-Fable-5.md)**：Fable 5作为多模型策略中的"最强公共模型"，掌握其能力边界和成本特征才能做好选型决策
- **[GPT-5.6](../entities/GPT-5.6.md)**：GPT-5.6的Sol/Terra/Luna分级与Claude的Fable/Opus/Sonnet形成对标，但Effort Level的设计哲学不同——Claude是自动调节，GPT-5.6是用户手动选择
- **[Context-Window-Optimization](../concepts/Context-Window-Optimization.md)**：模型选择需要考虑Context Window需求——不同模型对长上下文的处理能力差异显著

## 可执行建议

1. **立即测试"先大后小"策略**：在现有Agent流程中，先用最强模型+低Effort跑典型任务，记录耗时和token消耗；如果达标，这就是你的最优配置
2. **sub-agent选型**：vibe coding中高频调用的子Agent用Sonnet（性价比最优），高难度独立任务用Fable 5
3. **Effort Level调优实验**：针对固定任务集，测试不同Effort Level下的cost-per-task曲线，找到拐点（diminishing returns）
4. **建立模型选型评估表**：对每个关键任务，记录"模型+Effort→质量/成本/延迟"，形成可复用的决策矩阵

## 自评

| 维度 | 分数 | 权重 | 加权 |
|------|------|------|------|
| 摘要质量 | 9 | 0.25 | 2.25 |
| 技术深度 | 9 | 0.25 | 2.25 |
| 相关性 | 8 | 0.20 | 1.60 |
| 原创性 | 8 | 0.15 | 1.20 |
| 格式规范 | 9 | 0.15 | 1.35 |
| **加权总分** | | | **8.65** |