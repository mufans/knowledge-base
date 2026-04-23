# OpenClaw 源码分析

> 基于 v2026.4.9 本地安装路径 `/opt/homebrew/lib/node_modules/openclaw/` 的源码级分析

## 1. 项目结构

```
openclaw/
├── openclaw.mjs          # CLI 入口
├── dist/                 # 编译产物（Rollup chunk splitting，1000+ 文件）
│   ├── entry.js          # 进程入口（respawn 策略、TLS 环境注入）
│   ├── index.js          # 模块导出入口
│   ├── extensions/       # 110+ 内置扩展（channel/provider/tool）
│   │   ├── telegram/     # Telegram 渠道
│   │   ├── discord/      # Discord 渠道
│   │   ├── slack/        # Slack 渠道
│   │   ├── whatsapp/     # WhatsApp 渠道
│   │   ├── feishu/       # 飞书渠道
│   │   ├── memory-core/  # 记忆核心引擎
│   │   ├── memory-lancedb/ # 向量搜索
│   │   ├── memory-wiki/  # Wiki 记忆
│   │   ├── browser/      # 浏览器控制
│   │   ├── acpx/         # ACP 适配器
│   │   ├── ollama/       # Ollama provider
│   │   ├── openai/       # OpenAI provider
│   │   └── ...           # 100+ 更多扩展
│   ├── bundled/          # 内置插件（boot-md, bootstrap-extra-files 等）
│   ├── plugin-sdk/       # 插件 SDK 导出
│   ├── cli/              # CLI 子命令
│   ├── infra/            # 基础设施（安全审计、边界文件读取等）
│   ├── mcp/              # MCP 集成
│   └── agents/           # Agent 相关配置
├── skills/               # 内置技能（40+ 个 SKILL.md）
├── docs/                 # 文档
├── assets/               # 静态资源
└── package.json          # npm 包定义
```

## 2. Gateway 架构

### 2.1 入口与进程管理

**文件**: `dist/entry.js`

入口负责进程 respawn 策略：
- 自动注入 `--disable-warning=ExperimentalWarning`
- 自动配置 `NODE_EXTRA_CA_CERTS`（macOS 证书链）
- 子进程信号桥接（SIGTERM/SIGINT 传递）

```javascript
// src/entry.respawn.ts
function buildCliRespawnPlan(params = {}) {
  // 检查是否需要 respawn（TLS 证书、Node 警告抑制）
  if (!needsRespawn) return null;
  return { argv: [...childExecArgv, ...argv.slice(1)], env: childEnv };
}
```

### 2.2 插件注册表

**文件**: `dist/plugin-registry-DQcDEPca.js`, `dist/registry-oEQkgqjm.js`

插件系统采用**注册表模式**，运行时动态加载：
- `getChannelPlugin(channelId)` 获取渠道插件实例
- `getGlobalPluginRegistry()` 获取全局注册表
- `loadPluginManifestRegistry()` 加载插件清单

渠道插件清单在 `dist/channel-catalog.json` 中定义，包含 30+ 渠道的元数据。

### 2.3 消息路由（Dispatch Pipeline）

**文件**: `dist/dispatch-CFaSnCVe.js`

核心路由流程：
1. **入站去重**：基于 `provider|accountId|sessionScope|peerId|threadId|messageId` 的缓存 key
2. **会话路由**：`resolveReplyRoutingDecision()` 决定回复路由
3. **对话绑定**：`resolveConversationBindingRecord()` 维持会话-渠道映射
4. **Hook 触发**：`triggerInternalHook()` 触发插件钩子
5. **Agent 调用**：进入 `runEmbeddedPiAgent()` 执行

```javascript
// 入站去重 key 构建
function buildInboundDedupeKey(ctx) {
  const provider = normalizeOptionalLowercaseString(ctx.OriginatingChannel) || "";
  const messageId = normalizeOptionalString(ctx.MessageSid);
  return [provider, accountId, sessionScope, peerId, threadId, messageId]
    .filter(Boolean).join("|");
}
```

## 3. Agent 运行时

### 3.1 核心运行器

