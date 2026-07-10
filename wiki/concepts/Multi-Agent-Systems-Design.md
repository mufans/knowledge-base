---
title: "Multi-Agent系统设计：何时与如何使用"
category: "concepts"
tags: ["Multi-Agent", "Agent-Architecture", "Context-Engineering", "Subagent-Pattern"]
rating: 8.0
description: "Anthropic官方总结的多Agent系统设计指南：三种真正需要多Agent的场景（上下文隔离、并行化、专业化），以及context-centric分解原则"
date: "2026-05-18"
---

# Multi-Agent系统设计：何时与如何使用

> tags: #Multi-Agent #Agent-Architecture #Context-Engineering #Subagent-Pattern
> source: [Building multi-agent systems](https://claude.com/blog/building-multi-agent-systems-when-and-how-to-use-them)
> score: 技术深度9/10 | 实用价值9/10 | 时效性9/10 | 领域匹配9/10 | 综合 9.0/10

## 核心概念

Anthropic基于自身和客户的多Agent生产部署经验，总结出**大多数团队不需要多Agent系统**。多Agent系统仅在三种场景下 consistently 优于单Agent：**上下文污染**导致性能退化、任务可**并行化**、**专业化**提升工具选择或任务聚焦。核心模式是 **orchestrator-subagent**（编排者-子Agent）层级结构。

## 设计原理

### 单Agent优先原则

多Agent系统的开销是实质性的：
- **Token成本**：多Agent实现通常消耗 **3-10x** 更多token（上下文复制 + 协调消息 + 结果摘要）
- **维护负担**：每个Agent是额外的故障点、需要维护的prompt集合
- **上下文丢失**：Agent间切换时丢失context，类似"传话游戏"的退化

Anthropic观察到有团队花数月构建复杂多Agent架构，最终发现改进单Agent的prompting就能达到同等效果。

### 三种需要多Agent的场景

**1. Context Protection（上下文隔离）**
当子任务产生大量无关上下文（>1000 tokens）污染主任务时。例如：客服Agent需要查订单历史（2000+ tokens）的同时诊断技术问题。解决方案：子Agent处理完整数据，仅返回摘要（50-100 tokens）给主Agent。

```python
# 关键模式：子Agent返回摘要而非完整数据
order_summary = OrderLookupAgent().lookup_order(order_id)
# 主Agent只接收精简信息
context = f"Order {order_id}: {order_summary['status']}, purchased {order_summary['date']}"
```

**2. Parallelization（并行化）**
探索比单Agent更大的搜索空间。Anthropic自己的Research功能就用此模式。关键认知：**并行化的收益是全面性（thoroughness），不是速度**——多Agent总执行时间往往更长，但覆盖面更广。

```python
# 并行研究模式
facets = await lead_agent.decompose_query(query)
tasks = [research_subagent(facet) for facet in facets]
results = await asyncio.gather(*tasks)
return await lead_agent.synthesize(results)
```

**3. Specialization（专业化）**
- **工具集专业化**：Agent有20+工具时性能下降，按域拆分（CRM 8-10个工具 + Marketing 8-10个工具）
- **System prompt专业化**：冲突的行为模式需要分离（客服需要共情 vs 代码审查需要精确）
- **领域知识专业化**：法律分析、医学研究等需要大量域上下文

### Context-Centric分解（核心洞察）

**❌ Problem-centric（常反效果）**：按工作类型分（一个写功能、一个写测试、一个审查）→ 每次交接丢失context
**✅ Context-centric（通常有效）**：按上下文边界分（处理功能的Agent也负责其测试，因为它已有相关context）

> 只有当context可以真正隔离时，才应该拆分工作。

### 判断单Agent已不够用的信号

1. **接近context限制**：Agent常用大量context且性能退化（但compaction技术正在缓解）
2. **管理太多工具**：15-20+工具时，考虑先尝试 [Tool Search Tool](../concepts/Client-Side-Tool-Calling.md)（可减少85% token用量）
3. **可并行子任务**：自然分解为独立部分时

### 2026-05-30 更新：五种协调模式详解

Anthropic在后续博客《[Multi-agent coordination patterns](https://claude.com/blog/multi-agent-coordination-patterns)》中，进一步将多Agent协调细化为**五种具体模式**，并给出演进路径建议：

| 模式 | 适用场景 | 复杂度 | 关键权衡 |
|------|---------|--------|----------|
| **Generator-Verifier** | 质量关键输出+明确评估标准 | ★☆☆ | 最简模式，增加一次LLM调用但显著提升输出质量 |
| **Orchestrator-Subagent** | 清晰任务分解+有界子任务 | ★★☆ | 与上文核心模式一致，适合大多数场景 |
| **Agent Teams** | 并行独立长时间子任务 | ★★☆ | 需要结果合并策略，避免信息丢失 |
| **Message Bus** | 事件驱动管道+增长Agent生态 | ★★★ | 异步解耦，但调试复杂度高 |
| **Shared-State** | 协作式工作+Agent互建发现 | ★★★ | 最灵活但并发控制最难 |

**核心建议**：从最简单的Generator-Verifier或Orchestrator-Subagent开始，观察痛点后逐步演进。不要因为"听起来高级"就选复杂方案。

与上文"三种场景"的映射：Generator-Verifier ≈ 专业化（验证角色）；Orchestrator-Subagent = 核心编排模式；Agent Teams ≈ 并行化；Message Bus/Shared-State 是更高级的架构选择。

## 关联分析

- [Agent-Control-Flow](Agent-Control-Flow.md) — 单Agent流程控制模式
- [Context-Window-Optimization](Context-Window-Optimization.md) — 上下文管理策略
- [AI-Memory-Systems](AI-Memory-Systems.md) — Agent记忆系统设计
- [Claude-Code-Source-Analysis](../entities/Claude-Code-Source-Analysis.md) — Claude Code的子Agent实现
- [everything-claude-code](../entities/everything-claude-code.md) — Claude Code实践指南

## 可执行建议

1. **先优化单Agent**：遇到问题先尝试改进prompting、增加context compaction、使用Tool Search Tool
2. **按场景选择模式**：上下文隔离用subagent摘要；研究任务用并行搜索；多工具场景按域拆分
3. **遵循context-centric分解**：不要按工作类型分Agent，按上下文边界分
4. **预算3-10x token开销**：多Agent系统成本显著更高，确保ROI值得
5. **设计好handoff机制**：Agent间传递信息时，确保传递的是精炼摘要而非原始数据

## 自评

| 维度 | 分数 | 权重 | 加权 |
|------|------|------|------|
| 摘要质量 | 9 | 0.25 | 2.25 |
| 技术深度 | 9 | 0.25 | 2.25 |
| 相关性 | 10 | 0.20 | 2.00 |
| 原创性 | 8 | 0.15 | 1.20 |
| 格式规范 | 9 | 0.15 | 1.35 |
| **加权总分** | | | **9.05** |