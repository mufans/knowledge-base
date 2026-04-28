# Claude Code v2.1.88 源码深度分析

> tags: #ClaudeCode #AgentArchitecture #ToolSystem #MCP #ContextManagement #Subagent
> source: [claude-code-source-code](https://github.com/mufans/claude-code-source-code) (decompiled, v2.1.88)
> project: [Claude Code](https://github.com/anthropics/claude-code)
> score: 技术深度9/10 | 实用价值9/10 | 时效性8/10 | 领域匹配10/10 | 综合 9.0/10

## 核心概念

Claude Code是Anthropic官方的CLI Agent，采用TypeScript/Bun运行时构建，核心是一个基于流式API的agentic loop，支持工具调用、MCP协议、子agent分叉、会话持久化和多级上下文压缩。v2.1.88是反编译源码，保留了完整的架构信息。

## 整体架构

### 目录结构（按职责分层）

```
src/
├── entrypoints/          # 启动入口：cli.tsx(交互模式), sdk/(SDK模式), init.ts(初始化)
├── QueryEngine.ts        # 会话级引擎，管理消息历史、提交消息
├── query.ts              # 单次查询循环（核心agentic loop）
├── Tool.ts               # 工具类型定义和工具查找
├── tools.ts              # 内置工具注册表
├── tools/                # 30+内置工具实现（Bash、FileRead/Write/Edit、Agent、MCP等）
├── services/
│   ├── api/claude.ts     # Anthropic API调用层（流式、重试、fallback）
│   ├── mcp/              # MCP客户端（连接管理、协议实现）
│   ├── compact/          # 上下文压缩（autoCompact、reactiveCompact、snipCompact）
│   ├── tools/            # 工具执行编排（StreamingToolExecutor、toolOrchestration）
│   └── analytics/        # GrowthBook A/B测试 + OpenTelemetry遥测
├── state/                # React状态管理（AppState + Zustand-like store）
├── hooks/                # React hooks（权限检查、工具使用等）
├── components/           # Ink TUI组件（权限对话框、diff视图、消息渲染）
├── tasks/                # 后台任务系统（LocalAgentTask、DreamTask、RemoteAgentTask）
├── commands/             # 60+斜杠命令实现
├── utils/                # 通用工具（shell、sandbox、permissions、hooks、memory等）
├── constants/            # 系统提示词、XML标签等
└── ink/                  # Ink渲染引擎（fork自Svelte的Yoga布局，自包含）
```

### 启动流程

`src/entrypoints/cli.tsx` 的 `main()` 函数采用**多层快速路径分流**设计：

1. **零依赖快速路径**：`--version` 直接输出，不加载任何模块
2. **轻量快速路径**：`--dump-system-prompt`、`--chrome-native-host`、`--computer-use-mcp` 等只加载必要的动态import
3. **基础设施快速路径**：`daemon`、`bridge/remote-control`、`ps/logs/attach/kill` 等
4. **全量CLI路径**：其余所有情况加载 `main.tsx`

关键设计决策：**所有非主路径的import都是动态的**（`await import(...)`），避免启动时加载不必要的模块。这在`cli.tsx`中有大量注释强调"All imports are dynamic to minimize module evaluation for fast paths"。

`init.ts` 负责全局初始化：配置系统、graceful shutdown、遥测（懒加载OTel ~400KB）、代理/mTLS、Git仓库检测、OAuth填充等。遥测初始化**延迟到用户信任对话框之后**（`initializeTelemetryAfterTrust`），避免在未信任时发送数据。

### 模块依赖关系

核心数据流：`cli.tsx` → `init.ts` → `main.tsx` → `QueryEngine` → `query()`（agentic loop） → `runTools()` / `StreamingToolExecutor` → 各工具实现

状态管理采用React Context + 自定义store（`AppStateStore.ts`），通过`setAppState(fn)`函数式更新，类似Zustand但更轻量。`AppState`承载了权限上下文、fast mode、file history、进度信息等所有运行时状态。

### 设计模式

1. **Feature Flag DCE（Dead Code Elimination）**：使用Bun的`feature()`函数在构建时移除实验性代码。整个代码库中大量使用：
   ```typescript
   const snipModule = feature('HISTORY_SNIP')
     ? (require('./services/compact/snipCompact.js'))
     : null
   ```
   这保证了外部构建（公开npm包）不会包含内部实验代码。

2. **AsyncGenerator流式架构**：`query()` 和 `QueryEngine.submitMessage()` 都是 `AsyncGenerator<SDKMessage>`，通过yield逐条输出流式事件。消费者可以逐步消费assistant消息、工具调用进度和最终结果。

3. **Strategy Pattern（权限检查）**：`CanUseToolFn` 是一个注入的函数签名，根据当前权限模式（default/auto/bypass/plan）返回allow/deny/ask结果。

4. **Command Pattern（斜杠命令）**：每个斜杠命令是独立的模块，通过`processUserInput`统一调度，命令可以修改消息数组和查询参数。

## 核心功能模块深度分析

### 1. Agent Loop（`src/query.ts` + `src/QueryEngine.ts`）

**QueryEngine** 是会话级抽象（`src/QueryEngine.ts`，~1295行），每个对话一个实例：

- 维护 `mutableMessages: Message[]` 作为可变消息历史
- `submitMessage()` 是对外接口，每次调用开始一个新turn
- 内部调用 `query()` 执行实际的agentic循环

**query()** 是核心循环（`src/query.ts`，~800行），采用 `while(true)` + `yield*` 的generator模式：

```
queryLoop:
  while(true):
    1. 获取消息（messagesForQuery = getMessagesAfterCompactBoundary）
    2. 应用工具结果大小限制（applyToolResultBudget）
    3. 应用snip压缩（feature-gated）
    4. 应用microcompact（缓存编辑压缩）
    5. 应用context collapse（feature-gated）
    6. 构建API请求参数（systemPrompt + userContext + messages）
    7. 流式调用API（streamQuery）
    8. 处理流式响应（文本/thinking/tool_use）
    9. 执行工具（runTools / StreamingToolExecutor）
    10. 检查stop reason（end_turn继续循环，tool_use继续，max_tokens恢复）
    11. autoCompact检查（如果接近上下文窗口）
    12. token budget检查（feature-gated +500k自动续费）
```

关键设计：**循环状态集中管理在 `State` 对象中**，7个continue站点统一通过 `state = { ...state, ... }` 更新，避免分散的变量赋值。这是从实际调试中提炼出的模式（注释中提到"see the 7 continue sites"）。

**Thinking blocks处理规则**（query.ts中的著名注释）：
1. 包含thinking/redacted_thinking的消息必须 `max_thinking_length > 0`
2. thinking block不能是最后一条消息
3. thinking blocks必须在"assistant trajectory"（turn + tool_use + tool_result + next assistant）内保留

### 2. Tool System（`src/Tool.ts` + `src/tools/` + `src/services/tools/`）

**工具注册**（`src/tools.ts`）：返回 `Tools` 类型（即 `Tool[]`），每个工具包含：
- `name`: 工具名
- `inputSchema`: Zod schema（运行时验证）
- `execute()`: 执行函数，返回 `AsyncGenerator`
- `isReadOnly` / `isConcurrencySafe`: 并发控制标记
- `maxResultSizeChars`: 结果大小限制

**工具执行编排**（`src/services/tools/toolOrchestration.ts`）：
- `partitionToolCalls()`: 将工具调用分为并发安全批次和非并发批次
- `runToolsConcurrently()`: 并发安全工具并行执行
- `runToolsSerially()`: 非并发工具串行执行

**StreamingToolExecutor**（`src/services/tools/StreamingToolExecutor.ts`）：
- 流式接收工具调用（API还在流式输出时就开始执行）
- 跟踪每个工具的状态（queued/executing/completed/yielded）
- 支持sibling abort（一个Bash工具出错时杀死兄弟子进程）
- 结果按工具接收顺序buffered，保证顺序一致性

内置工具30+个，按功能分组：
- **文件操作**：FileRead、FileWrite、FileEdit（sed-like）、Glob、Grep
- **Shell**：Bash、PowerShell、REPL
- **Agent**：AgentTool（子agent）、TaskCreate/List/Get/Update/Stop/Output
- **MCP**：MCPTool（动态代理）、ListMcpResources、ReadMcpResource、McpAuth
- **搜索**：WebSearch、WebFetch、ToolSearch
- **协作**：TeamCreate/Delete、SendMessage
- **特殊**：EnterPlanMode/ExitPlanMode、Sleep、Brief、SyntheticOutput（结构化输出）、NotebookEdit

### 3. Session Management（`src/services/compact/` + `src/utils/sessionStorage.ts`）

**四级上下文压缩策略**（从轻到重）：

1. **Microcompact**（缓存编辑压缩）：对大型工具结果（如文件内容）进行缓存编辑。API返回 `cache_creation_input_tokens` 和 `cache_read_input_tokens`，利用prompt caching减少重复token。

2. **Snip Compact**（`feature('HISTORY_SNIP')`）：在query循环中裁剪旧消息。保留protected tail（最近的assistant消息），中间部分用摘要替换。在microcompact之前运行。

3. **Auto Compact**（`src/services/compact/autoCompact.ts`）：当token使用接近上下文窗口时触发。通过 `tokenCountWithEstimation()` 估算当前token数，与 `getEffectiveContextWindowSize()` 比较。触发后调用 `compactConversation()` 使用模型生成摘要。支持连续失败断路器（`consecutiveFailures`）。

4. **Reactive Compact**（`feature('REACTIVE_COMPACT')`）：API返回 `prompt_too_long` 错误时的应急压缩。在autoCompact之后运行，作为最后防线。

**会话持久化**：`recordTranscript()` 将消息序列化到 `~/.claude/sessions/` 目录。支持 `--resume` 恢复。`flushSessionStorage()` 在CCP（Claude Cowork Platform）模式下提前刷盘。

### 4. MCP Client（`src/services/mcp/`）

MCP协议实现位于 `src/services/mcp/`，关键文件：

- **`client.ts`**: `connectToServer()` 和 `fetchToolsForClient()` — 连接MCP服务器并获取工具列表
- **`MCPConnectionManager.tsx`**: React组件，管理MCP服务器生命周期
- **`types.ts`**: 配置schema定义（stdio/sse/sse-ide/http/ws/sdk六种传输方式）

支持六种传输协议：`stdio`（本地进程）、`sse`（HTTP SSE）、`sse-ide`（IDE扩展）、`http`、`ws`（WebSocket）、`sdk`（内部SDK）。

配置层级：`local` → `user` → `project` → `dynamic` → `enterprise` → `claudeai` → `managed`，每层可覆盖上层。

OAuth支持：MCP服务器可以通过 `oauth` 配置字段声明OAuth认证需求，Claude Code自动处理OAuth流程（`McpOAuthConfigSchema`）。

MCPTool是动态代理工具 — 它不预先知道有哪些工具，而是在运行时从MCP服务器获取工具列表后动态创建工具定义。

### 5. Permission System（`src/hooks/toolPermission/` + `src/components/permissions/`）

权限系统围绕 `CanUseToolFn` 函数签名构建：

```typescript
type CanUseToolFn = async (
  tool, input, toolUseContext, assistantMessage, toolUseID, forceDecision
) => PermissionResult
```

权限模式：
- **default**: 每次工具调用都询问用户（通过Ink TUI对话框）
- **auto**: 自动批准安全操作，危险操作仍询问
- **bypass**: 跳过所有权限检查（`--dangerously-skip-permissions`）
- **plan**: 计划模式下限制工具使用

权限规则存储在 `ToolPermissionContext` 中：
- `alwaysAllowRules`: 白名单规则（按来源：command/config/cli）
- `alwaysDenyRules`: 黑名单规则
- `alwaysAskRules`: 强制询问规则

UI组件位于 `src/components/permissions/`，每种工具类型有独立的权限对话框（BashPermissionRequest、FileEditPermissionRequest等），支持差异展示和命令预览。

**拒绝重试机制**：`SDKPermissionDenial` 记录所有拒绝事件，包含工具名、输入和use_id。QueryEngine中通过 `wrappedCanUseTool` 包装canUseTool来收集这些数据。

### 6. Hook System（`src/utils/hooks.ts`）

Hook系统支持20+种生命周期事件：

**核心Hook事件**：
- `PreToolUse` / `PostToolUse` / `PostToolUseFailure` — 工具调用前后
- `PreCompact` / `PostCompact` — 压缩前后
- `SessionStart` / `SessionEnd` — 会话开始/结束
- `Stop` / `StopFailure` — Agent停止
- `SubagentStart` / `SubagentStop` — 子agent
- `Notification` — 通知事件
- `PermissionDenied` — 权限拒绝
- `ConfigChange` / `CwdChanged` / `FileChanged` — 环境变化

Hook实现为shell命令，通过 `spawn()` 执行。支持两种输出格式：
- **Sync JSON output**: 单次JSON输出，直接作为hook结果
- **Async JSON output**: 持续JSON流输出（通过stdin接收事件）

Hook可以返回 `PromptResponse` 来修改系统提示词（用于动态注入上下文）或 `PermissionRequestResult` 来干预权限决策。

Hook配置通过frontmatter格式注册在 `CLAUDE.md` 文件中（`registerFrontmatterHooks`），也支持 `settings.json` 中的配置。

### 7. Subagent/Teammate（`src/tools/AgentTool/` + `src/tasks/`）

**AgentTool**（`src/tools/AgentTool/`）支持两种子agent模式：

1. **Named Agent**（`subagent_type` 指定）：从 `.claude/agents/` 目录或内置agent定义加载
2. **Fork Agent**（`feature('FORK_SUBAGENT')`）：省略 `subagent_type` 时触发隐式分叉，子agent继承父agent的完整上下文和系统提示词

**forkSubagent.ts** 的关键设计：
- Fork子agent的消息前缀使用 `FORK_PLACEHOLDER_RESULT` 占位符，确保所有fork子agent生成**字节级相同的API请求前缀**，实现prompt cache共享
- 防递归保护：通过检测 `FORK_BOILERPLATE_TAG` 标签阻止嵌套fork
- 与coordinator模式互斥

**子agent执行**（`runAgent.ts`）：
- 每个子agent创建独立的 `QueryEngine` 实例
- 通过 `createSubagentContext()` 创建隔离的上下文（工具集、权限模式、文件缓存）
- MCP连接按需建立（`connectToServer`）
- 权限模式支持 `bubble`（上浮到父agent的终端）和 `default`

**后台任务系统**（`src/tasks/`）：
- `LocalAgentTask`: 本地子agent任务
- `DreamTask`: 异步"做梦"任务（后台自主思考）
- `RemoteAgentTask`: 远程agent任务
- `InProcessTeammateTask`: 进程内队友
- `LocalShellTask`: 本地shell任务

## 关键技术实现

### Token管理和上下文窗口控制

三层token管理：

1. **估算层**（`src/utils/tokens.ts`）：`tokenCountWithEstimation()` — 优先使用API返回的usage数据，否则使用字符估算（~4 chars/token）
2. **预算层**（`src/query/tokenBudget.ts`）：`feature('TOKEN_BUDGET')` 启用后，支持 `+500k` 自动续费机制，通过 `taskBudget.remaining` 跨压缩边界追踪
3. **压缩层**：四级压缩策略（见上文），`getEffectiveContextWindowSize()` 返回 `contextWindow - maxOutputTokensForSummary`

**工具结果大小限制**：`applyToolResultBudget()` 在每次query循环开始时检查工具结果大小，对超大结果进行内容替换。`maxResultSizeChars` 可按工具配置。

### 流式输出实现

API调用层（`src/services/api/claude.ts`）使用 `@anthropic-ai/sdk` 的流式接口：

```typescript
const stream = await anthropic.messages.beta.stream(params)
for await (const event of stream) {
  // 处理 content_block_start/delta/stop, message_start/delta/stop
}
```

流式事件通过 `AsyncGenerator<SDKMessage>` 向上传递。`StreamingToolExecutor` 在流式接收工具调用时就开始并行执行，不等流结束。

### SDK模式（-p）vs 交互模式的差异

- **SDK模式**：使用 `QueryEngine` 类直接调用 `submitMessage()`，不需要Ink TUI。所有UI操作（权限对话框等）通过 `structuredIO` 处理
- **交互模式**：通过 `main.tsx` 启动Ink React应用，消息通过Ink渲染到终端
- SDK模式自动设置 `isNonInteractiveSession = true`，影响权限行为（`shouldAvoidPermissionPrompts`）
- `feature('BG_SESSIONS')` 启用后，SDK模式支持 `--bg` 后台运行，通过 `~/.claude/sessions/` 注册

### 并发和安全沙箱机制

**工具并发**：
- `partitionToolCalls()` 根据 `isConcurrencySafe` 标记分区
- 并发安全工具（如FileRead、Glob、Grep）可以并行执行，最大并发数由 `CLAUDE_CODE_MAX_TOOL_USE_CONCURRENCY` 控制（默认10）
- 非并发安全工具（如Bash、FileWrite）串行执行

**安全沙箱**：
- `src/utils/sandbox/`: 沙箱模式实现
- `--sandbox-toggle` 命令切换沙箱
- 沙箱模式下Bash工具在受限环境中执行
- `Scratchpad`（`isScratchpadEnabled`）: 独立的临时文件目录

## 与SI项目的对比借鉴点

### 值得SI借鉴的设计

1. **QueryEngine类抽象**：将会话状态、消息历史、token追踪封装为独立类，支持多turn和会话恢复。SI当前缺少这种会话级抽象。

2. **StreamingToolExecutor的流式并行**：不等API流结束就开始执行工具，显著减少延迟。SI目前是等API返回完整响应后才执行工具。

3. **四级上下文压缩策略**：特别是microcompact（缓存编辑）和snip compact的分层设计。SI目前只有简单的compact。

4. **Feature Flag DCE**：用feature()函数在构建时移除实验代码，保证生产构建的体积和安全性。SI可以用类似方式管理实验功能。

5. **快速路径启动分流**：CLI入口的多层快速路径设计，避免不必要的模块加载。SI启动时间可以借鉴。

6. **工具结果大小预算**：`applyToolResultBudget()` 在每次循环开始时裁剪过大的工具结果，防止上下文爆炸。SI应该实现类似机制。

7. **Fork Agent的prompt cache优化**：所有fork子agent生成字节级相同的请求前缀，最大化prompt cache命中率。

### SI的差异/优势

1. **SI有更丰富的项目分析能力**：Claude Code是通用编程助手，SI专注于Android/代码分析领域，有领域特定的工具和提示词
2. **SI的知识库同步机制**：自动同步到GitHub Pages，Claude Code没有类似功能
3. **SI的Cron定时任务**：支持定时分析任务，Claude Code的cron是通过ScheduleCronTool实现的

### 具体改进建议

1. **实现会话级QueryEngine**：将SI的消息管理、工具执行、上下文压缩封装为一个类，支持多turn对话和会话恢复
2. **工具执行流式化**：在API流式响应时就开始执行已完成的工具调用
3. **添加工具结果大小限制**：对FileRead等工具的返回内容设置maxResultSizeChars
4. **实现microcompact**：利用API的缓存编辑功能压缩大型工具结果

## 代码质量评估

### 代码组织

- **高度模块化**：每个工具独立目录，职责清晰
- **类型系统完善**：大量使用TypeScript类型推导和Zod schema验证
- **配置与代码分离**：系统提示词、常量、schema都有独立文件

### 错误处理

- **分类错误处理**：`categorizeRetryableAPIError()` 对API错误进行分类，区分可重试和不可重试错误
- **Fallback机制**：`FallbackTriggeredError` + maxOutputTokensRecovery实现API降级
- **断路器**：autoCompact的 `consecutiveFailures` 防止无限重试
- **Graceful shutdown**：全局注册cleanup handler，确保进程退出时资源释放

### 测试策略

反编译源码中**没有测试文件**（`.test.ts` / `.spec.ts` 为0个），这是反编译的限制。但从代码结构可以看出：
- 大量pure function设计（便于单元测试）
- 依赖注入模式（`QueryDeps`接口，`productionDeps()`默认实现）
- Feature flag使得测试可以独立启禁功能模块

### 代码风格

- 使用Biome作为linter/formatter
- 大量ESLint自定义规则（`custom-rules/no-top-level-side-effects`等）
- 注释质量高，特别是设计决策的说明（如thinking blocks规则、fork cache优化等）

## 关联分析

- [claude-context](../entities/claude-context.md) — Claude的上下文管理策略
- [everything-claude-code](../entities/everything-claude-code.md) — Claude Code功能全景分析
- [OpenClaw](../entities/OpenClaw.md) — OpenClaw的Agent架构对比
