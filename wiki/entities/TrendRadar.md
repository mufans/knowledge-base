---
title: "TrendRadar"
category: "entities"
tags: ["AI", "Public-Opinion", "MCP", "RSS", "Monitor"]
rating: 8.0
description: "AI驱动的舆情监控与趋势追踪工具，支持多平台聚合、RSS订阅、MCP架构"
date: "2026-05-17"
---

# TrendRadar

> tags: #AI #PublicOpinion #MCP #RSS #TrendMonitor #Python
> source: [sansan0/TrendRadar](https://github.com/sansan0/TrendRadar)
> project: [TrendRadar](https://github.com/sansan0/TrendRadar)
> score: 技术深度7/10 | 实用价值9/10 | 时效性8/10 | 领域匹配7/10 | 综合 7.8/10

## 核心概念

TrendRadar 是一个 AI 驱动的舆情监控与趋势筛选工具，聚合多平台热点（微博/知乎/ Hacker News 等）+ RSS 订阅，支持关键词精准筛选、AI 智能分析简报直推手机。核心差异化是支持 MCP 架构接入，赋能 AI 自然语言对话分析、情感洞察与趋势预测。

## 设计原理

设计动机是**解决信息过载问题**：开发者和研究人员需要从海量信息源中筛选有价值的内容。TrendRadar的架构选择：

- **多平台聚合**：统一数据层覆盖社交媒体、技术社区、RSS源
- **AI 智能筛选**：不是简单关键词过滤，而是用LLM做内容理解和优先级排序
- **MCP 集成**：通过 MCP 协议暴露能力给其他AI工具，实现"用Claude/Cursor对话式分析舆情"
- **多渠道推送**：微信/飞书/钉钉/Telegram/邮件/ntfy/bark/slack 全覆盖
- **数据自主**：支持 Docker 自托管，数据本地或云端自持

Trade-off：功能全面意味着配置复杂度高，需要维护多个平台的API密钥和数据源。但自托管方案保证了数据隐私。

## 关键实现

### 技术栈
| 组件 | 技术 |
|---|---|
| 语言 | Python |
| 部署 | Docker + docker-compose |
| 数据源 | 多平台API + RSS |
| AI 能力 | 多LLM支持 |
| 推送渠道 | 微信/飞书/钉钉/Telegram/Slack/邮件/ntfy/bark |
| AI 集成 | MCP协议 |

### 核心功能
- **AI 筛选**：自然语言描述筛选条件，LLM自动判断内容相关性
- **AI 翻译**：跨语言内容自动翻译
- **AI 分析简报**：自动生成每日/每周趋势分析报告
- **MCP 接入**：通过MCP Server暴露数据给其他AI工具使用
- **关键词过滤**：精确匹配 + 语义匹配双层过滤

### ⭐指标
- GitHub Stars: 57,689
- 语言: Python

## 关联分析

- 与当前知识库采集脚本对比：TrendRadar覆盖面更广（多平台），但知识库脚本更轻量且已定制化
- MCP 集成思路与 [Anthropic-Agent-API](Anthropic-Agent-API.md) 的 MCP Connector 设计方向一致
- 与 [OpenClaw](OpenClaw.md) 的 Skill 系统可互补：TrendRadar作为信息采集MCP Server，OpenClaw作为处理和存储层

## 可执行建议

1. **参考MCP Server实现**：如果做信息采集工具，TrendRadar的MCP Server封装方式值得借鉴
2. **多平台推送架构参考**：推送层支持10+渠道的设计模式可用于自己的工具项目
3. **不建议直接替代现有采集方案**：当前知识库的Python采集脚本已定制化，迁移成本高于收益
4. **关注AI筛选模块实现**：LLM做内容理解和优先级排序的模式，可应用到自己的信息流处理

## 自评
| 维度 | 分数 | 权重 | 加权 |
|------|------|------|------|
| 摘要质量 | 8 | 0.25 | 2.00 |
| 技术深度 | 7 | 0.25 | 1.75 |
| 相关性 | 7 | 0.20 | 1.40 |
| 原创性 | 7 | 0.15 | 1.05 |
| 格式规范 | 9 | 0.15 | 1.35 |
| **加权总分** | | | **7.55** |

> 评分说明：功能覆盖完整，MCP集成有参考价值；技术深度受限于源码未深入分析；与用户信息采集场景高度相关。