**文件**: `dist/agent-runner.runtime-BhSS0F7i.js`

Agent 运行时是整个系统最复杂的模块，负责：
- **System Prompt 组装**：workspace 文件 + skills + 工具定义
- **模型调用**：支持 fallback 链、模型切换、auth profile
- **回复处理**：流式/块式、媒体路径归一化、去重、线程绑定
- **上下文管理**：token 估算、compaction、context window guard

关键依赖：`@mariozechner/pi-coding-agent`（SessionManager 类）

### 3.2 Workspace 上下文注入

**文件**: `dist/workspace-4tKa-1bN.js`

识别并注入的 workspace 文件：
```javascript
const DEFAULT_AGENTS_FILENAME = "AGENTS.md";
const DEFAULT_SOUL_FILENAME = "SOUL.md";
const DEFAULT_TOOLS_FILENAME = "TOOLS.md";
const DEFAULT_IDENTITY_FILENAME = "IDENTITY.md";
const DEFAULT_USER_FILENAME = "USER.md";
const DEFAULT_HEARTBEAT_FILENAME = "HEARTBEAT.md";
const DEFAULT_BOOTSTRAP_FILENAME = "BOOTSTRAP.md";
const DEFAULT_MEMORY_FILENAME = "MEMORY.md";
```

加载机制：
- 文件边界检查（防止路径穿越）
- 文件大小限制（2MB）
- 内容缓存（基于 `dev:ino:size:mtimeMs` 指纹）
- Frontmatter 剥离（`---` 分隔的 YAML 头部）
- 子 Agent/Cron 会话中跳过 MEMORY.md（安全隔离）

### 3.3 上下文窗口保护

**文件**: `dist/context-window-guard-BrkZ7mmP.js`

```javascript
const CONTEXT_WINDOW_HARD_MIN_TOKENS = 16_000;
const CONTEXT_WINDOW_WARN_BELOW_TOKENS = 32_000;

function evaluateContextWindowGuard(params) {
  return {
    tokens,
    shouldWarn: tokens > 0 && tokens < warnBelow,  // < 32K 警告
    shouldBlock: tokens > 0 && tokens < hardMin,    // < 16K 阻止
  };
}
```

Context window 从三个来源解析：`models.providers[].models[].contextTokens` → 模型元数据 → 默认值。可通过 `agents.defaults.contextTokens` 强制上限。

## 4. Skill 系统

### 4.1 Skill 发现与加载

**文件**: `dist/skills-U3bcZf5o.js`

Skill 发现路径：
1. **Bundled skills**：`package_root/skills/` 目录
2. **Workspace skills**：`~/.openclaw/workspace/skills/` 目录
3. **Plugin skills**：通过插件 manifest 注册

加载流程：
```javascript
function loadSingleSkillDirectory(params) {
  const skillFilePath = path.join(params.skillDir, "SKILL.md");
  const raw = readSkillFileSync({ filePath: skillFilePath, maxBytes });
  const frontmatter = parseFrontmatter(raw);  // 解析 YAML frontmatter
  const name = frontmatter.name || path.basename(params.skillDir);
  const description = frontmatter.description;
  return { name, description, filePath, baseDir, source };
}
```

每个 skill 的 SKILL.md 必须包含 `name` 和 `description`（frontmatter 或文件名回退）。

### 4.2 Skill 注入 System Prompt

**文件**: `dist/skills-U3bcZf5o.js` → `formatSkillsForPrompt()`

Skills 以 XML 格式注入 system prompt：
```xml
<available_skills>
  <skill>
    <name>1password</name>
    <description>Set up and use 1Password CLI...</description>
    <location>/opt/homebrew/.../skills/1password/SKILL.md</location>
  </skill>
  ...
</available_skills>
```

Agent 收到用户消息后，按需使用 `read` 工具加载完整 SKILL.md 内容。

### 4.3 Skill 安全扫描

**文件**: `dist/skill-scanner-C03dgwPs.js`

安装前对 skill 文件进行安全扫描，检测规则：

