---
title: "fabrica"
category: "entities"
tags: ["GitHub", "工具", "框架", "终端"]
rating: 6.5
description: "tags: #Coding-Agent #Terminal #Minimal #Vibe-Coding"
date: "2026-05-07"
---

# fabrica

> tags: #Coding-Agent #Terminal #Minimal #Vibe-Coding
> source: [fabrica](https://github.com/Endi1/fabrica)
> score: 技术深度7/10 | 实用价值7/10 | 时效性8/10 | 领域匹配8/10 | 综合 7.45/10

## 核心概念

fabrica 是一个基于终端的极简编码 Agent harness，强调最小化设计和轻量级集成。它提供编码 Agent 的核心骨架（LLM 对话循环、文件操作、终端命令执行），让开发者可以快速搭建自己的编码助手，而不被复杂框架绑死。

## 设计原理

**核心 trade-off**：选择"只提供骨架"而非"全功能 IDE"，好处是灵活度极高，可以自由选择 LLM 后端和工具集；代价是需要自己补充很多功能（如 diff 预览、git 集成、上下文管理等）。

**harness 模式**：不是 Agent 本身，而是运行 Agent 的框架。类似 test harness，定义了 Agent 的生命周期（初始化 → 循环 → 退出）和接口约定。这让不同的 Agent 实现可以在同一框架下运行。

## 关键实现

- **终端 UI**：基于 Go 的 TUI 框架，支持多面板显示（对话、文件 diff、终端输出）
- **工具抽象**：定义标准化的工具接口（文件读写、shell 执行、搜索），Agent 通过这些接口与系统交互
- **LLM 后端无关**：通过配置指定 API endpoint 和模型，支持 OpenAI/Anthropic/本地模型

## 关联分析

- [pi-mono](pi-mono.md) — 功能更完整的 TS 编码 Agent 工具包
- [Claude-Code-Source-Analysis](Claude-Code-Source-Analysis.md) — 成熟编码 Agent 的架构参考
- [GoClick](GoClick.md) — 另一个终端 Agent 工具

## 可执行建议

1. **自建编码 Agent 入门**：如果不想依赖 Claude Code/Cursor，fabrica 是一个轻量的起点，可以在此基础上添加自己的工具和逻辑
2. **Vibe Coding 参考**：理解 harness 模式有助于理解编码 Agent 的核心架构，不依赖具体实现

## 自评
| 维度 | 分数 | 权重 | 加权 |
|------|------|------|------|
| 摘要质量 | 7 | 0.25 | 1.75 |
| 技术深度 | 7 | 0.25 | 1.75 |
| 相关性 | 8 | 0.20 | 1.60 |
| 原创性 | 7 | 0.15 | 1.05 |
| 格式规范 | 9 | 0.15 | 1.35 |
| **加权总分** | | | **7.50** |