---
title: "nanobot"
category: "entities"
tags: ["GitHub", "工具", "框架"]
rating: 7.5
description: "tags: #AI-Agent #Lightweight #Multi-LLM"
date: "2026-05-07"
---

# nanobot

> tags: #AI-Agent #Lightweight #Multi-LLM #MCP #MultiChannel
> source: [HKUDS/nanobot](https://github.com/HKUDS/nanobot)
> score: 技术深度7/10 | 实用价值9/10 | 时效性9/10 | 领域匹配8/10 | 综合 8.25/10

## 核心概念

nanobot 是港大数据科学实验室（HKUDS）开源的超轻量个人 AI Agent 框架，基于 Python，支持多 LLM 后端（OpenAI、Claude、Gemini、本地模型等）。它以极低的启动成本提供完整的 Agent 能力——对话、工具调用、文件操作、代码执行，41K+ stars 证明其社区认可度。定位类似OpenClaw/Claude Code/Codex，但保持核心Agent loop精简可读。

## 设计原理

**核心 trade-off**：nanobot 选择"够用就好"的极简路线，而非追求 LangChain/CrewAI 那样的全功能框架。好处是学习曲线低、依赖少、易于定制；代价是缺少高级编排能力（如多 Agent 协作、复杂 workflow）。

**插件式架构**：核心只提供对话循环和工具调度，具体能力通过插件扩展。这让用户可以按需加载，避免引入不需要的依赖。

**本地优先**：支持完全本地运行（Ollama、vLLM），不依赖云端 API。这对数据敏感场景和成本控制很重要。

### 2026-05-16 更新：密集迭代（v0.1.5.post3）

nanobot保持每日迭代节奏，近一个月的重要更新：
- **v0.1.5 (2026-04-05)**：Dream两阶段记忆、生产级沙箱、Programming Agent SDK
- **v0.1.5.post1 (2026-04-14)**：Dream skill发现、mid-turn follow-up注入、WebSocket channel
- **v0.1.5.post2 (2026-04-21)**：Windows & Python 3.14支持、Office文档阅读、SSE streaming
- **v0.1.5.post3 (2026-04-29)**：更智能的线程处理（Feishu/Discord/Slack/Teams）、DeepSeek-V4支持、Hugging Face & Olostep集成
- **新功能**：WebUI聊天界面、`/goal`长期目标追踪、Streaming reasoning、NVIDIA NIM支持、LM Studio集成、MCP多服务器、Dream记忆蒸馏、Context自动压缩

## 关键实现

- **多 LLM 统一接口**：通过 adapter 模式统一不同 LLM 的 API 调用，切换模型只需改配置
- **工具系统**：内置文件读写、代码执行、搜索等基础工具，支持自定义工具注册
- **配置驱动**：通过 YAML 配置文件定义 Agent 行为、可用工具、系统提示等
- **终端 + Web UI**：提供 TUI 和 Web 两种交互界面
- **多Channel支持**（新增）：Discord/Telegram/Feishu/WhatsApp/WeChat/Slack/MSTeams/QQ
- **Dream记忆**（新增）：两阶段记忆系统——短期记忆 + 梦境蒸馏，类似人类睡眠整理记忆
- **MCP多服务器**（新增）：支持同时连接多个MCP服务器
- **Context自动压缩**（新增）：session过长时自动compact，保持活跃任务不被截断

## 关联分析

- [mem0](mem0.md) — Agent 记忆层，nanobot的Dream记忆是另一种实现思路
- [pi-mono](pi-mono.md) — 另一个轻量 Agent 工具包，TypeScript 实现
- [OpenClaw](OpenClaw.md) — 类似定位的全功能Agent框架，nanobot更轻量
- [CowAgent](CowAgent.md) — 同为中国开发者的Agent框架，CowAgent更侧重多平台IM

## 可执行建议

1. **快速原型验证**：如果你想快速验证一个 Agent 想法（如自动化某个工作流），nanobot 的启动成本比 LangChain 低得多
2. **学习参考**：代码库相对精简，适合阅读学习 Agent 的核心实现模式（对话循环、工具调度、上下文管理）
3. **本地部署方案**：结合 Ollama 可以实现完全本地的 Agent，适合隐私敏感场景
4. **Dream记忆机制**：值得关注其"梦境蒸馏"的Memory设计——定期从短期记忆中提炼长期知识

## 自评
| 维度 | 分数 | 权重 | 加权 |
|------|------|------|------|
| 摘要质量 | 7.5 | 0.25 | 1.88 |
| 技术深度 | 7.5 | 0.25 | 1.88 |
| 相关性 | 8.5 | 0.20 | 1.70 |
| 原创性 | 7.5 | 0.15 | 1.13 |
| 格式规范 | 9.0 | 0.15 | 1.35 |
| **加权总分** | | | **7.93** |

> 评分依据：迭代速度极快，功能覆盖面已接近OpenClaw级别。Dream记忆和Context自动压缩是有特色的技术点。