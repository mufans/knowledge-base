---
title: "MCP 工具开发最佳实践"
category: "sources"
tags: ["MCP", "Tool-Development", "Agent", "Best-Practice"]
rating: 7.5
description: "MCP工具开发实践经验：Agent每次读工具输出但工具描述只读一次"
date: "2026-05-17"
---

# MCP 工具开发最佳实践

> tags: #MCP #ToolDevelopment #AgentEngineering #BestPractice #ToolDescription
> source: [Building MCP tools: AI agents read outputs every time, tool descriptions once](https://aleahim.com/blog/cupertino-04-release/)
> score: 技术深度7/10 | 实用价值9/10 | 时效性8/10 | 领域匹配9/10 | 综合 8.3/10

## 核心概念

文章提出一个关键的MCP工具开发洞察：**Agent每次调用工具时都会读取工具输出（tool output），但工具描述（tool description）只在首次发现时读取一次**。这个看似简单的观察，对MCP工具的设计有深远影响。

## 设计原理

### 工具描述 vs 工具输出的不对称性

| 维度 | 工具描述 | 工具输出 |
|---|---|---|
| 读取频率 | 首次发现时读一次 | 每次调用都读 |
| Token消耗 | 固定（注册时一次性） | 可变（每次调用） |
| 影响范围 | Agent是否选择该工具 | Agent如何使用结果 |
| 优化重点 | 清晰、精确、包含决策信息 | 结构化、信息密度高 |

### 对MCP工具设计的启示

1. **工具描述要精确到足以让Agent做出正确决策**：因为描述只读一次，必须包含所有Agent需要的信息来决定"何时用"和"怎么用"
2. **工具输出要结构化且信息密度高**：因为每次调用都消耗token读取输出，冗余输出是纯浪费
3. **输出格式要可预测**：Agent依赖输出格式来解析信息，不一致的格式会导致错误推理

## 关键实现

### MCP工具描述优化建议
```
好的描述：
"搜索指定GitHub仓库的issues。返回匹配issue的标题、状态、标签和URL。
参数：repo（格式：owner/name）、query（搜索关键词）、state（open/closed/all）"

差的描述：
"搜索GitHub issues"（太模糊，Agent无法判断何时使用和如何传参）
```

### MCP工具输出优化建议
- 使用结构化格式（JSON）而非自由文本
- 包含Agent需要的所有信息，避免二次查询
- 截断过长内容，提供摘要而非全文
- 包含元数据（总数、是否截断、相关度等）

## 关联分析

- 与 [Claude-Code-Source-Analysis](../entities/Claude-Code-Source-Analysis.md) 中Tool System的分析一致：Claude Code的 `maxResultSizeChars` 就是在控制工具输出大小
- 与 [Anthropic-Agent-API](../entities/Anthropic-Agent-API.md) 的MCP Connector相关：API层自动处理工具发现，工具描述质量直接影响Agent的工具选择效果
- 与 [Context-Window-Optimization](Context-Window-Optimization.md) 相关：工具输出优化本质上是上下文窗口优化的一部分

## 可执行建议

1. **审查自己的MCP工具描述**：确保描述精确、完整，Agent能仅凭描述做出正确的工具选择
2. **优化工具输出格式**：结构化JSON > 自由文本，信息密度高 > 冗余描述
3. **设置输出大小限制**：参考Claude Code的 `maxResultSizeChars`，防止工具输出撑爆上下文
4. **测试Agent的工具选择准确性**：如果Agent经常选错工具，问题很可能出在描述不够精确

## 自评
| 维度 | 分数 | 权重 | 加权 |
|------|------|------|------|
| 摘要质量 | 8 | 0.25 | 2.00 |
| 技术深度 | 7 | 0.25 | 1.75 |
| 相关性 | 9 | 0.20 | 1.80 |
| 原创性 | 7 | 0.15 | 1.05 |
| 格式规范 | 8 | 0.15 | 1.20 |
| **加权总分** | | | **7.80** |

> 评分说明：工具描述vs输出的不对称性洞察有实用价值；MCP工具开发实践与用户Agent开发方向高度匹配；可执行建议具体可落地。