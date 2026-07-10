---
title: "Stork - MCP 服务器搜索"
category: "entities"
tags: ["MCP", "Search", "Agent-Tool", "Discovery"]
rating: 8.0
description: "MCP服务器搜索引擎，可搜索 14000+ MCP 服务器和 AI 工具"
date: "2026-05-17"
---

# Stork - MCP 服务器搜索

> tags: #MCP #SearchEngine #AgentTools #ToolDiscovery #MCP-Server
> source: [Stork](https://www.stork.ai)
> score: 技术深度7/10 | 实用价值8/10 | 时效性8/10 | 领域匹配8/10 | 综合 7.8/10

## 核心概念

Stork 是一个 MCP 服务器，为 Claude/Cursor 等 AI 工具提供 14,000+ MCP 服务器和 AI 工具的搜索能力。本质上是"MCP生态的应用商店"——通过MCP协议暴露搜索接口，让AI Agent能自主发现和使用外部工具。

## 设计原理

设计动机是**解决MCP生态的工具发现问题**：

- **14,000+ MCP服务器**：MCP生态爆发式增长后，开发者面临"有哪些MCP工具可用"的信息过载问题
- **MCP即服务**：Stork本身就是一个MCP Server，AI工具通过MCP协议直接调用搜索功能
- **Agent自主发现**：Agent可以在运行时搜索并决定使用哪些工具，而不需要人工预先配置

Trade-off：依赖外部搜索服务意味着网络依赖和可用性风险。但对MCP生态的健康发展至关重要——没有发现机制的生态会碎片化。

## 关键实现

### 核心特征
| 特征 | 值 |
|---|---|
| 类型 | MCP Server |
| 数据量 | 14,000+ MCP服务器和AI工具 |
| 接入方式 | MCP协议 |
| 支持客户端 | Claude、Cursor等MCP兼容工具 |
| 官网 | [stork.ai](https://www.stork.ai) |

### 工作模式
1. AI工具（如Claude）通过MCP协议连接Stork
2. 用自然语言描述需求（"我需要一个能操作数据库的MCP工具"）
3. Stork返回匹配的MCP服务器列表和配置信息
4. AI工具自动连接选中的MCP服务器

## 关联分析

- 与 [Anthropic-Agent-API](Anthropic-Agent-API.md) 的MCP Connector互补：Stork解决"发现"，MCP Connector解决"连接"
- MCP生态爆发印证了 [Claude-Ecosystem-Tools](../concepts/Claude-Ecosystem-Tools.md) 中对MCP趋势的判断
- 14,000+ MCP服务器说明MCP已成为事实上的工具协议标准

## 可执行建议

1. **接入Stork扩展Agent能力**：如果构建自己的Agent工具，可以通过Stork MCP Server自动发现可用工具
2. **跟踪MCP生态趋势**：14,000+服务器的规模说明MCP生态已进入爆发期，值得持续关注
3. **参考Stork的搜索设计**：如果做自己的工具发现平台，Stork的分类和搜索方式可借鉴

## 自评
| 维度 | 分数 | 权重 | 加权 |
|------|------|------|------|
| 摘要质量 | 7 | 0.25 | 1.75 |
| 技术深度 | 7 | 0.25 | 1.75 |
| 相关性 | 8 | 0.20 | 1.60 |
| 原创性 | 7 | 0.15 | 1.05 |
| 格式规范 | 8 | 0.15 | 1.20 |
| **加权总分** | | | **7.35** |

> 评分说明：MCP生态的关键基础设施；工具发现机制有实用价值；信息源有限（Show HN帖子），技术深度受限。