---
title: "Khoj"
category: "entities"
tags: ["GitHub", "工具"]
rating: 7.0
description: "tags: #RAG #Self-Hosted #AI-Agent #Productivity #Semantic-Search"
date: "2026-05-15"
---

# Khoj

> tags: #RAG #Self-Hosted #AI-Agent #Productivity #Semantic-Search
> source: [khoj-ai/khoj](https://github.com/khoj-ai/khoj)
> project: [Khoj](https://github.com/khoj-ai/khoj)
> score: 技术深度7/10 | 实用价值9/10 | 时效性8/10 | 领域匹配8/10 | 综合 8.0/10

## 核心概念

Khoj 是一个开源、可自托管的个人 AI 第二大脑，集成了 RAG 检索、自定义 Agent、自动化调度和深度研究能力。支持多种 LLM 后端（GPT、Claude、Gemini、Llama、Qwen、Mistral 等），覆盖从本地推理到云端 API 的全场景。

## 设计原理

Khoj 的核心设计理念是 **个人知识的外延**——不是单纯的聊天机器人，而是将文档检索、语义搜索、Agent 自动化和多端访问整合为一个统一的知识操作系统。

- **多端统一**：Web、Obsidian、Emacs、Desktop、Phone、WhatsApp 全覆盖，体现了"AI 能力无处不在"的设计思路
- **自托管优先**：AGPL v3 许可，强调数据主权，适合对隐私敏感的开发者
- **Agent 可定制**：支持自定义知识库、人格、聊天模型和工具，构建专属 Agent
- **自动化调度**：可定时执行研究任务，生成个人新闻简报和智能通知

## 关键实现

- **技术栈**：Python，基于 Django 后端
- **文档支持**：PDF、Markdown、Notion、Word、org-mode、图片等
- **部署方式**：Docker 自托管 / 云端 [app.khoj.dev](https://app.khoj.dev)
- **Star 数**：34.5k+（2026-05），社区活跃度高
- **新项目 Pipali**：开源 AI coworker，运行在本地电脑上，扩展了 Khoj 的桌面协同能力

```bash
# Docker 自托管快速启动
docker run -d --name khoj \
  -p 42110:42110 \
  -v khoj_config:/root/.khoj/ \
  ghcr.io/khoj-ai/khoj:latest
```

## 关联分析

- 与 [mem0](mem0.md) 互补：Khoj 侧重文档检索和 Agent 编排，Mem0 侧重对话记忆层
- 与 [RAGFlow](RAGFlow.md) 对比：Khoj 面向个人知识管理，RAGFlow 更偏企业级 RAG 引擎
- 与 [Dify](Dify.md) 对比：Khoj 强调自托管和个人使用，Dify 侧重低代码工作流编排
- 适用 [Context-Window-Optimization](../concepts/Context-Window-Optimization.md)：大量文档场景下的检索策略

## 可执行建议

1. **快速体验**：直接用 [app.khoj.dev](https://app.khoj.dev) 免费试用，评估 RAG 检索质量
2. **自托管部署**：Docker 一键启动，接入 Obsidian 笔记库作为个人知识引擎
3. **Agent 开发参考**：学习其自定义 Agent 的知识注入和工具集成模式，可借鉴到移动端 AI 应用
4. **自动化思路**：定时研究任务的实现方式可作为个人 AI 工作流的参考架构

## 自评
| 维度 | 分数 | 权重 | 加权 |
|------|------|------|------|
| 摘要质量 | 8 | 0.25 | 2.00 |
| 技术深度 | 7 | 0.25 | 1.75 |
| 相关性 | 8 | 0.20 | 1.60 |
| 原创性 | 7 | 0.15 | 1.05 |
| 格式规范 | 8 | 0.15 | 1.20 |
| **加权总分** | | | **7.60** |