---
title: "mem0"
category: "entities"
tags: ["GitHub", "工具", "开源项目"]
rating: 8.5
description: "tags: #Agent-Memory #RAG #Personalization #BM25"
date: "2026-05-07"
---

# mem0

> tags: #Agent-Memory #RAG #Personalization #BM25
> source: [mem0ai/mem0](https://github.com/mem0ai/mem0)
> score: 技术深度8/10 | 实用价值9/10 | 时效性9/10 | 领域匹配9/10 | 综合 8.75/10

## 核心概念

mem0 是一个为 AI Agent 提供持久化记忆层的开源库（Python + TypeScript），通过自动提取、存储和检索对话中的关键信息，让 Agent 具备跨会话的上下文感知和个性化能力。它不是简单的聊天历史存储，而是对交互内容进行语义提炼后的结构化记忆。

## 设计原理

**核心 trade-off**：mem0 选择在 Agent 和 LLM 之间插入一个独立的记忆管理层，而非依赖 LLM 的 context window 或 prompt engineering 来维持状态。这样做的好处是记忆持久化且成本可控（不需要每次都把历史塞进 prompt），代价是引入了额外的存储依赖和检索延迟。

**记忆类型分离**：mem0 区分短期记忆（session-level）和长期记忆（user-level），通过不同的 TTL 和检索策略管理。这解决了 Agent 在多轮对话中"遗忘"和"信息过载"的矛盾。

**架构选择**：支持多种后端（Qdrant、PostgreSQL、MongoDB 等），而非绑定单一向量数据库。这让用户可以根据部署环境选择——本地开发用 SQLite + ChromaDB，生产环境用 Qdrant/PGVector。

### 2026-05-16 更新：新记忆算法（2026年4月）

2026年4月发布全新记忆算法，benchmark数据显著提升：

| Benchmark | 旧算法 | 新算法 | Tokens | Latency p50 |
|-----------|--------|--------|--------|-------------|
| LoCoMo | 71.4 | **91.6** (+20.2) | 7.0K | 0.88s |
| LongMemEval | 67.8 | **94.8** (+27.0) | 6.8K | 1.09s |
| BEAM (1M) | — | **64.1** | 6.7K | 1.00s |
| BEAM (10M) | — | **48.6** | 6.9K | 1.05s |

**算法变更要点**：
- **Single-pass ADD-only提取**：一次LLM调用，不再有UPDATE/DELETE操作。记忆只增不覆盖，简化了冲突处理
- **Agent生成事实成为一等公民**：当Agent确认执行某操作时，该信息以同等权重存储
- **Entity linking**：提取实体并embedding，跨记忆关联，提升检索质量
- **Multi-signal检索**：语义搜索 + BM25关键词 + 实体匹配三路并行融合
- **Temporal Reasoning**：时间感知检索，对"当前状态"、"过去事件"、"未来计划"查询区分处理

## 关键实现

- **记忆提取**：每次交互后，通过 LLM 自动判断哪些信息值得记忆（人名、偏好、决策等），生成结构化的 memory entry
- **记忆检索**：新对话开始时，根据当前 context 从记忆库中检索相关记忆，注入 system prompt
- **冲突解决**：当新信息与已有记忆矛盾时（如用户改了偏好），自动更新而非追加
- **集成方式**：提供 OpenAI/Anthropic/LangChain/LlamaIndex 的原生适配器，也支持 MCP 协议
- **TypeScript SDK**：`mem0-ts` 子项目提供 Node.js 支持，便于前端/全栈项目集成
- **Agent Mode CLI**（新增）：`mem0 init --agent --agent-caller claude-code --json`，Agent可自主初始化，无需人工登录
- **Skills集成**（新增）：支持Claude Code/Codex/Cursor等通过npx skills加载mem0能力

```python
from mem0 import Memory
memory = Memory()
# 添加记忆
memory.add("Prefers dark mode and vim keybindings", user_id="alice")
# 检索记忆
results = memory.search("What does Alice prefer?", user_id="alice")
```

## 关联分析

- [Memory-Management](../concepts/Memory-Management.md) — Agent 记忆系统的设计模式
- [claude-mem](../entities/claude-mem.md) — Claude Code 的记忆实现对比
- [OpenClaw](../entities/OpenClaw.md) — 使用记忆系统的 Agent 框架
- [nanobot](nanobot.md) — 另一个轻量Agent框架，可与mem0组合使用

## 可执行建议

1. **个人项目集成**：如果你的 Agent 需要记住用户偏好（如 coding style、常用工具），mem0 是最成熟的开源方案，比自建记忆层省大量时间
2. **成本控制**：新算法单次检索仅需~7K tokens、延迟~1s，性价比极高
3. **移动端场景**：TypeScript SDK + 轻量后端（SQLite）可以部署为个人记忆服务，供移动端 Agent 调用
4. **Agent Mode体验**：直接用`mem0 init --agent`让Coding Agent自主完成记忆层集成

## 自评
| 维度 | 分数 | 权重 | 加权 |
|------|------|------|------|
| 摘要质量 | 8.5 | 0.25 | 2.13 |
| 技术深度 | 8.0 | 0.25 | 2.00 |
| 相关性 | 9.0 | 0.20 | 1.80 |
| 原创性 | 7.5 | 0.15 | 1.13 |
| 格式规范 | 9.0 | 0.15 | 1.35 |
| **加权总分** | | | **8.40** |

> 评分依据：新算法的benchmark数据和架构变更都是实质性技术更新，Agent Mode CLI降低了集成门槛。
