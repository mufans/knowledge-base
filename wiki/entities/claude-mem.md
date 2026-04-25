# Claude-Mem 深度分析报告

> 项目：[thedotmack/claude-mem](https://github.com/thedotmack/claude-mem) v12.3.9  
> 分析时间：2026-04-25  
> 作者：Claw

---

## 一、架构分析

### 整体架构

Claude-Mem 是一个为 Claude Code 设计的持久化记忆压缩系统，采用 **Plugin + Worker + Database** 三层架构：

```
┌─────────────────────────────────────────────────┐
│           Claude Code (Host Process)             │
│  ┌──────────┐  ┌──────────┐  ┌──────────────┐  │
│  │ Lifecycle │  │  Hooks   │  │ MCP Tools    │  │
│  │ Events    │→ │ (6个)    │  │ (3层搜索)     │  │
│  └──────────┘  └────┬─────┘  └──────┬───────┘  │
└───────────────────────┼────────────────┼──────────┘
                        │ stdin/stdout   │ HTTP
                        ↓                ↓
┌─────────────────────────────────────────────────┐
│              Worker Service (Bun)                │
│  ┌─────────────┐  ┌──────────┐  ┌───────────┐  │
│  │ Express API  │  │ SSE推送   │  │ Agent SDK │  │
│  │ :37777      │  │ 实时更新  │  │ AI处理    │  │
│  └──────┬──────┘  └──────────┘  └─────┬─────┘  │
└─────────┼──────────────────────────────┼────────┘
          ↓                              ↓
┌─────────────────────────────────────────────────┐
│              Storage Layer                       │
│  ┌──────────────┐    ┌──────────────────────┐  │
│  │ SQLite + FTS5│    │ ChromaDB (可选)      │  │
│  │ 主存储+全文搜索│    │ 向量语义搜索         │  │
│  └──────────────┘    └──────────────────────┘  │
└─────────────────────────────────────────────────┘
```

### 模块划分

1. **Plugin Hooks（6个生命周期钩子）**：直接嵌入 Claude Code 的执行流程
   - `context-hook` → SessionStart：启动 Worker，注入历史上下文
   - `user-message-hook` → UserMessage：调试用
   - `new-hook` → UserPromptSubmit：创建会话，保存用户原始 prompt
   - `save-hook` → PostToolUse：捕获每次工具调用（核心数据采集点）
   - `summary-hook` → Stop：生成会话摘要
   - `cleanup-hook` → SessionEnd：标记会话完成

2. **Worker Service**：常驻后台进程，提供 HTTP API + SSE + AI 处理
   - Express.js 服务器，端口 37777
   - 10 个搜索端点 + 8 个 Viewer UI 端点
   - 通过 Claude Agent SDK 进行 AI 压缩处理

3. **Database Layer**：`bun:sqlite` 驱动的 SQLite
   - WAL 模式支持并发读写
   - FTS5 虚拟表实现全文搜索
   - 可选 ChromaDB 向量搜索

4. **Viewer UI**：React + TypeScript 构建的 Web 界面，实时展示记忆流

### 数据流

核心数据流是 **Observation Pipeline**：

```
Claude 工具调用 → stdin(Hook) → SQLite(原始) → Worker(异步) → Agent SDK(AI压缩) → SQLite(结构化) → 下次会话注入
```

关键设计：Hook 只负责"写入原始数据"，AI 压缩是异步的，不阻塞 Claude 的正常工作流。这是一个明智的解耦——Hook 执行有超时限制，如果把 AI 调用放在 Hook 里会导致超时。

### 设计模式

- **Observer Pattern**：通过 6 个生命周期 Hook 观察 Claude 的所有行为
- **CQRS-lite**：写入（Hook → SQLite）和读取（Worker API → FTS5）路径分离
- **Progressive Disclosure**：搜索采用 3 层渐进式展示（索引 → 时间线 → 详情），节省 token
- **Event Sourcing 思想**：所有工具调用作为不可变事件存储，后续通过 AI 提取语义

---

## 二、核心实现

### 2.1 Hook 数据采集（PostToolUse 为例）

`save-hook` 是最核心的数据采集点。每次 Claude 使用工具（文件读写、命令执行等），Claude Code 都会通过 stdin 将工具执行数据传递给 Hook。Hook 解析 JSON 后写入 SQLite：

```typescript
// src/hooks/save-hook.ts (构建后为 plugin/scripts/save-hook.js)
// 核心逻辑伪代码：
async function handlePostToolUse(input: ToolUseInput) {
  const observation = {
    session_id: input.session_id,
    sdk_session_id: input.sdk_session_id,
    project: input.project,
    tool_name: input.tool_name,       // 如 "Read", "Write", "Bash"
    correlation_id: input.correlation_id,
    // 原始数据暂存，等待 Worker 异步处理
    raw_input: JSON.stringify(input),
    created_at: new Date().toISOString(),
    created_at_epoch: Date.now()
  };
  await sessionStore.createObservation(observation);
}
```

### 2.2 AI 压缩处理

Worker Service 通过 Claude Agent SDK 对原始工具调用进行语义压缩：

```typescript
// src/sdk/worker.ts 核心流程
async function processObservation(observation: RawObservation) {
  // 构建 XML prompt，要求 Claude 提取结构化信息
  const prompt = buildPrompt(observation);
  
  const response = await claude.messages.create({
    model: "claude-sonnet-4-20250514",
    messages: [{ role: "user", content: prompt }],
    max_tokens: 1024
  });
  
  // 解析 XML 响应，提取结构化字段
  const parsed = parseXMLResponse(response.content);
  
  // 更新 observation 为结构化数据
  await sessionStore.updateObservation(observation.id, {
    title: parsed.title,
    subtitle: parsed.subtitle,
    narrative: parsed.narrative,
    facts: parsed.facts,        // 事实列表
    concepts: parsed.concepts,  // 概念标签
    type: parsed.type,          // decision/bugfix/feature/...
    files_read: parsed.filesRead,
    files_modified: parsed.filesModified
  });
}
```

**XML Prompt Builder**（`src/sdk/prompts.ts`）的设计值得注意——它要求 Claude 输出严格的 XML 格式：

```xml
<observation>
  <type>decision</type>
  <title>简短标题</title>
  <subtitle>子标题</subtitle>
  <narrative>详细叙述</narrative>
  <facts>
    <fact>事实1</fact>
    <fact>事实2</fact>
  </facts>
  <concepts>
    <concept>概念1</concept>
  </concepts>
  <filesRead>file1.ts, file2.ts</filesRead>
  <filesModified>file3.ts</filesModified>
</observation>
```

### 2.3 上下文注入（SessionStart）

`context-hook` 在新会话开始时，从数据库读取最近的结构化 observations 注入到 Claude 的上下文中：

```typescript
// src/hooks/context-hook.ts 核心逻辑
async function injectContext() {
  // 1. 确保 Worker 运行中
  await ensureWorkerRunning();
  
  // 2. 获取最近 N 条 observations（可配置）
  const recentObs = await sessionStore.getRecentObservations({
    project: currentProject,
    limit: settings.contextObservationCount // 默认值可配
  });
  
  // 3. 格式化为上下文文本注入
  const context = formatContext(recentObs);
  
  return { type: "context", content: context };
}
```

### 2.4 FTS5 全文搜索

```sql
-- observations_fts 虚拟表
CREATE VIRTUAL TABLE observations_fts USING fts5(
  title, subtitle, narrative, text, facts, concepts,
  content='observations', content_rowid='id'
);

-- 通过触发器自动同步
CREATE TRIGGER observations_ai AFTER INSERT ON observations BEGIN
  INSERT INTO observations_fts(rowid, title, subtitle, narrative, text, facts, concepts)
  VALUES (new.id, new.title, new.subtitle, new.narrative, new.text, new.facts, new.concepts);
END;
```

FTS5 查询支持丰富语法：`title:"authentication" AND "bug"`，且做了 SQL 注入防护（双引号转义 + 332 条注入测试）。

### 2.5 3 层渐进式搜索

这是 Claude-Mem 最精巧的设计之一，解决 token 成本问题：

```
Layer 1: search() → 返回紧凑索引（ID + 标题，~50-100 tokens/条）
Layer 2: timeline() → 按时间线展示上下文
Layer 3: get_observations(ids) → 只获取用户筛选后的完整详情（~500-1000 tokens/条）
```

**效果**：10x token 节省。先看索引决定要不要深入，避免全量拉取。

---

## 三、设计决策分析

### 决策1：Hook 异步写入 + Worker 异步 AI 处理

**选择**：Hook 只写原始数据到 SQLite，AI 压缩由后台 Worker 异步完成。

**Trade-off**：
- ✅ 不阻塞 Claude Code 的执行流程（Hook 有超时限制）
- ✅ 系统容错性好——Worker 挂了不影响 Claude 正常工作
- ❌ 新会话可能看不到上一会话的最新 observations（还在处理队列中）
- ❌ 需要额外维护一个常驻进程

**为什么这样选**：Claude Code 的 Hook 机制对执行时间敏感。如果 Hook 中调用 AI API（通常 2-10 秒），会显著拖慢 Claude 的响应速度。这个设计把"采集"和"理解"完全解耦。

### 决策2：SQLite + FTS5 而非 PostgreSQL + pgvector

**选择**：本地 SQLite 作为主存储，ChromaDB 作为可选向量搜索。

**Trade-off**：
- ✅ 零依赖安装——用户不需要数据库服务
- ✅ 单文件部署，适合个人开发者场景
- ✅ bun:sqlite 性能优秀（原生绑定）
- ❌ 不支持多机共享
- ❌ 大数据量下 SQLite 的并发能力有限
- ❌ ChromaDB 是额外依赖（需要 Python 的 uv）

**为什么这样选**：Claude-Mem 的核心场景是**单用户、单机**的 Claude Code 会话。SQLite 的 WAL 模式足以应对单用户的并发读写。对于个人工具来说，零依赖比扩展性更重要。

### 决策3：XML Prompt/Response 而非 JSON

**选择**：AI 压缩使用 XML 格式的 prompt 和 response。

**Trade-off**：
- ✅ XML 比 JSON 对 LLM 更友好（标签天然描述语义）
- ✅ 容错性好——缺失标签不会导致整个解析失败
- ❌ 解析代码更复杂（不能用简单的 JSON.parse）
- ❌ 没有强 schema 约束

**为什么这样选**：这是 LLM 工程中的常见实践。Claude 系列模型对 XML 的理解和生成能力很强，且 XML 的嵌套结构更适合表达 observation 这种半结构化数据。

### 决策4：Bun 作为进程管理器

**选择**：用 Bun 管理 Worker Service 的生命周期（启动、停止、重启）。

**Trade-off**：
- ✅ Bun 启动速度极快（比 Node.js 快 ~4x）
- ✅ 内置进程管理能力
- ❌ 多一个运行时依赖（用户可能已装 Node 但没 Bun）
- ❌ Bun 的稳定性在某些边缘场景不如 Node

**为什么这样选**：Worker Service 需要频繁重启（版本更新、异常恢复），Bun 的启动速度优势明显。且 Claude-Mem 的安装脚本会自动检测和安装 Bun。

### 决策5：Progressive Disclosure 搜索模式

**选择**：3 层渐进式搜索而非直接返回完整结果。

**Trade-off**：
- ✅ 大幅节省 token（10x）
- ✅ Claude 可以更精准地选择需要的信息
- ❌ 需要多次 MCP 工具调用（增加延迟）
- ❌ Claude 需要学习这个 workflow

**为什么这样选**：对于长期使用的项目，observations 可能积累到成千上万条。直接全量返回会消耗大量 context window。渐进式披露让 Claude 只"付费"看它真正需要的信息。

---

## 四、竞品对比

### 4.1 vs OpenClaw Memory

| 维度 | Claude-Mem | OpenClaw Memory |
|------|-----------|-----------------|
| **架构** | Plugin Hook + Worker + SQLite | SOUL.md + MEMORY.md + daily notes |
| **存储** | 结构化数据库（SQLite + FTS5） | 纯 Markdown 文件 |
| **AI 处理** | Claude Agent SDK 异步压缩 | 无 AI 处理，人工/Agent 写入 |
| **搜索** | FTS5 + ChromaDB 向量搜索 | 无搜索（文件读取） |
| **跨会话** | 自动（Hook 注入） | 手动（Agent 读文件） |
| **隐私** | 本地 SQLite | 本地文件 |
| **扩展性** | 支持 Claude Code / Gemini CLI / OpenCode / OpenClaw | 仅 OpenClaw |
| **实时性** | SSE 实时推送 Viewer | 无实时功能 |

**核心差异**：Claude-Mem 是**全自动**的记忆系统——用户无需手动记录，Hook 自动捕获所有行为。OpenClaw Memory 是**半手动**的——依赖 Agent 在 heartbeat/cron 中主动整理。Claude-Mem 的自动化程度更高，但 OpenClaw Memory 更灵活（可以记录任意非工具相关的信息，如情绪、决策推理）。

### 4.2 vs mem0

| 维度 | Claude-Mem | mem0 |
|------|-----------|------|
| **定位** | Claude Code 专用记忆插件 | 通用 AI 记忆层 |
| **存储** | SQLite + FTS5 | Qdrant/Chroma/pgvector |
| **记忆类型** | 工具调用 observation | 用户偏好、对话历史 |
| **AI 模型** | Claude Agent SDK | 可配任意 LLM |
| **接入方式** | Hook 自动 | SDK/API 调用 |
| **适用场景** | 开发会话记忆 | 通用 AI 应用 |

**核心差异**：mem0 是一个通用的记忆中间件，需要开发者主动调用 API 添加记忆。Claude-Mem 是**被动采集**——完全依赖 Hook 自动捕获，用户无需任何操作。mem0 更适合构建自定义 AI 应用的开发者，Claude-Mem 更适合直接使用 Claude Code 的开发者。

### 4.3 vs MemGPT (Letta)

| 维度 | Claude-Mem | MemGPT |
|------|-----------|--------|
| **记忆模型** | 扁平 observation 列表 | 分层记忆（core + archival + recall） |
| **记忆管理** | AI 压缩提取 | AI 主动管理（搜索、归档、遗忘） |
| **上下文策略** | 注入最近 N 条 | 动态分页加载 |
| **自省能力** | 无（被动记录） | 有（Agent 可以反思自己的记忆） |

**核心差异**：MemGPT 的分层记忆模型更接近人类记忆系统（工作记忆 + 长期记忆），Agent 可以主动管理自己的记忆。Claude-Mem 更像一个**自动化的工作日志**——忠实地记录所有操作，通过搜索回顾，但没有主动的记忆管理能力。

---

## 五、可借鉴模式

### 5.1 Hook 驱动的被动采集模式

**核心思路**：不要求用户主动记录，而是 Hook 到 AI Agent 的生命周期事件自动采集。

**可落地实现**：
```typescript
// 适用于任何支持 Hook 的 AI Agent（如 Cursor、Windsurf）
// 1. 在 PostToolUse hook 中捕获工具调用
// 2. 提取关键信息：工具名、输入参数、输出摘要、修改的文件
// 3. 异步写入存储，不阻塞主流程
```

**适用场景**：AI 编程助手的使用记录、操作审计、知识积累。

### 5.2 AI 压缩 + 结构化提取

**核心思路**：原始工具调用数据量大且噪声多，用 LLM 提取语义结构。

**可落地实现**：
```typescript
// Prompt 模板（Claude-Mem 的做法）
const COMPRESSION_PROMPT = `
分析以下工具调用，提取关键信息：
工具名: ${toolName}
输入: ${input}
输出: ${output}

请以 XML 格式返回：
<observation>
  <type>decision|bugfix|feature|discovery|change</type>
  <title>一句话总结</title>
  <narrative>详细描述</narrative>
  <facts>关键事实列表</facts>
</observation>
`;
```

**关键点**：
- 分类枚举（type）让后续搜索和过滤更高效
- facts 和 concepts 字段为 FTS5 搜索提供高质量索引内容
- 异步处理，不增加用户等待时间

### 5.3 3 层渐进式 Token 节省

**核心思路**：搜索结果分 3 层返回，让 AI 先看索引再决定要不要深入。

**可落地实现**：
```typescript
// Layer 1: 紧凑索引
search(query: string) → [{ id: 123, title: "修复认证Bug", type: "bugfix", date: "2026-04-25" }]

// Layer 2: 时间线上下文
timeline(observationId: 123) → [前后 5 条 observation 的摘要]

// Layer 3: 完整详情（按需）
getObservations(ids: [123, 456]) → [完整 observation 数据]
```

**适用场景**：任何需要在 LLM context 中展示大量历史数据的场景。这个模式可以直接迁移到 OpenClaw 的 MEMORY.md 管理——不是每次都注入完整记忆，而是提供一个"记忆索引"，让 Agent 按需查询。

### 5.4 FTS5 + Trigger 自动同步

**核心思路**：用 SQLite FTS5 做全文搜索，通过 Trigger 自动保持同步。

**可落地实现**：
```sql
-- 创建 FTS 虚拟表
CREATE VIRTUAL TABLE memories_fts USING fts5(
  title, content, tags,
  content='memories', content_rowid='id'
);

-- 自动同步 Trigger
CREATE TRIGGER memories_ai AFTER INSERT ON memories BEGIN
  INSERT INTO memories_fts(rowid, title, content, tags)
  VALUES (new.id, new.title, new.content, new.tags);
END;
```

**优势**：零维护成本的全文搜索。比外部搜索引擎（Elasticsearch）轻量得多，对个人/小团队场景完全够用。

### 5.5 Smart Install Pre-Hook

**核心思路**：在 Hook 执行前先检查依赖是否就绪，避免每次 Hook 调用都检查。

```javascript
// smart-install.js：检查 Bun、依赖包等是否安装
// 通过缓存机制只在版本变化时重新检查
// 避免每次 Claude Code 启动都执行耗时的依赖检查
```

---

## 六、质量评估

### 代码质量：7.5/10

**优点**：
- 架构清晰，模块划分合理
- 完善的错误处理（SQL 注入防护、332 条注入测试）
- 丰富的文档（官方 docs 站点 + 30+ 语言 README）
- 完整的测试覆盖（tests/ 目录下有 sqlite、search、context、server 等测试套件）
- CI/CD 完善（GitHub Actions: 测试、npm 发布、文档部署）
- TypeScript 全栈类型安全

**不足**：
- Worker Service 的构建产物是 minified 单文件（`worker-service.cjs`），源码只能从 `src/` 推断
- 依赖较重（Express + React + ChromaDB + Bun），安装链较长
- AGPL-3.0 许可证对商业使用有限制
- ChromaDB 需要 Python 环境（uv），对纯 Node.js 用户不友好

### 实用性：8.5/10

**优点**：
- `npx claude-mem install` 一键安装，用户体验极佳
- 完全自动化，无需手动操作
- 支持 Claude Code、Gemini CLI、OpenCode、OpenClaw 多平台
- Web Viewer UI 提供直观的记忆可视化
- 3 层搜索设计真正解决了 token 成本问题
- Progressive Disclosure 理念先进

**不足**：
- 依赖 Bun 运行时（部分用户可能抵触）
- AI 压缩需要消耗 Claude API 额度（每次工具调用都会触发）
- 对非英语用户，观察结果默认是英文（虽然有 `code--zh` 模式）
- 记忆只限于工具调用，无法记录非工具行为（如思考过程、决策推理）

### 综合评价

Claude-Mem 是目前 Claude Code 生态中最成熟的记忆解决方案。它的核心价值在于**零摩擦的自动化**——安装后完全不需要用户干预，就能跨会话保持上下文。

**最值得借鉴的 3 个设计**：
1. **被动采集 + 异步 AI 压缩**：不侵入工作流，后台静默处理
2. **3 层渐进式搜索**：以最小 token 成本获取最相关信息
3. **结构化 Observation 类型系统**（decision/bugfix/feature/discovery）：让记忆可分类、可过滤、可搜索

**对 mufans 的启示**：这个项目的设计理念可以直接应用于 AI Agent 的记忆管理。特别是 3 层渐进式搜索模式，可以改造 OpenClaw 的记忆检索机制——不是每次都注入完整 MEMORY.md，而是提供一个轻量索引，让 Agent 按需深入查询。这在 Agent 长期运行、记忆量大的场景下尤为重要。