| 规则 ID | 严重级别 | 检测内容 |
|---------|---------|---------|
| `dangerous-exec` | critical | `exec/spawn` + `child_process` |
| `dynamic-code-execution` | critical | `eval()` / `new Function()` |
| `crypto-mining` | critical | stratum 协议、xmrig 等 |
| `suspicious-network` | warn | 非标准端口 WebSocket |
| `potential-exfiltration` | warn | 文件读取 + 网络发送 |
| `obfuscated-code` | warn | 十六进制/Base64 混淆 |
| `env-harvesting` | critical | `process.env` + 网络发送 |

限制：最多 500 文件、单文件 1MB。

### 4.4 ClawHub 集成

**文件**: `dist/clawhub-BFjxm1oA.js`, `dist/clawhub-DExQ87KK.js`

ClawHub 是 skill/插件的分发平台：
- **规格解析**：`clawhub:name@version`
- **完整性校验**：SHA-256 hash 验证（整体 archive 或逐文件）
- **下载安装**：JSZip 解压 + 安装策略
- **兼容性检查**：gateway 版本、plugin API range
- **错误码**：`PACKAGE_NOT_FOUND`, `VERSION_NOT_FOUND`, `ARCHIVE_INTEGRITY_MISMATCH` 等

## 5. Cron/定时任务系统

### 5.1 任务调度

**文件**: `dist/schedule-SK1QQumZ.js`, `dist/heartbeat-runner-B1G6t3fn.js`

调度实现：
- 使用 `croner` 库解析 cron 表达式
- Cron 任务创建 **isolated session**（独立会话）
- Session freshness 评估决定是否复用或新建会话

```javascript
function resolveCronSession(params) {
  const entry = store[params.sessionKey];
  if (!params.forceNew && entry?.sessionId) {
    if (evaluateSessionFreshness({ updatedAt: entry.updatedAt, now: params.nowMs, policy: resetPolicy }).fresh) {
      return { sessionId: entry.sessionId, isNewSession: false };
    }
  }
  return { sessionId: crypto.randomUUID(), isNewSession: true };
}
```

### 5.2 Task Registry

**文件**: `dist/task-registry-BxgEZwQl.js`

任务状态管理使用 **SQLite**（`node:sqlite`）：
- 状态路径：`~/.openclaw/state/tasks/runs.sqlite`
- 任务状态：`pending` → `running` → `succeeded`/`failed`/`timed_out`/`cancelled`/`lost`
- 支持通知策略：`silent`（静默）、`state_changes`（状态变更通知）
- 自动投递：终端状态自动投递到配置的 delivery channel

TaskFlow 扩展：`~/.openclaw/state/flows/registry.sqlite`，支持多步骤编排（`single_task` / `managed`）。

### 5.3 Heartbeat 机制

**文件**: `dist/heartbeat-runner-B1G6t3fn.js`, `dist/heartbeat-fvllvegq.js`

Heartbeat 是更灵活的"软 cron"：
- 读取 `HEARTBEAT.md` 中的检查项
- 支持 **活跃时段**（`activeHours`），避免夜间打扰
- 系统事件队列（`system-events-CZI_VaP5.js`）
- HEARTBEAT_TOKEN（`HEARTBEAT_OK`）静默回复
- 可通过 `requestHeartbeatNow()` 主动触发

```javascript
function isWithinActiveHours(cfg, heartbeat, nowMs) {
  if (!active) return true;
  // 支持跨午夜时段（如 22:00 - 08:00）
  if (endMin > startMin) return currentMin >= startMin && currentMin < endMin;
  return currentMin >= startMin || currentMin < endMin;
}
```

## 6. MCP 集成

**文件**: `dist/mcp/plugin-tools-serve.js`

OpenClaw 作为 **MCP Server** 暴露插件工具：
```javascript
const server = new Server({ name: "openclaw-plugin-tools", version: VERSION }, 
  { capabilities: { tools: {} } });

server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: tools.map(tool => ({
    name: tool.name,
    description: tool.description,
    inputSchema: resolveJsonSchemaForTool(tool)
  }))
}));

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const tool = toolMap.get(request.params.name);
  const result = await tool.execute(`mcp-${Date.now()}`, request.params.arguments);
  return { content: result.content };
});
```

