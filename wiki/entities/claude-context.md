# Claude Context

> Zilliz（Milvus母公司）出品的语义代码搜索MCP工具，让AI编码代理能检索整个代码库作为上下文

## 项目概述

Claude Context 是一个 MCP (Model Context Protocol) 服务器，为 Claude Code、Codex CLI、Cursor 等 AI 编码代理提供**语义代码搜索**能力。核心价值：用自然语言查询代码库，返回语义相关的代码片段，而不是简单的文本匹配。

**GitHub**: zilliztech/claude-context | **Stars**: ~8,000+ | **License**: MIT

## 解决的核心问题

传统 AI 编码代理在面对大型代码库时有两个痛点：

1. **上下文窗口限制**：无法将整个代码库塞进 context，导致 agent 只能"盲人摸象"——看到什么改什么
2. **发现成本高**：agent 需要多轮 grep/文件读取才能找到相关代码，消耗大量 token 和时间

Claude Context 的方案是：**预先将代码库索引到向量数据库**，agent 通过自然语言查询一次就能拿到相关代码，官方评测称在同等检索质量下减少约 40% 的 token 消耗。

## 技术架构

### Monorepo 结构

```
packages/
├── core/           # 核心引擎：索引、分块、向量存储
├── mcp/            # MCP Server：暴露搜索工具给 AI agent
└── vscode/         # VS Code 扩展（可选）
```

### 核心依赖链

- **tree-sitter** 系列：AST 感知的代码分块（支持 TS/JS/Python/Java/Go/Rust/C++/C#/Kotlin/Swift/Scala 等 14 种语言）
- **OpenAI/VoyageAI/Ollama/Gemini**：Embedding 模型（可选，默认 OpenAI）
- **Milvus/Zilliz Cloud**：向量数据库（必需）
- **faiss-node**：本地向量检索（辅助）
- **LangChain**：字符级分块的后备方案

### 搜索机制：混合搜索

Claude Context 采用 **BM25 + Dense Vector** 的混合搜索策略：

- **BM25**：传统关键词匹配，擅长精确的标识符搜索（如函数名、类名）
- **Dense Vector**：语义相似度匹配，擅长意图理解（如"处理用户认证的函数"）

两者的 trade-off：纯语义搜索可能在精确匹配上不如 BM25，纯关键词搜索无法理解意图。混合搜索通过加权融合两者结果，覆盖两种场景。

### 增量索引：Merkle Tree

代码库频繁变更，全量重建索引代价太高。Claude Context 用 Merkle Tree 跟踪文件变更：

- 每个文件生成一个 hash（基于内容）
- 目录的 hash = 子文件 hash 的组合
- 只对比顶层 hash 就能判断是否有变更，递归定位到具体变更文件

这比简单对比文件修改时间更可靠（避免 git checkout 等操作导致的假变更）。

### 代码分块策略

默认使用 **AST splitter**（tree-sitter），按语法结构分割代码：
- 以函数、类、方法为边界
- 保留上下文信息（父节点路径）
- 不支持的语言自动 fallback 到 LangChain 字符级分块

为什么选择 AST 而不是固定行数？因为代码的语义单元不是按行分布的——一个函数可能 5 行也可能 500 行，固定行数会切断语义。

## MCP 工具定义

暴露 4 个工具：

| 工具 | 功能 | 关键参数 |
|------|------|----------|
| `index_codebase` | 索引代码库 | path, force, splitter(ast/langchain), customExtensions, ignorePatterns |
| `search_code` | 语义搜索 | path, query, limit(max 50), extensionFilter |
| `clear_index` | 清除索引 | path |
| `get_index_status` | 查看索引状态 | path |

## Trade-off 分析

### 为什么强依赖外部向量数据库？

这是个有争议的设计。好处是**可扩展性**——无论代码库多大，搜索性能由 Milvus 集群保证。坏处是**部署复杂度高**——需要注册 Zilliz Cloud 或自建 Milvus，还额外需要 OpenAI API Key 做 embedding。对于小项目（<10万行），本地方案（如 ripgrep + 简单 embedding）可能更实际。

### 为什么是 Zilliz 的项目？

这是典型的**生态护城河**策略。Zilliz 是 Milvus 的商业化公司，Claude Context 本质上是 Milvus/Zilliz Cloud 的**一个上层应用场景**——让用户在用 AI 编码工具时"顺便"用上向量数据库。对 Zilliz 来说是获客渠道，对用户来说提供了实用工具。

### 与 grep/AST 工具的本质区别

- **grep-based**（如 ripgrep）：精确但无语义，搜"auth"不会返回"authentication"
- **AST-based**（如 tree-sitter query）：有结构但无语义，能找到所有函数定义但无法理解意图
- **Claude Context**：有语义理解，但依赖 embedding 质量且需要外部基础设施

三者不是替代关系，而是互补：精确搜索用 grep，结构搜索用 AST，意图搜索用语义。

## 适用场景

**适合**：
- 超大型代码库（百万行级别）的 AI 辅助开发
- 需要跨模块理解代码关系的场景
- 团队已经使用 Milvus/Zilliz 的基础设施

**不必要**：
- 小型项目直接让 agent 用 grep/ripgrep 就够了
- 不想引入额外外部依赖（向量数据库 + embedding API）的场景
- 对搜索延迟敏感的场景（需要网络往返）
