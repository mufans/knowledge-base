# Claude Context 源码分析

> 基于 zilliztech/claude-context 仓库的源码级技术分析

## 架构总览

项目采用 monorepo，核心分为三层：

```
@zilliz/claude-context-mcp (MCP Server层)
    ↓ 调用
@zilliz/claude-context-core (引擎层)
    ↓ 依赖
Milvus/Zilliz Cloud + Embedding Provider (基础设施层)
```

## MCP Server 入口分析

**文件**: `packages/mcp/src/index.ts`

### 1. stdout 劫持——关键的协议保障

```typescript
const originalConsoleLog = console.log;
console.log = (...args: any[]) => {
    process.stderr.write('[LOG] ' + args.join(' ') + '\n');
};
```

这是 MCP stdio 传输的**经典陷阱**：MCP 协议通过 stdout 传递 JSON-RPC 消息，如果任何 console.log 泄漏到 stdout，会破坏协议解析。代码在第一行就劫持了 console.log/warn 到 stderr，确保只有 MCP SDK 的消息走 stdout。这个细节体现了作者对 stdio 传输协议的深刻理解。

### 2. 初始化链路

```typescript
// 1. 创建 embedding 实例（支持 OpenAI/VoyageAI/Ollama/Gemini）
const embedding = createEmbeddingInstance(config);

// 2. 创建向量数据库连接
const vectorDatabase = new MilvusVectorDatabase({
    address: config.milvusAddress,
    token: config.milvusToken
});

// 3. 初始化核心 Context
this.context = new Context({ embedding, vectorDatabase, collectionNameOverride });

// 4. 启动时加载已有快照
this.snapshotManager.loadCodebaseSnapshot();
```

初始化顺序很重要：embedding → vectorDB → Context → snapshot。snapshot 在 Context 之后加载，因为 snapshot 管理需要 Context 实例来执行搜索。

### 3. 工具注册模式

```typescript
this.server.setRequestHandler(ListToolsRequestSchema, async () => ({
    tools: [indexTool, searchTool, clearTool, statusTool]
}));
this.server.setRequestHandler(CallToolRequestSchema, async (request) => {
    // 路由到 ToolHandlers
});
```

标准的 MCP 工具注册方式。Tool 定义中的 description 写得非常详细（包含使用场景、注意事项），这是为了让 AI agent 更好地理解何时调用哪个工具——本质上是在对 agent 做"提示工程"。

## Core 引擎分析

**文件**: `packages/core/package.json`

### 依赖选择分析

| 依赖 | 用途 | 为什么选它 |
|------|------|-----------|
| `tree-sitter` + 14种语言 grammar | AST 分块 | tree-sitter 是目前最快的增量解析器，支持部分解析 |
| `faiss-node` | 本地向量索引 | Meta 出品，C++ 核心，Node.js 绑定，适合小规模/本地场景 |
| `@zilliz/milvus2-sdk-node` | 远程向量数据库 | 官方 SDK，Milvus 是生产级向量数据库 |
| `langchain` | 字符级分块 fallback | LangChain 的 RecursiveCharacterTextSplitter 成熟稳定 |
| `glob` | 文件遍历 | 比 fs.readdir 递归更简洁，支持 ignore pattern |

### 为什么同时依赖 faiss-node 和 Milvus？

这是一个有趣的**双模式设计**：faiss-node 用于本地/轻量场景，Milvus 用于生产/大规模场景。但从代码看，MCP Server 只初始化了 MilvusVectorDatabase，faiss-node 更可能是 core 包内部使用或留给直接调用 core 的用户。

## 文件过滤系统

**文件**: `docs/dive-deep/file-inclusion-rules.md`

过滤规则是一个**多层叠加**系统：

```
最终文件 = (默认扩展 + MCP自定义 + 环境变量) - (默认忽略 + MCP自定义 + 环境变量 + .gitignore + .xxxignore + 全局.contextignore)
```

设计亮点：
1. **尊重 .gitignore**：不会索引 git 已经忽略的文件
2. **尊重 .cursorignore 等**：兼容其他 AI 工具的排除规则
3. **全局 .contextignore**：`~/.context/.contextignore` 允许用户对所有项目统一排除
4. **MCP 动态扩展**：agent 可以在对话中动态指定额外的扩展和忽略规则

这个设计比简单的 `.ignore` 文件更灵活，但也更复杂。trade-off 是：灵活性 vs 认知负担。

## Embedding Provider 抽象

支持 4 种 embedding 提供商：

1. **OpenAI**（默认）：`text-embedding-3-small`，生态最成熟
2. **VoyageAI**：`voyage-code-3`，专门为代码优化的 embedding 模型
3. **Ollama**：本地运行，离线可用，但质量较低
4. **Gemini**：Google 的 embedding 服务

 VoyageAI 的 `voyage-code-3` 值得关注——它是专门为代码检索训练的 embedding 模型，在代码搜索任务上可能比通用的 OpenAI embedding 表现更好。如果 Zilliz 推荐这个选项，说明他们做过对比评测。

## 关键设计决策总结

1. **混合搜索（BM25 + Dense）**：不单纯依赖向量相似度，BM25 补偿精确匹配能力
2. **AST 分块优先**：代码是结构化文本，AST 分块比固定窗口更符合代码语义
3. **Merkle Tree 增量索引**：避免每次全量重建，但增加了实现复杂度
4. **外部向量数据库**：牺牲部署简便性换取可扩展性
5. **Tool Description 即 Prompt**：MCP 工具的 description 就是给 AI 的 prompt，写得越详细 agent 越会用

## 与同类方案对比

| 维度 | Claude Context | aider (repo-map) | grep-based |
|------|---------------|------------------|------------|
| 搜索方式 | 语义+关键词混合 | AST + ctags | 纯文本匹配 |
| 基础设施 | 需要向量数据库 | 本地无依赖 | 本地无依赖 |
| 索引成本 | 高（embedding API费用） | 低 | 无 |
| 语义理解 | 强 | 中（基于结构） | 无 |
| 适合规模 | 大型代码库 | 中型 | 任意 |
