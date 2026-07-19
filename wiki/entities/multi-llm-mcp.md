---
title: "multi-llm-mcp — 多LLM调用的MCP工具"
category: "entities"
tags: ["MCP", "multi-LLM", "Claude-Code", "Codex", "Agent-orchestration"]
rating: 9.0
date: "2026-06-04"
description: "MCP Server让Claude Code调用Codex执行任务，支持多模型统一调度"
---

# multi-llm-mcp — 多LLM调用的MCP工具

> tags: #MCP #multi-LLM #Claude-Code #Codex #Agent-orchestration
> source: [mai-yyy/multi-llm-mcp](https://github.com/mai-yyy/multi-llm-mcp)
> score: 技术深度7/10 | 实用价值8/10 | 时效性8/10 | 领域匹配8/10 | 综合7.8/10

## 核心概念

一个MCP Server，让Claude Code能够调用Codex执行任务，同时支持调用多个LLM模型。Python实现，核心思路是将多个LLM provider封装为统一MCP工具接口，实现跨模型任务分发和协作。

## 设计原理

### 单一Agent调用多LLM的痛点

当前主流AI编程工具（Claude Code、Codex、OpenCode等）各自绑定单一模型。实际开发中不同任务适合不同模型：
- **Claude Opus/Sonnet**：适合复杂推理和长上下文理解
- **Codex/GPT-4o**：适合代码生成和补全
- **Gemini**：适合长文档处理和搜索增强

multi-llm-mcp通过MCP协议将多模型调用抽象为统一工具，让Claude Code作为"主Agent"按需调度其他模型。

### MCP作为多模型桥梁

利用MCP的标准tool-call机制：
- 定义统一的`call_llm`工具接口
- 参数包含目标模型、prompt、temperature等
- Claude Code通过tool_use调用其他模型，获取结果后在本地上下文中整合

## 关键实现

- **语言**：Python
- **Star**：34（早期项目，但思路有参考价值）
- **核心功能**：
  - 将多个LLM封装为MCP tool
  - 支持Claude Code作为主Agent调用Codex
  - 统一的tool-call接口，模型切换透明

### 使用场景示例

```python
# Claude Code通过MCP调用Codex生成代码
# tool_use: call_llm(model="codex", prompt="实现xxx函数")
# 然后在本地审查、修改生成的代码
```

## 关联分析

- 与 [Claude-Code-Subagents-Guide](Claude-Code-Subagents-Guide.md) 互补——subagent是进程级多Agent协作，multi-llm-mcp是tool-call级多模型协作
- 与 [MCP-Tunnel](MCP-Tunnel.md) 相关——MCP传输层的选择影响多模型调用的延迟
- 与 [Multi-Agent-Systems-Design](Multi-Agent-Systems-Design.md) 相关——多LLM调度是多Agent架构的一种简化实现
- 与 [MCP-Tool-Development-Best-Practices](MCP-Tool-Development-Best-Practices.md) 相关——MCP工具开发的具体案例

## 可执行建议

1. **在Agent项目中考虑多模型策略**：不要绑定单一模型，用MCP抽象多模型调用接口，根据任务类型选择最优模型
2. **成本优化思路**：简单任务用便宜模型（Haiku/GPT-4o-mini），复杂推理用贵模型（Opus/GPT-5.5），通过MCP统一调度
3. **参考其架构设计**：即使不直接使用，"MCP工具封装多模型"的思路值得在自建Agent工具中借鉴

## 自评
| 维度 | 分数 | 权重 | 加权 |
|------|------|------|------|
| 摘要质量 | 7 | 0.25 | 1.75 |
| 技术深度 | 7 | 0.25 | 1.75 |
| 相关性 | 8 | 0.20 | 1.60 |
| 原创性 | 7 | 0.15 | 1.05 |
| 格式规范 | 9 | 0.15 | 1.35 |
| **加权总分** | | | **7.50** |

> 评分标准：摘要质量（MCP统一工具+多模型调度思路）| 技术深度（架构设计+使用场景）| 相关性（MCP+Agent开发直接相关）| 原创性（多模型成本优化建议）| 格式规范（完整标签链接评分）