# DeepSeek Harness（dsh）深度分析报告

> 分析对象：本地 git 仓库 `/Users/liujun/agentProj/deepseek-harness`（origin = https://github.com/deepseek-ai/deepseek-harness.git）
> 当前版本：`0.1.0-rc.5`（developer preview，MIT 协议），master 分支，约 1.2 万次提交、7400 余个被跟踪文件
> 分析日期：2026-08-13

---

## 1. 项目概述

### 1.1 解决什么问题

DeepSeek Harness（命令行名 `dsh`）是 DeepSeek AI 开源的一个 **agent harness（智能体运行框架/骨架）**。它解决的核心问题是：**agent 的"骨架"应该与"血肉"彻底解耦**——模型适配、工具、会话持久化、执行循环、权限策略，每一个部件都应该是可替换的插件，而不是写死在核心里的特权代码。

官方 README 第一句话就是定位：*"an open-source agent harness... It uses an architecture where **everything is a plugin**, and is powered by Cordis."*（`README.md:5-7`）。

### 1.2 目标用户

- **插件开发者**：把自定义能力（工具、模型 provider、策略）挂到标准扩展点上，用 `dsh-plugin` topic 发布（`README.md:40`）。
- **想要本地/私有部署 Agent 的团队**：`npx @deepseek-ai/dsh web` 一条命令起 Web UI（`README.md:20`）。
- **用 Python 做 Agent 的开发者**：通过 `python/` 下的 SDK 把 dsh 当子进程驱动。
- **研究插件化架构的工程师**：Cordis 范式本身是论文级别的设计（[A Programming Paradigm for Spatiotemporal Composability](https://github.com/cordiverse/paper)）。

### 1.3 agent harness 与 agent framework 的区别

这是理解本项目的关键。**Framework（框架）**（如 LangChain、LangGraph）是"我在框架里写业务代码"，框架替你编排控制流；**Harness（骨架/托架）**是"我提供可替换的运行环境"，业务方通过**插件挂载**扩展，而不是通过继承/回调写死在框架内。

dsh 里这一区别体现在 `docs/architecture.md:11-13`：*"There is no privileged core to patch: you extend dsh by mounting a plugin beside the others, and registrations are effects that unwind when their plugin unloads."* —— 没有特权内核，扩展 = 挂插件，注册 = 可逆 effect。

### 1.4 项目规模与活跃度

- git 历史约 **12293 次提交**、约 **7412 个被跟踪文件**（含 `node_modules` 则 7 万+，任务书提醒不要误读）。
- 近期提交显示 release 节奏：`0.1.0-rc.3` → `0.1.0-rc.5`，以及 `npm-public` 发布（`git log`）。
- 包名统一 `@deepseek-ai/dsh-*`，`@deepseek-ai/cordis` 是每个 harness 包的 peerDependency。

---

## 2. 技术栈

### 2.1 语言与运行时

- **TypeScript**（严格模式，`strict: true` + `noImplicitAny`），ESM（`"type": "module"`）。
- **Node.js** `^22.19.0 || >=24.0.0`（CI 覆盖 22.19 / 24 / 26，`package.json:8-10`）。

### 2.2 框架：Cordis（vendored）

Cordis 是核心依赖，采用**vendor 方式**内嵌在 `vendor/` 目录（`vendor/cordis`、`vendor/loader`、`vendor/schemastery`、`vendor/cosmokit` 等），同步流程见 `vendor/README.md`。

Cordis 的五个核心概念（`docs/cordis-primer.md:7-13`）：
1. **插件 = 实现 Service 的对象**（函数插件带 `inject`/`apply`，或 `Service` 子类）。
2. **Context = 服务仓库**，通过 `ctx.<key>` 按 key 取服务，不 import 具体实现。
3. **`inject` 声明依赖**，加载顺序由服务依赖表达，而非手工排序。
4. **Typed Events** 通信，`emit` / `waterfall` / `parallel` / `serial` 四种分发模式。
5. **注册即可逆 effect**（`ctx.effect()` / `ctx.on()`），卸载时自动 unwind。

### 2.3 构建与工具链

- **包管理**：pnpm workspaces（`pnpm@11.7.0`），workspace 覆盖 `packages/*/*`、`apps/*`、`native/*`、`vendor/*`、`website`（`package.json:11-18`）。
- **构建**：`tsc -b` 双 aggregate（Host/Client）+ `tsdown` 打包，Web 走 Vite（`package.json:20-24`）。
- **Lint**：**oxlint**（`1.76.0`），而非 ESLint；配合 `oxlint-tsgolint`。
- **测试**：**vitest** + `@vitest/coverage-v8`；快照测试；Playwright 做 Web GUI 测试。
- **其它质量门**：jscpd（克隆检测）、knip（未用导出检测）、publint（发布检查）、lefthook（Git hooks）。
- **TypeScript 布局**：Host/Client 两个 aggregate（`tsconfig.host.json` / `tsconfig.client.json`），原因是两端对 Cordis `Context` 的声明合并同名不同服务，合并进一个 program 会冲突（`docs/development.md:56`）。
- **关键内部库**：`schemastery`（vendored，声明式 JSON Schema 校验，工具配置即 schema）；**typert**（`packages/typert/`，类型图生成器 + runtime 注册表，Host 构建期生成 Remote 投影，支撑 `@Remote` RPC 网关）；`cosmokit`（vendored 基础工具）。

### 2.4 依赖管理策略

一个显著工程决策：**Cordis 是 vendored 而非 npm 依赖**，且被 rescope 到 `@deepseek-ai/*` scope（`docs/rescope.md`）。根 `AGENTS.md` 声明：*"Prefer maintained dependencies over hand-rolling"* 与 *"explicit > implicit at package boundaries"* 并存——外部依赖能真正删掉自有代码和测试时才引入，否则宁可手写；包边界上的默认值永远是显式的 `resolve(request): Spec` 步骤，而非藏在 `run()` 里的 `?? default`。

### 2.5 python/ 目录与 native/ 目录

- **`python/`**：独立的 Python SDK（`python/README.md`）。`python/sdk/` 是 `deepseek-harness-sdk`（高层 turns API + 底层 JSON-RPC 客户端），`python/sdk-runtime/` 是 `deepseek-harness-runtime-bin`（打包的运行时二进制 + 默认 agent 配置）。**边界**：Python 端通过 stdio 上的 newline-delimited JSON-RPC 把 dsh 当子进程驱动，不共享 Node 代码。
- **`native/`**：Landlock 沙箱 launcher（`native/landlock-run/`），`@deepseek-ai/node-addon-landlock-run`，负责"自限制后 exec"的进程 confinement，由独立 release 流程发布（`native/README.md`）。

---

## 3. 架构设计

### 3.1 Monorepo 结构

顶层布局（`package.json:11-18` + 目录树）：

| 目录 | 作用 |
|---|---|
| `packages/<group>/<pkg>/` | 主体，按组组织（`core`/`llm`/`session`/`web`/`fs`/`shell`/`mcp` 等 50+ 组） |
| `apps/cli` | `dsh` 命令 launcher（`@deepseek-ai/dsh`） |
| `apps/web` | Web 前端（Vite） |
| `vendor/` | 内嵌的 Cordis 家族源码 |
| `native/` | Landlock 沙箱 |
| `python/` | Python SDK + runtime |
| `examples/` | 可运行的 cordis.yml 叶子 |
| `website/` | VitePress 文档站 |
| `docs/` | 架构/子系统/手册（中英双语） |
| `scripts/` | 大量 verify-* 质量门脚本 |

### 3.2 "一切皆插件"的具体机制

一个正在运行的 `dsh` 是一棵**在启动时从有序分层组合出来的插件树**（`docs/architecture.md:15-37`）：

- **Profile**（profile）：存放在 Harness home 的具名组合，列出它 stack 的 bundle、安装的树外插件、以及用户自己的 `cordis.patch.yml`。`web` 和 `headless` 是出厂模板。
- **Bundle**（bundle）：Cordis 配置行的分发格式，声明在 `package.json` 的 `dsh.bundle` 字段。
- 分层顺序：空条目列表 → 按 profile 声明的 bundle 顺序 → profile 的 `cordis.patch.yml` → home 级 → `--patch` overlay。

三个出厂 bundle 是 `dsh-base`（模型适配、工具、持久化、沙箱、审批、设置、凭证、遥测）、`dsh-web-app`（浏览器应用）、`dsh-headless`（一次性 runner）。

核心包对 Cordis 树的贡献（`docs/architecture.md:43-51`）：

| 包 | 拥有 | `ctx` key |
|---|---|---|
| `core/session` | append-only `SessionEvent` 日志 + 内存存储 | `ctx.sessions` |
| `core/system-prompt` | 提示段落与工具 schema 组装 | `ctx.systemPrompt` |
| `core/tools` | 作用域工具注册表 + 受保护的执行管线 | `ctx.tools` |
| `core/agent` | `Agent` 接口、活注册表、`agent/*` 事件 | `ctx.agents` |
| `core/agent-loop` | 默认 driver 实现 | `ctx.agentLoop` |
| `core/scope` | 每 agent 的作用域注册原语 | library，无 key |
| `llm/llm` | 消息/流词汇 + 适配器 seam | `ctx.llm` |

### 3.3 能力接缝（capability seam）

这是 dsh 架构最独特的概念（`docs/glossary.md:9`）：一个 **seam**（可替换能力）由三个角色组成：
- **Service Definition**：声明接口的抽象类（如 `ShellExecutor`）。
- **Service Provider**：实现它（如 `dsh-bash-local` / `dsh-bash-sandbox`）。
- **Consumer**：消费它（通常是模型可见的 tool，如 `dsh-tool-bash`）。

因为 filesystem 和 subprocess provider 共享同一个执行世界，把它们指向远程沙箱时，Bash、PTY、LSP 一起移动，无需为 provider 分叉（`docs/architecture.md:102`）。

### 3.4 事件分发模式（扩展点）

事件是 dsh 的扩展点（`docs/architecture.md:55-61`），分三类：
- **Session events**：可持久的事实，追加到日志并通过 `session/event` 广播。
- **Agent events**（`agent/*`）：携带活 `Agent` 的 in-flight 事件。
- **Capability events**（`fs/*`、`tools/*`、`telemetry/*`）：给 seam 附加策略和适配器。

四种分发模式（`docs/cordis-primer.md:19-24`）：

| 模式 | 是否等待 | 分发顺序 | 是否有返回值 |
|---|---|---|---|
| `emit` | 否 | 注册顺序观察 | 无 |
| `waterfall` | 否 | 注册顺序观察 | 有 |
| `parallel` | 是 | 并行 | 无 |
| `serial` | 是 | 注册顺序 | 有 |

`waterfall` 是 around-middleware：监听者收到 `(...args, next)`，`next()` 委托，不调用则短路（`docs/cordis-primer.md:30-34`）。这条语义是 dsh 所有"策略拦截"的基础——`agent/pre-step`、`agent/request`、`llm/stream`、`tools/*` 都是 waterfall。

---

## 4. 核心功能详解

### 4.1 dsh web 是什么

`dsh web` 是 `--profile web` 的别名（`apps/cli/README.md:13`），启动一个本地 Web UI（默认 `http://127.0.0.1:3080`）。它由 `packages/host/`（API gateway + HTTP route server）和 `packages/client/`（浏览器半边：shell、wire、object services、`ui-*` 插件）组成。用户流程：配置模型 key → 选择 workspace → 发起任务，agent 可读写文件、跑命令、委托子任务、维护计划（`docs/user/guide/index.md`）。

### 4.2 Agent 执行流程（turn/step 状态机）

这是最值得深入的部分，实现在 `packages/core/agent-loop/src/agent.ts` 的 `ReactLoopAgent` 类：

- **step** = 一次模型请求 + 它调用的工具；**turn** = 零个或多个 step（`docs/glossary.md:36-38`）。
- 核心状态机字段 `phase`（`agent.ts:38-46`）：`idle` / `maintenance` / `running` 三态，带 `AbortController` 和 `lastTurn`。
- `turn()`（`agent.ts:246-330`）：打开 `turn/start` 事件 → 循环 `preStep` → 追加 `step/start` → `step()` → `step/end` → 判断是否有下一步，直到 `turn/end`。`max-tokens` 是 sticky 的（一旦某步触顶，后续正常完成的 step 不会降级 turn 结果）。
- `step()`（`agent.ts:332-401`）：`buildRequest` → `llm/stream` → 逐 chunk 追加 `assistant/chunk` → `createAssistantMessage` 追加 `assistant/message` → 过滤 `tool-call` block → `executeToolCalls`。
- 消息流入走单一 `Inbox`，`send`/`followup`/`steer`/`inject` 对应不同目标（`next-turn`/`next-step`）和 wakeup 语义（`agent.ts:113-132`）。

### 4.3 工具调用管线（深入机制一）

`packages/core/tools/src/index.ts` 的 `ToolRuntime` 是工具注册表和执行管线的核心：

- **注册**：`register(definition)` 返回精确 disposer（`index.ts:1037`）。作用域分层通过 `ScopedLayers` + `ToolLayer`，支持**作用域注册 shadow 全局注册**、`restrict()`（按 scope 过滤全局工具集）、`guard()`（单调拒绝）。
- **执行管线**（`ToolDefinition`，`index.ts:222`）：每个工具声明 `output.schema`（强制 JSON Schema 校验规范输出）、`execute(args, exec)`（返回 lossless-JSON 值）、可选的 `finalizeContent` / `presentCall` / `presentResult`（纯函数，供 UI 流式渲染和日志回放）。
- **事件瀑布**：`tools/pre-execute`（允许/拒绝/询问）→ `tools/execute`（around 包装，超时/重试/度量）→ `tools/post-execute`（接受/替换/阻断）→ `tools/result`（emit）。前三个是 waterfall，监听者必须 `next()`。
- **Code Mode**：`Config.mode` 支持 `native` / `code` / `both`。`code` 模式下只向模型暴露 `run_code` 一个工具 + 生成的 SDK 提示，模型在程序内调用其它工具（`run_code` 是保留名，`index.ts:1054`）。

### 4.4 会话日志作为唯一事实源（深入机制二）

`docs/architecture.md:94-96` 有一条硬性不变量：**"Model-visible means logged."**——任何到达模型请求的内容都必须能从 session log 重建，运行时 invariant 会断言它。`session.deriveMessages()` 从日志投影模型历史；`assistant/chunk` 原始事件保留回放和 UI 保真度。fork、resume、transcript、telemetry、persistence 全部派生自这条流。

`packages/session/` 组含多个持久化 provider：`session-persistence-jsonl`（append-only 文件）、`session-persistence-sqlite`（`node:sqlite` 行存储，`SCHEMA_VERSION` 单调递增）。SQLite 后端把每个 `SessionEvent` 1:1 映射到一行 `(session_id, seq, type, time, data, ...)`，append = 事务，支持崩溃恢复（中断 turn 关闭）和懒物化。

### 4.5 MCP 支持

`packages/mcp/mcp-client/`（`dsh-mcp-client`）是 MCP 客户端桥接插件：连接外部 MCP server，把其工具注册到 `ctx.tools`，模型看到 `mcp__<serverName>__<rawName>` 这样的命名（与 Claude Code / Codex 同构）。支持 `stdio` 和 `streamable-http` 两种 transport，自动重连（指数退避 + 预算），HMR 热切换。**已知限制**：只桥接了 Tools，Resources/Prompts 尚无 consumer（`mcp-client/README.md:111`）。

### 4.6 并行工具调度（深入机制三）

`packages/core/agent-loop/src/tool-calls.ts` 的 `executeToolCalls` 展示了 dsh 对并发的精细控制：

- 工具通过 `ToolDefinition.isConcurrencySafe` 自报是否可并行；`ctx.tools.executionMode(exec)` 返回 `parallel` 或 `exclusive`。
- `runGroup`（`tool-calls.ts:121`）用**有界滚动池**调度：`maxParallelToolCalls` 控制 in-flight 上限，`exclusive` 调用形成顺序屏障；dispatch 可重叠，但**结果和上下文严格按模型顺序提交**（`commitReady`，`tool-calls.ts:146`）。
- **取消语义**：abort 时停止补充新调用、排空已启动调用、为未启动调用合成 `ABORTED_BEFORE_DISPATCH` 错误结果——保证回放仍有效（`tool-calls.ts:248-259`）。

这套调度器和 `ToolRuntime` 内部暴露的 `TOOL_RUNTIME_SCHEDULER` symbol（`tools/src/index.ts:466`）配合，把"pre-execute 顺序执行、dispatch 并行、finalize 顺序提交"三段拆开，是 agent 并发编排的高质量范本。

### 4.7 LLM 适配器 seam（深入机制四）

`packages/llm/llm/src/index.ts` 的 `LlmRuntime` 定义模型层：抽象类 `LlmAdapter`（`index.ts:180`）只有一个必需方法 `stream(options)`，其余 `providerInfo` / `listModels` / `resolveModel` 均可选。`registerAdapter(providers, adapter)` 注册 provider 路由，`prepareCall` 把一次调用的能力解析与 dispatch 绑定到同一次注册（防 HMR 把 A 适配器的能力结果配到 B 适配器）。`llm/stream` 是 waterfall（`index.ts:64`），中间件可以拦截、重试、路由、或短路流。所有错误规范化为 `LlmError`（`code` 为 `AUTH`/`RATE_LIMIT`/`NO_ADAPTER` 等共享分类）。

### 4.8 插件开发接口

两种插件形态（`packages/AGENTS.md`）：
- **Service 类**：default-export service class。
- **函数插件**：命名导出 `name` / `inject` / `Config` / `apply`，无 default export。

用 `ctx.effect()` / `ctx.on()` / `ctx.waterfall()` 贡献；注册即返回 disposer。cookbook 提供 `adding-a-tool` / `adding-an-llm-adapter` / `adding-a-package` / `adding-a-conversation-node` 四步指南（`docs/architecture.md:129`）。

---

## 5. 与同类项目对比

| 项目 | 定位 | 与 dsh 的差异 |
|---|---|---|
| **Claude Code / OpenAI Codex** | 面向终端用户的产品化 coding agent（闭源） | dsh 是开源骨架，Claude Code/Codex 是完整产品；dsh 的 `hooks/` 组专门桥接 Claude Code/Codex 的 wire-protocol |
| **LangGraph / LangChain** | Python 图编排框架，控制流显式 | dsh 把控制流（agent-loop）也做成可替换插件；dsh 强调持久化日志为事实源、可逆 effect、作用域注册 |
| **OpenClaw** | 另一个 agent harness 生态 | 同属 harness 赛道；dsh 差异化在"一切皆插件 + Cordis 时空可组合范式 + 能力接缝" |
| **Ralph/workflow** | dsh 内置的前台 fresh-agent 工作流策略 | 不是外部项目，是 dsh 用 subagent+workflow 原语组合出的模型工具 |

一句话：**Claude Code / Codex 卖的是"成品 agent"，dsh 卖的是"可以拼出任意 agent 的插件化骨架"**。dsh 的 MCP 客户端甚至刻意对齐了 Claude Code/Codex 的 `mcp__server__tool` 命名，方便生态互通。

补充两个具体的定位证据：

- `packages/hooks/` 组明确职责是"Hook bridges + the shared Claude Code / Codex wire-protocol library"（`packages/README.md:44`）——dsh 不把 Claude Code/Codex 当对手，而是当可桥接的 wire 协议。
- 对比 LangGraph：LangGraph 用显式图（节点+边）表达控制流，dsh 用事件瀑布 + 可替换的 agent-loop 表达控制流；前者适合"流程可枚举"的工作流，后者适合"开放式的 agent 对话 + 工具调用"，且 dsh 的每一步都可被持久化、回放、fork。

---

## 6. 代码质量

### 6.1 测试

- 单元测试 `pnpm run test`（vitest），CI 覆盖门是 `test:coverage`——**要求 packages 每个文件 100% 覆盖**（`AGENTS.md:commands`）。
- 快照测试 `test:snapshot`（keyless 回放 vs 期望输出），真实 API e2e `test:e2e`（无 `DEEPSEEK_API_KEY` 自动跳过）。
- Web 有 Playwright 测试（`test:web`）、性能（`test:web:perf`）、压力（`test:web:stress`）。
- Python SDK 有自己的 pytest（`python/sdk`，`uv run pytest`）。
- 测试政策要求：product-visible 插件必须有非单元的真实组合测试（boot 真实 cordis.yml 走 Loader，只 mock 外部服务）。

### 6.2 文档

质量极高，且**中英双语成对维护**（`.md` + `.zh.md` + `.i18n.yaml` pairing 合约，`docs/AGENTS.md`）。`docs/` 下有 architecture、subsystems（每个子系统一页 type 定义 + 生成的 Cordis API）、cookbook、cordis-tutorial、postmortem、glossary、生成的 tool-catalog/config-catalog/persistence-catalog 等。还有专门的 `doc-sync` 门（verify-md-links、verify-type-equiv、verify-doc-budgets 等十余个脚本）。

### 6.3 CI/CD

`.github/workflows/` 有 15 个 workflow。主 `ci.yml`（937 行）非常精细：
- `node 24 / static`、`node 24 / coverage`、`node 24 / snapshots and artifacts` 三个 enterprise job。
- Node 22.19 / 26 兼容性矩阵。
- Windows 信号：Wine 跑真实 Windows Node 做 blocking gate，另有原生 Windows kernel job。
- Python SDK + runtime 两个 job。
- 自托管 runner 热备（self-hosted standby）+ 失败切换 runbook（`DSH_CI_FAILOVER_*`）。
- 还有 `.gitlab-ci.yml`（说明同时维护 GitLab CI）。

### 6.4 Lint 与其它

oxlint + 大量 `verify-*` 门（`package.json:66-128` 列出了 40+ 个脚本）。值得单独指出几个代表工程水准的门：
- `verify-export-jsdoc`：每个导出必须有 JSDoc（`@param`/`@returns`）。
- `verify-package-invariants`：每个包必须有一个运行时 invariant（检查事件/数据关系，空实现需说明理由）。
- `verify-cordis-config`：cordis.yml 里的裸插件必须出现在 resolver manifest 的 `dependencies`。
- `verify-type-equiv`：文档里粘贴的类型声明必须与源码逐字节等价（防止文档漂移）。
- `verify-doc-budgets`：文档字数预算上限。
- `duplication`（jscpd）：跨文件克隆检测。
- `doc-typecheck`：文档里 fenced `ts` 代码块必须能编译。

lefthook 做 pre-commit（staged 文件 oxlint 修复 + 配对记录校验 + 第三方声明再生成 + 空白检查 + vendor manifest 守卫）和 pre-push（跑 typecheck）。

**评价**：工程化成熟度远超一般开源项目的 preview 阶段——100% 覆盖门、双语言文档合约、跨平台 CI、失败切换预案、40+ 质量门脚本，这些是"生产级团队"才有的投入。风险在于门太多会导致贡献门槛偏高，但这正是项目"pre-release 优先正确基础"定位的体现（`AGENTS.md`）。

---

## 7. 适用场景

### 适合

- 想**定制自己的 coding/agent 工具**的团队（私有部署、自有模型 provider、自定义工具集）。
- **研究 agent 插件化架构**、学习 Cordis 范式的工程师。
- 需要**本地持久化、可重放、可 fork** 会话的应用（session log 为事实源）。
- 想用 **Python 驱动 agent** 的场景（Python SDK 把 dsh 当子进程）。
- 需要**沙箱隔离**（bwrap/Landlock/Seatbelt 三种 backend）执行不可信代码的场景。

### 不适合

- 想要**开箱即用的成品 agent 产品**（还在 developer preview，兼容性破坏警告明确，`README.md:11`）。
- 生产环境**持久化数据不可丢**的场景（SQLite 后端明确"unreleased software; no persisted user data to preserve"，无迁移路径）。
- 对**高吞吐多会话服务**（SQLite `DatabaseSync` 同步阻塞，`session-persistence-sqlite/README.md:58`）。
- 需要 **Resources/Prompts 级别的 MCP** 能力（仅 Tools 被桥接）。

---

## 8. 学习价值（对移动端转 AI Agent 开发者）

1. **插件化架构是"组合优于继承"的极致实践**：无特权内核、注册即 effect、卸载即 unwind。移动端开发者熟悉的依赖注入/模块化，在这里被推到"时空可组合"的高度。
2. **能力接缝（Service Definition / Provider / Consumer）**：这是比"接口 + 实现"更完整的抽象——一个能力必须三角色齐全，换 provider 即换整个产品行为。类比移动端的"数据源 + 仓库 + 使用方"分层，但边界更清晰。
3. **Typed Events + declaration merging**：用 TypeScript 声明合并做类型安全的事件契约，四种分发模式（emit/waterfall/parallel/serial）是并发编排的教科书。
4. **会话日志作为唯一事实源**："model-visible ⟺ logged" 这条不变量对理解可观测、可回放、可恢复的 agent 系统极有价值。
5. **工程化质量门**：100% 覆盖、双语言文档合约、跨平台 CI、失败切换预案——一套可以直接照搬的 monorepo 治理模板。
6. **从状态机学 agent loop**：`ReactLoopAgent` 的 idle/maintenance/running 三态 + AbortController 取消传播，是理解"如何优雅地取消一个进行中的 LLM 调用"的好教材。
7. **并发编排**：`tool-calls.ts` 的"有界并行池 + 顺序提交 + 取消合成结果"模式，直接映射到移动端网络请求并发/串行控制的经验，但语义更严谨（工具通过 `isConcurrencySafe` 自报可并行性）。
8. **写作与文档纪律**：`docs/AGENTS.md` 的文档分层（tutorial/reference、一词一概念、字数预算、双语配对）本身是一套可复用的技术写作方法论，对转型期梳理知识体系很有启发。
9. **质量门即文档**：把 100% 覆盖、JSDoc 强制、类型等价、包 invariant 变成 CI 硬门，让"文档/类型/测试同步"不再是口号，而是可执行的机制。

---

## 9. 局限性

1. **Preview 阶段迭代极快**：`README.md:11` 明确"THERE WILL BE COMPATIBILITY-BREAKING CHANGES"，无外部消费者，重命名/重构可自由进行。
2. **持久化无迁移路径**：SQLite `SCHEMA_VERSION` 单调递增，只有 pristine 新库或当前版本可打开，其它一律拒绝（`session-persistence-sqlite/README.md:60`）。
3. **SQLite 后端同步阻塞**：`DatabaseSync` 每次 append 事务阻塞事件循环，多会话高并发是吞吐瓶颈。
4. **MCP 只桥接 Tools**：Resources/Prompts deferred；启动超时继承 MCP SDK 默认，未暴露连接超时。
5. **非文本多媒体渲染有损**：MCP 的 image/audio/resource 在模型上下文里退化成占位符。
6. **单一 context 注入较繁琐**：`inject` 的上下文等在 inbox 直到另一条消息唤醒（`docs/architecture.md:86`），对"静默注入上下文"的场景有延迟。
7. **学习曲线陡峭**：Cordis 范式（插件/事件/effect/作用域）对新手有门槛，文档体量巨大。

---

## 10. 行业定位

### 10.1 DeepSeek 的战略意义

DeepSeek 以开源模型（DeepSeek-V3/R1）闻名，开源 agent harness 是**从"模型层"向"应用运行层"的自然延伸**：模型是发动机，harness 是底盘——提供一个 MIT 协议的、插件化的、持久化优先的 agent 骨架，等于为第三方开发者铺设了"在 DeepSeek 生态上构建 agent 应用"的高速路，而不锁定到任何闭源产品。

### 10.2 对国内 AI 生态的影响

- **补位开源 agent harness 空白**：国内此前缺一个与 Claude Code 生态同层级的、真正工程化的开源 harness。dsh 的 MCP 命名刻意对齐 Claude Code/Codex，降低了迁移成本。
- **中文友好**：中英双语文档成对维护、企微社区（`README.zh.md:41`）、飞书入群问卷、微信公众号——面向国内开发者的运营投入罕见地高。
- **范式输出**：Cordis 的"时空可组合编程范式"有独立论文，dsh 是它的旗舰实践，对国内 agent 框架的设计有示范意义。
- **风险**：preview 阶段的兼容性破坏 + 快速迭代，意味着现在跟进的企业要承受 API 漂移成本；但"无外部消费者、优先正确基础"的姿态（`AGENTS.md`）说明团队在为长期稳定而非短期兼容做投入。

---

*报告完。*
