---
title: "RAGFlow"
category: "entities"
tags: ["GitHub", "OS", "RAG", "工具", "框架", "检索增强"]
rating: 7.5
description: "tags: #RAG #Agent #OpenSource #RetrievalAugmented #KnowledgeManagement"
date: "2026-05-07"
---

# RAGFlow

> tags: #RAG #Agent #OpenSource #RetrievalAugmented #KnowledgeManagement
> source: [ai-knowledge-base采集](https://github.com/infiniflow/ragflow)
> project: [infiniflow/ragflow](https://github.com/infiniflow/ragflow)
> score: 技术深度8/10 | 实用价值9/10 | 时效性8/10 | 领域匹配9/10 | 综合 8.5/10

---
title: "RAGFlow：开源RAG引擎与Agent融合平台"
category: entities
tags: [RAG, Agent, 开源, 检索增强, 知识管理]
rating: 8.5
description: "RAGFlow是infiniflow开源的RAG+Agent引擎，79k+ stars，融合深度文档理解与Agent工作流，为LLM提供高质量上下文层"
date: 2026-05-07
---

## 核心概念

RAGFlow 是一个开源的检索增强生成（RAG）引擎，核心定位是**将深度文档理解能力与 Agent 工作流融合**，为 LLM 应用提供经过精细切分和检索的上下文层。与普通 RAG 框架不同，RAGFlow 强调"深度文档理解"（DeepDoc）——对 PDF、表格、图片等非结构化文档进行版面分析和结构化提取。

项目数据：79,854 stars、9,089 forks（截至 2026-05），是目前 RAG 领域最受欢迎的开源项目之一。

## 设计原理

**Trade-off 分析**：

- **深度文档解析 vs 速度**：RAGFlow 采用自研 DeepDoc 引擎做版面分析（布局检测、表格识别、OCR），精度高但处理速度比纯文本切分慢。选择这个 trade-off 是因为企业场景中 PDF/表格占比极高，浅层切分会导致召回质量灾难
- **一体化平台 vs 可组合微服务**：RAGFlow 提供完整的 Web UI + API + Agent 编排，开箱即用但定制灵活性不如纯 SDK（如 LangChain）。适合快速落地，不适合需要深度定制检索管线的场景
- **Agent 内置 vs 外接 Agent 框架**：内置了 Agent 编排能力（对话流、工具调用），但也支持通过 API 外接 LangGraph/CrewAI 等。这个设计降低了入门门槛，同时保留了扩展性

## 关键实现

### 技术栈
- **后端**：Python + Flask，深度文档处理用 PyTorch
- **前端**：React
- **部署**：Docker Compose 一键启动，依赖 Elasticsearch/Infinity 作为向量库
- **文档解析**：DeepDoc 引擎（版面分析 + OCR + 表格结构化）

### 核心模块（源码结构）
```
agent/        → Agent 编排逻辑（对话流、工具调用）
deepdoc/      → 深度文档解析引擎（核心壁垒）
api/          → REST API 层
mcp/          → MCP 协议支持（可被其他 Agent 框架调用）
conf/         → 配置管理（LLM 接入、模型选择）
```

### 检索管线
1. 文档上传 → DeepDoc 解析（版面检测 → 表格/图片/文本分类 → 结构化提取）
2. 文本切分（支持多种策略：手动、自动、按 QA 对）
3. 向量化 + 入库（支持 Elasticsearch、Infinity）
4. 查询时：混合检索（向量 + 关键词 BM25）+ 重排序

### Agent 能力
- 内置对话流编排（可视化拖拽）
- 支持 MCP 协议，可被 OpenClaw 等 Agent 框架作为工具调用
- 支持多轮对话上下文管理

## 关联分析

- [Self-RAG](../concepts/Self-RAG.md)：Self-RAG 是 RAG 的方法论改进，RAGFlow 是工程实现层面的平台，两者互补
- 与 [LangChain](https://github.com/langchain-ai/langchain) 的定位差异：LangChain 是可组合的 SDK，RAGFlow 是一体化 RAG 平台，各自适合不同场景
- 与纯向量数据库（Milvus/Weaviate）的关系：RAGFlow 是上层应用，依赖向量库做存储和检索

## 可执行建议

1. **快速试用**：`docker compose -f docker/docker-compose.yml up -d`，5 分钟跑通 Demo
2. **移动端场景**：如果做"文档问答"类移动端应用，RAGFlow 的 API 可以作为后端，前端负责文档上传和对话交互
3. **与现有 Agent 集成**：通过 MCP 协议将 RAGFlow 接入 OpenClaw 或其他 Agent 框架，作为知识检索工具
4. **关注 DeepDoc**：即使不用 RAGFlow 整体，其 DeepDoc 文档解析模块值得单独研究，尤其是表格和版面分析部分

## 自评

| 维度 | 分数 | 权重 | 加权 |
|------|------|------|------|
| 摘要质量 | 8 | 0.25 | 2.00 |
| 技术深度 | 8 | 0.25 | 2.00 |
| 相关性 | 9 | 0.20 | 1.80 |
| 原创性 | 8 | 0.15 | 1.20 |
| 格式规范 | 9 | 0.15 | 1.35 |
| **加权总分** | | | **8.35** |

> 评分说明：摘要质量扣分因缺少基准测试数据；技术深度覆盖了架构和 trade-off 但未深入 DeepDoc 算法细节；相关性高因 RAG + Agent 是核心研究方向