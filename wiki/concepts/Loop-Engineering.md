---
title: "Loop Engineering"
category: "concepts"
tags: ["Agent", "Context", "LLM", "Prompt"]
rating: 9.0
description: "tags: #Loop-Engineering #Agent-Architecture #ReAct #Agent-Loop #Loop-Optimization"
date: "2026-07-10"
---

# Loop Engineering：AI Agent 循环系统设计

> tags: #Loop-Engineering #Agent-Architecture #ReAct #Agent-Loop #Loop-Optimization
> source: [Anthropic: Building effective agents](https://www.anthropic.com/engineering/building-effective-agents) | [LangGraph Concepts](https://langchain-ai.github.io/langgraph/concepts/high_level/) | pi-agent-ts源码分析
> score: 技术深度9/10 | 实用价值9/10 | 时效性9/10 | 领域匹配10/10 | 综合 9.0/10

## 核心概念

Loop Engineering 是 AI Agent 架构中的关键工程学科，专注于**设计、实现和优化 Agent 的迭代循环系统**。Agent 的本质是一个持续的 observe-think-act 循环，Loop Engineering 要解决的核心问题是：**如何在保证可靠性的前提下，让 LLM 高效地循环决策和行动**。

与 [Agent控制流设计](Agent-Control-Flow.md) 的确定性优先理念不同，Loop Engineering 不回避 LLM 作为循环核心的不确定性，而是通过**循环结构设计**来管理和利用这种不确定性。它关注的是"如何设计循环本身"，而非"如何用确定性代码取代循环"。

## 设计原理

### 为什么循环是 Agent 的核心

LLM 本身是"一次推理"的模型——输入 prompt，输出回答。要让 LLM 完成多步骤、涉及外部交互的任务，必须引入循环结构：

```
while not goal_met:
    observe(context)     # 感知当前状态
    think(plan)         # 推理决策
    act(tool_call)      # 执行行动
    reflect(result)     # 评估结果
```

这个基本循环是几乎所有 Agent 系统的基础。

### 循环深度与可靠性 trade-off

| 循环深度 | 优点 | 代价 | 适用场景 |
|---------|------|------|---------|
| **浅循环（1-3步）** | 延迟低、Token少、可控 | 能力受限 | 简单查询、分类路由 |
| **中循环（3-20步）** | 平衡能力与成本 | 需要错误恢复 | 代码生成、文档处理 |
| **深循环（20-200+步）** | 强大、能完成复杂任务 | 高延迟、高Token、易发散 | 自主编程、长期项目 |

**核心权衡**：循环次数增加 10 倍，Token 消耗可能增加 30-50 倍（因为每次循环都要传递上下文）。这是 [Expensively Quadratic](https://en.wikipedia.org/wiki/Expensively_quadratic) 现象在 Agent 领域的体现。

### 循环的三大设计维度

1. **结构维度**：循环的拓扑结构（线性、树形、图状）
2. **状态维度**：循环间如何传递和压缩上下文
3. **终止维度**：何时退出循环（条件判定、最大步数、超时）

## 循环架构模式

### 1. 单循环模式（ReAct）

最简单的 Agent 循环，也是基础形态：

```
Input → Think → Act → Observe → Think → Act → ... → Output
```

- **优点**：最简单、实现成本低
- **缺点**：灵活性差，一步失败全链崩溃
- **代表**：OpenAI Function Calling、早期 ReAct 实现

### 2. 双循环模式（Follow-up + Tool Call）

pi-agent 使用的经典架构：

```
外循环（Follow-up Loop）：
    ├── 生成回复/决定下一步
    └── 内循环（Tool Call Loop）：
        ├── 调用工具
        ├── 处理工具结果
        └── 决定继续/回到外循环
```

- **优点**：工具调用单独管理，外循环保持回复连贯性
- **缺点**：状态管理复杂度增加
- **代表**：pi-agent、Claude Code

### 3. 状态机循环模式

将循环视为状态机，LLM 在状态间转换：

```
[Plan] → [Execute] → [Validate] → [Plan/Retry/Exit]
```

- **优点**：确定性最强，易于调试和监控
- **缺点**：灵活性下降，需要预定义所有状态
- **代表**：[Agent控制流设计](Agent-Control-Flow.md) 模式

### 4. 图状循环模式

循环结构为有向图，LLM 决策路径选择：

```
         ┌──→ Tool A ──→ Observe ──┐
Input ──→ Think ──→ Tool B ──→     ├──→ Reflect ──→ Continue/Exit
         └──→ Tool C ──→ Observe ──┘
```

- **优点**：最灵活，支持条件分支和并行
- **缺点**：状态空间爆炸，调试困难
- **代表**：LangGraph、CrewAI

### 循环模式选择决策树

```
任务是否可分解为固定步骤？
├── 是 → 状态机循环模式
└── 否 → 是否需要工具调用？
    ├── 是 → 是否需要独立回复生成？
    │   ├── 是 → 双循环模式
    │   └── 否 → 单循环模式
    └── 否 → 是否需要条件分支/并行？
        ├── 是 → 图状循环模式
        └── 否 → 单循环模式
```

## 循环优化技术

### 1. 上下文压缩（Compaction）

深循环的核心挑战：上下文窗口膨胀。解决策略：

- **滑动窗口**：保留最近 N 轮循环，丢弃早期内容
- **摘要压缩**：把过去的循环内容摘要成一句话
- **分层存储**：近期循环保持完整，远期存为摘要
- **渐进式遗忘**：根据 relevance score 决定保留哪些历史

**参考**：pi-agent 的 compaction 机制。

### 2. 提早终止（Early Termination）

减少无效循环的关键：

- **达成条件检测**：明确的 goal check，不依赖 LLM 判断是否完成
- **N步无进展退出**：连续 N 次循环结果无变化时强制退出
- **Token预算控制**：设定最大 Token 消耗上限
- **时间预算控制**：设定最大执行时间

### 3. 错误恢复（Error Recovery）

循环中错误不可避免，需设计恢复策略：

- **重试退避**：工具调用失败时，指数退避重试
- **降级路径**：主工具失败时切换到备选方案
- **人类接管**：N 次失败后请求人工介入
- **部分结果保存**：即使循环提前终止，已完成的步骤依然有效

### 4. Token 成本优化

- **缓存中间结果**：相同输入的 LLM 调用复用缓存
- **模型分层**：简单循环用低成本模型（Flash），复杂循环用高能力模型
- **并行化无关步骤**：独立的工具调用并发执行

## 循环安全与治理

### Guardrails

- **输入验证**：每个循环步骤前检查输入合法性
- **输出审查**：每个工具调用结果检查是否安全
- **行为边界**：定义 Agent 不能进入的状态/行为

### Human-in-the-Loop

关键决策点插入人类审核：

- **高风险操作前**：文件删除、代码推送、资金操作
- **N 步后审核**：每 N 次循环展示进度供人类确认
- **异常状态介入**：循环发散或异常时自动通知人类

### 终止保障

- **硬性上限**：最大循环次数（通常 50-200）
- **软性停止**：效用递减检测（继续循环的边际收益下降时停止）
- **看门狗定时器**：超时自动停止

## 与相关概念的关系

- **[Agent控制流设计](Agent-Control-Flow.md)**：互补关系，控制流关注"要不要循环"，Loop Engineering 关注"怎么循环"
- **[Agent-Workflow-Patterns](Agent-Workflow-Patterns.md)**：Loop Engineering 包含工作流模式的循环实现
- **[Self-Evolving-Agent](Self-Evolving-Agent.md)**：自引用优化循环是 Loop Engineering 的高级形态
- **[Context-Engineering](Context-Engineering.md)**：循环中的上下文传递和压缩是 Context Engineering 的关键应用

## 可执行建议

1. **从最简单的循环开始**：先跑通单循环，再考虑双循环和状态机
2. **明确终止条件**：最常出问题的地方就是"不知道什么时候该停"
3. **错误恢复不是可选项**：没有错误恢复的循环在生产环境无法存活
4. **监控循环健康**：记录每次循环的 Token 消耗、步数、成功率
5. **渐进式优化**：先确保循环正确，再优化成本，最后优化延迟

## 自评

| 维度 | 分数 | 权重 | 加权 |
|------|------|------|------|
| 摘要质量 | 9 | 0.25 | 2.25 |
| 技术深度 | 9 | 0.25 | 2.25 |
| 相关性 | 10 | 0.20 | 2.00 |
| 原创性 | 8 | 0.15 | 1.20 |
| 格式规范 | 9 | 0.15 | 1.35 |
| **加权总分** | | | **9.05** |
