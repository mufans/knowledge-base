---
title: "Claude Fable 5"
category: "entities"
tags: ["Claude", "GitHub", "开源项目"]
rating: 9.0
description: "Anthropic前沿推理模型，采用自适应推理机制自动调整推理深度，在Cursor和Cognition企业场景验证为可无人值守运行的编码Agent"
date: "2026-07-25"
---

# Claude Fable 5：Anthropic 前沿推理模型

> tags: #Claude-Fable-5 #Anthropic #Adaptive-Reasoning #Max-Effort #Frontier-Model
> source: [Artificial Analysis](https://artificialanalysis.ai/models/claude-fable-5) | [OpenAI GPT-5.6发布引用](https://openai.com/index/gpt-5-6/)
> project: [Anthropic](https://www.anthropic.com)
> score: 技术深度8/10 | 实用价值9/10 | 时效性9/10 | 领域匹配9/10 | 综合 8.75/10

## 核心概念

Claude Fable 5 是 Anthropic 于 2026 年 6 月发布的前沿大语言模型，在 Artificial Analysis Intelligence Index 上排名 **#1/186**。其核心特色是 **Adaptive Reasoning（自适应推理）**——模型根据任务复杂度自动调整推理深度，在简单问题上快速响应，在复杂问题上投入更多计算。

## 设计原理

### Adaptive Reasoning 机制

Fable 5 采用了一种混合推理策略：
- **简单问题**：快速直出，节省 token 和延迟
- **困难问题**：自动激活深度推理链，投入更多计算
- **中间状态**：介于两者之间，根据置信度动态调整

这与 GPT-5.6 的 `medium→ultra` 手动选择的思路形成对比——Fable 5 是自动调节，GPT-5.6 是用户手动选择投入级别。

### Max Effort 模式

Fable 5 还提供 **Max Effort** 模式，用于应对极端困难的任务。在这个模式下，模型可以进行更长时间的推理、多次尝试和自我修正。

### Opus 4.8 Fallback

Fable 5 配备 Opus 4.8 作为备选方案，当自适应推理不确定或任务类型更适合时，可以回退到 Opus 4.8 的输出风格。

## 关键数据

### 价格

| 指标 | 数值 |
|------|------|
| 输入价格 | $10.00/1M tokens |
| 输出价格 | $50.00/1M tokens |
| Cache 写入 | $12.50/1M tokens |
| Cache 命中 | $1.00/1M tokens (-90%) |
| 输出速度 | 2.9 tokens/s |
| AI Index 排名 | #1/18660 |

### 与 GPT-5.6 Sol 对比

| 维度 | Fable 5 | GPT-5.6 Sol |
|------|---------|-------------|
| AA Intelligence Index | #1 | 接近 #1 |
| Coding Agent Index | 77.2 | **80** (领先2.8分) |
| Agent' Last Exam | 40.5 | **53.6** (+13.1) |
| 成本 | 基准 | **~1/2** (同等或更强结果) |
| 推理模式 | 自适应(自动) | 分级可调(手动) |
| 发布月份 | 2026-06 | 2026-07 |

### 2026-07-23 更新：Jacobian 猜想反例与数学推理突破

Claude Fable 在 2026 年 7 月给出了 Jacobian 猜想的反例——数学界数十年未解的难题。菲尔兹奖得主陶哲轩（Terence Tao）随后使用 ChatGPT 深入分析验证了这一结果。

**事件意义**：
- Fable 5 展示了超越语言模型的数学推理能力——不仅是"计算"，而是"发现"和"证明"
- 陶哲轩使用 ChatGPT 验证结果，标志着 AI 辅助数学研究的实际落地
- 与 [GPT-5.6](GPT-5.6.md) 的 Agent 编程和代码生成能力形成对比：不同模型在"智能"的侧重点上各有长短，Fable 在数学/科学推理上有独特优势

### 2026-07-25 更新：Cursor与Cognition的企业级信任验证

两大AI编程工具厂商在Claude Blog上分享了Fable 5在生产环境中的信任验证结果：

**Cursor（Nate Schmidt，模型评估负责人）**：Nate的工作就是评估前沿模型处理长期、真实工程问题的能力。Cursor为Fable 5设计了CoderBench，专门测试模型在长耗时（多轮次）复杂编码任务上的表现。Fable 5在CoderBench上达成绩效基准，扩展了Cursor对Agentic coding的能力边界。核心信号：**Fable 5能够处理最难的1%编码问题**。

**Cognition Devin（Silas Alberti，研究SVP）**：Silas在Devin（Cognition的AI软件工程师产品）中测试了几乎所有Claude模型，**Fable 5是第一个他愿意留下运行一整夜（8小时无人值守）并交付生产级代码的模型**。这意味着Fable 5在长时间自主运行的可靠性上达到了质变——经过验证可以信任模型独立完成复杂工程任务。

**事件意义**：
- Fable 5的可靠性已通过两个顶级AI编程产品（Cursor和Devin）的生产验证
- 从"需要人工监督"到"可无人值守"——这是Agent可靠性的一个关键门槛突破
- 与Sol在编程bench上的领先形成互补：Sol在评估指标上领先，Fable 5在长时间自主运行的稳定性上得到业界验证

## 关联分析

- **[GPT-5.6](GPT-5.6.md)**：直接竞品，Anthropic 与 OpenAI 的最新旗舰对决
- **Adaptive Reasoning vs 分级推理**：两种设计哲学——自动 vs 手动，各有优劣
- Fable 5 在 AI Index 排名 #1 但被 Sol 在多个具体 bench 上超越，说明"综合排名"不代表"所有场景最优"
- **CursorBench vs Terminal-Bench**：不同评测环境的设计差异反映了Agent能力评估的碎片化问题——"在哪个bench上赢"比"赢了多少分"更重要

## 可执行建议

1. **Fable 5 在综合推理上仍然是 SOTA**，特别是需要自适应深度推理的复杂知识工作场景
2. **成本考量**：Sol 在代码生成场景下成本优势明显（约 1/3），纯编程任务优先考虑 Sol
3. **关注后续迭代**：Anthropic 可能很快推出竞品响应版本，保持关注

## 自评

| 维度 | 分数 | 权重 | 加权 |
|------|------|------|------|
| 摘要质量 | 8 | 0.25 | 2.00 |
| 技术深度 | 8 | 0.25 | 2.00 |
| 相关性 | 9 | 0.20 | 1.80 |
| 原创性 | 8 | 0.15 | 1.20 |
| 格式规范 | 9 | 0.15 | 1.35 |
| **加权总分** | | | **8.35** |