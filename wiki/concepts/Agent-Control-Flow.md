---
title: "Agent控制流设计：确定性优先于Prompt"
category: "concepts"
tags: ["Agent-Architecture", "Control-Flow", "State-Machine", "LLM-Engineering"]
rating: 8.5
description: "可靠的Agent系统需要确定性控制流（状态机、校验检查点），而非更复杂的prompt链。LLM是组件而非系统本身。"
date: "2026-05-08"
---

# Agent控制流设计：确定性优先于Prompt

> tags: #Agent-Architecture #Control-Flow #State-Machine #LLM-Engineering
> source: [Agents need control flow, not more prompts](https://bsuh.bearblog.dev/agents-need-control-flow/)
> score: 技术深度9/10 | 实用价值9/10 | 时效性8/10 | 领域匹配10/10 | 综合 9.0/10

## 核心概念

当前Agent开发的核心误区：试图用越来越复杂的prompt来解决可靠性问题。正确路径是**将LLM视为决策组件，用确定性控制流（状态机、校验检查点、条件分支）编排其行为**。这一观点来自HN 388 points、202 comments的热门讨论，代表了2026年Agent工程化的共识转向。

## 设计原理

- **Trade-off分析**：纯prompt驱动的Agent（如ReAct循环）在简单场景表现良好，但面对多步骤、有副作用（写文件、发请求）的操作时，prompt的不确定性会导致不可预测的行为。确定性控制流牺牲了一定的灵活性，换取了可调试性和可预测性。
- **核心洞察**：LLM擅长理解和生成自然语言，不擅长可靠的流程控制。把两者分离——LLM做决策，确定性代码做执行和流程管理。
- **与[Weak-Model-Orchestration](Weak-Model-Orchestration.md)的呼应**：弱模型编排同样强调用代码逻辑管理LLM调用，而非依赖模型自身做流程控制。

## 关键实现

```python
# 状态机模式的Agent控制流
class AgentState(Enum):
    PLAN = "plan"
    EXECUTE = "execute"
    VALIDATE = "validate"
    RETRY = "retry"

def run_agent(task):
    state = AgentState.PLAN
    attempts = 0
    max_attempts = 3
    
    while state != AgentState.VALIDATE or not validated:
        if state == AgentState.PLAN:
            plan = llm.generate_plan(task)
            state = AgentState.EXECUTE
        elif state == AgentState.EXECUTE:
            result = execute_with_sandbox(plan)
            state = AgentState.VALIDATE
        elif state == AgentState.VALIDATE:
            validated = deterministic_check(result, task)
            if not validated and attempts < max_attempts:
                state = AgentState.RETRY
                attempts += 1
        elif state == AgentState.RETRY:
            plan = llm.refine_plan(plan, error_info)
            state = AgentState.EXECUTE
```

关键模式：
- **校验检查点**：每个关键操作后插入确定性校验，而非让LLM自己判断成功与否
- **重试边界**：硬编码最大重试次数，避免无限循环
- **沙箱执行**：副作用操作在隔离环境中执行，结果经校验后才提交

## 关联分析

- [Weak-Model-Orchestration](Weak-Model-Orchestration.md) — 用代码逻辑管理弱模型调用的编排模式
- [Vibe-Coding-Agent-Engineering-Convergence](Vibe-Coding-Agent-Engineering-Convergence.md) — Vibe Coding与Agent工程的融合趋势
- [AI-Agent沙箱方案讨论](../../sources/AI-Agent沙箱方案讨论.md) — Agent沙箱化的工程实践

## 可执行建议

1. **立即落地**：在下一个Agent项目中引入状态机模式，将LLM调用限制在"决策节点"，流程控制用纯代码实现
2. **审计现有系统**：检查当前Agent是否有"LLM判断LLM输出"的循环，替换为确定性校验
3. **参考[OpenClaw](../entities/OpenClaw.md)的实现**：OpenClaw的tool approval机制本质上就是确定性控制流在Agent中的应用

## 自评
| 维度 | 分数 | 权重 | 加权 |
|------|------|------|------|
| 摘要质量 | 9 | 0.25 | 2.25 |
| 技术深度 | 9 | 0.25 | 2.25 |
| 相关性 | 10 | 0.20 | 2.00 |
| 原创性 | 8 | 0.15 | 1.20 |
| 格式规范 | 9 | 0.15 | 1.35 |
| **加权总分** | | | **9.05** |