使用 `@modelcontextprotocol/sdk`，通过 stdio transport 运行。这让 Claude Code 等 ACP 客户端可以调用 OpenClaw 注册的工具（如 memory_recall、memory_store）。

## 7. Plugin/Channel 系统

### 7.1 Channel 抽象

**文件**: `dist/channel-catalog.json`

每个 channel 是独立 npm 包（`@openclaw/telegram` 等），通过 `openclaw.channel` manifest 字段声明元数据：
```json
{
  "channel": {
    "id": "telegram",
    "label": "Telegram",
    "blurb": "...",
    "markdownCapable": true,
    "aliases": ["tg"]
  }
}
```

### 7.2 内置扩展

`dist/extensions/` 包含 110+ 扩展，分类：

| 类型 | 数量 | 示例 |
|------|------|------|
| Channel | ~25 | telegram, discord, slack, whatsapp, feishu, qqbot |
| Provider | ~40 | openai, anthropic, google, ollama, deepseek, qwen |
| Tool | ~15 | browser, memory-core, diffs, webhooks |
| Capability | ~30 | speech-core, video-generation-core, media-understanding |

每个扩展有 `runtime-api.js` sidecar，gateway 启动时加载。

### 7.3 消息格式化

各渠道的 Markdown 能力不同，OpenClaw 自动适配：
- `isMarkdownCapableMessageChannel()` 检测渠道能力
- Discord/WhatsApp：不使用 markdown 表格，用 bullet list 替代
- Discord 链接：`<url>` 抑制 embed

## 8. Subagent 系统

### 8.1 Session Fork

**文件**: `dist/session-fork.runtime-BPG2RZVI.js`

子 Agent 通过 session fork 创建：
```javascript
function forkSessionFromParentRuntime(params) {
  const manager = SessionManager.open(parentSessionFile);
  const leafId = manager.getLeafId();
  // 尝试创建分支会话（共享前缀，节省 prefix cache）
  const sessionFile = manager.createBranchedSession(leafId);
  // 如果失败，创建全新会话并记录 parent 引用
  const header = {
    type: "session", version: CURRENT_SESSION_VERSION,
    id: sessionId, timestamp,
    parentSession: parentSessionFile  // 父会话引用
  };
}
```

### 8.2 子 Agent 注册表

**文件**: `dist/subagent-registry.runtime-CJS7hAJZ.js`

管理子 Agent 生命周期：
- 运行时插件加载：`ensureRuntimePluginsLoaded()`
- 上下文引擎初始化：`ensureContextEnginesInitialized()`
- 子 Agent 结果自动 announce 回父会话

## 9. 安全机制

### 9.1 文件边界检查

**文件**: `dist/boundary-file-read-D4i4p3X_.js`

所有文件读取都经过边界检查，防止路径穿越：
- `openBoundaryFile()` 确保文件在允许的根目录内
- `isPathInside()` 相对路径检查（无 `..` 前缀）
- `isPathInsideWithRealpath()` 处理符号链接

### 9.2 Workspace 文件安全

- MEMORY.md 在 subagent/cron 会话中不加载（防隐私泄露）
- Workspace 文件最大 2MB
- Frontmatter 剥离防止 YAML 注入

### 9.3 环境变量保护

从 `.env` 文件加载时，阻止以下环境变量被覆盖：
- `OPENCLAW_*` 运行时控制变量
- 浏览器控制覆盖变量
- 跳过服务器变量

## 10. 数据流总结

```
用户消息 → Channel Plugin (inbound)
  → Dispatch Pipeline (去重、路由、Hook)
  → Session Store (会话查找/创建)
  → Agent Runtime (system prompt 组装)
    ├── Workspace Files (SOUL/USER/AGENTS/TOOLS/MEMORY)
    ├── Skills (XML injection)
    ├── Plugin Tools (MCP/Channel/Provider)
    └── Context Window Guard
  → LLM API (with fallback chain)
  → Reply Pipeline (格式化、去重、线程绑定)
  → Channel Plugin (outbound)
  → 用户收到回复
```
