---
title: "AI Engineering Hub: LLM/RAG/Agent实战教程集"
category: "entities"
tags: ["LLM", "RAG", "AI-Agents", "MCP", "Machine-Learning", "Tutorial"]
rating: 8.5
description: "面向LLM/RAG/AI Agent的实战教程合集，Jupyter Notebook形式，涵盖MCP、DeepSeek微调等前沿技术"
date: "2026-05-11"
---

# AI Engineering Hub: LLM/RAG/Agent实战教程集

> tags: #LLM #RAG #AI-Agents #MCP #Machine-Learning #Tutorial
> source: [patchy631/ai-engineering-hub](https://github.com/patchy631/ai-engineering-hub) ⭐34889
> score: 技术深度7/10 | 实用价值9/10 | 时效性8/10 | 领域匹配9/10 | 综合 8.2/10

## 核心概念

AI Engineering Hub是一个**面向实战的AI工程教程合集**，以Jupyter Notebook形式提供LLM、RAG、AI Agent的端到端实现。涵盖从基础的RAG管道到高级的Multi-Agent系统、MCP集成、DeepSeek微调等前沿方向。⭐34.8k，教程以"能跑的代码"为核心，不是理论堆砌。

## 设计原理

### 教程设计理念

- **Notebook-First**：每个教程都是可直接运行的Jupyter Notebook，降低学习门槛
- **Progressive Complexity**：从基础到高级递进，不是碎片化的代码片段
- **Real-World Focus**：教程基于真实场景（网站RAG、YouTube分析、DeepSeek微调等）

Trade-off：Notebook形式适合学习和原型验证，但不适合生产环境直接使用。教程深度有限，每个方向点到为止，需要进一步深入学习。

### 技术覆盖范围

| 方向 | 教程内容 |
|------|----------|
| RAG | Colivara + DeepSeek网站RAG、FireCrawl网站转API |
| Agent | Multi-Agent深度研究器（MCP集成） |
| 微调 | DeepSeek微调实战 |
| OCR | LLaMA + LaTeX OCR |
| 推理 | Build reasoning model |
| 代码 | acp-code（Agent Communication Protocol） |

## 关键实现

### 代表性教程

1. **Multi-Agent深度研究器（MCP）**：构建多Agent协作的深度研究系统，集成MCP协议，支持Windows/Linux
2. **DeepSeek微调**：使用DeepSeek模型进行微调的完整pipeline
3. **网站RAG**：使用Colivara进行文档索引 + DeepSeek进行问答
4. **YouTube趋势分析**：使用LLM分析YouTube视频数据

### 技术栈

- **语言**：Python（Jupyter Notebook）
- **LLM集成**：OpenAI、DeepSeek、Llama
- **框架**：LangChain、LlamaIndex
- **协议**：MCP（Model Context Protocol）

### 项目结构

```
ai-engineering-hub/
├── Build-reasoning-model/        # 推理模型构建
├── Colivara-deepseek-website-RAG/ # 网站RAG
├── DeepSeek-finetuning/           # DeepSeek微调
├── LaTeX-OCR-with-Llama/          # LaTeX OCR
├── Multi-Agent-deep-researcher-mcp-windows-linux/ # 多Agent研究器
├── Website-to-API-with-FireCrawl/ # 网站转API
├── Youtube-trend-analysis/        # YouTube分析
└── acp-code/                      # Agent通信协议
```

## 关联分析

- [LlamaFactory](LlamaFactory.md) — DeepSeek微调教程的底层框架，LlamaFactory提供更系统的微调能力
- [browser-use](browser-use.md) — 网站RAG和网站转API教程可能使用类似技术
- [Dify](Dify.md) — Dify提供低代码的RAG/Agent编排，与教程的代码实现互补
- [RAGFlow](RAGFlow.md) — RAGFlow是生产级RAG引擎，教程的RAG部分是其简化版
- [Agent-Skills-Architecture](../sources/Agent-Skills-Architecture.md) — MCP教程与Agent Skills架构的对比

## 可执行建议

1. **快速上手**：如果你要快速验证某个AI工程方向（如MCP、RAG），这里是最好的起点——Notebook即克隆即跑
2. **MCP实战**：Multi-Agent MCP教程是当前少有的MCP实战资料，建议优先学习
3. **教学参考**：如果你计划做AI Agent相关的技术分享或写作，这些Notebook是很好的素材来源
4. **深度延伸**：每个教程只是入门，建议结合源码和官方文档深入学习——比如MCP教程后去读MCP规范

## 自评
| 维度 | 分数 | 权重 | 加权 |
|------|------|------|------|
| 摘要质量 | 7 | 0.25 | 1.75 |
| 技术深度 | 7 | 0.25 | 1.75 |
| 相关性 | 9 | 0.20 | 1.80 |
| 原创性 | 7 | 0.15 | 1.05 |
| 格式规范 | 9 | 0.15 | 1.35 |
| **加权总分** | | | **7.70** |

> 评分说明：34.8k stars的教程项目，实用价值高但技术深度有限；教程覆盖面广但每个方向较浅；MCP实战教程是当前稀缺资源；领域匹配度极高，直接对应用户的学习方向。