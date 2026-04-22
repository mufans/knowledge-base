# OpenClaw 源码学习路径

> 针对 mufans 的背景（12年移动端开发、转型 AI Agent）定制
> 源码：https://github.com/openclaw/openclaw
> 技术栈：TypeScript / Node.js
> AI 辅助阅读：https://deepwiki.com/openclaw/openclaw

---

## 源码核心目录结构

```
src/
├── agents/          # 🎯 Agent 核心（session、state、workspace 管理）
├── bindings/        # 多渠道路由（消息如何分发到不同 agent）
├── bootstrap/       # 首次启动流程（SOUL.md、IDENTITY.md 生成）
├── gateway/         # 🎯 Gateway 核心（启动、配置、生命周期）
├── sessions/        # 🎯 会话管理（历史、压缩、状态）
├── cron/            # 🎯 定时任务系统
├── tools/           # 🎯 工具系统（browser、exec、web_search 等）
├── channels/        # 渠道接入（钉钉、WhatsApp、Telegram 等）
├── mcp/             # MCP 客户端实现
├── models/          # LLM 模型抽象（provider、failover）
├── nodes/           # iOS/Android/macOS Node 通信
├── canvas-host/     # Canvas 可视化面板
├── plugins/         # 插件系统
├── acp/             # ACP（Agent Communication Protocol）编码代理
├── chat/            # 对话处理核心
├── cli/             # CLI 命令行
└── auto-reply/      # 自动回复逻辑
```

---

## 学习路线（4周计划）

### 第1周：整体架构 + Gateway 入口

**目标**：理解 OpenClaw 的整体设计和启动流程

**阅读顺序**：
1. `package.json` → 了解依赖和脚本入口
2. `src/gateway/` → Gateway 启动流程、配置加载
3. `src/agents/` → Agent 定义、workspace 管理、SOUL.md 加载
4. `src/bootstrap/` → 首次启动 Q&A 流程（你刚体验过的）

**重点关注**：
- Gateway 如何加载 `openclaw.json` 配置
- Agent 的 workspace、agentDir、session store 三层隔离
- SOUL.md / AGENTS.md 是如何被注入到 system prompt 的

**产出**：画出 OpenClaw 的启动流程图

---

### 第2周：会话管理 + 上下文压缩

**目标**：理解 Agent 的"记忆"是怎么工作的

**阅读顺序**：
1. `src/sessions/` → 会话创建、存储、查询
2. `src/sessions/` 中的 compaction 相关代码 → 上下文压缩机制
3. `src/models/` → LLM 调用抽象、provider 管理

**重点关注**：
- 会话历史存储格式（messages、tool calls）
- compaction 触发条件和压缩策略（你经历过的"会话压缩"）
- 模型 failover 机制（主模型挂了怎么切换）
- token 计数和预算控制

**产出**：理解为什么你经常遇到 compaction，以及 token 消耗的控制策略

---

### 第3周：工具系统 + MCP 集成

**目标**：理解 Agent 如何调用外部工具

**阅读顺序**：
1. `src/tools/` → 工具注册、执行、结果返回
2. `src/mcp/` → MCP 客户端实现
3. `src/tools/browser/` → 浏览器自动化（最复杂的工具之一）

**重点关注**：
- 工具定义格式（function calling schema）
- MCP server 的发现、连接、工具注册流程
- 工具执行结果如何注入回对话上下文
- 并发工具调用（streaming tool results）

**产出**：能自己写一个简单的 MCP Server 并接入 OpenClaw

---

### 第4周：定时任务 + 多Agent路由 + 渠道

**目标**：理解 OpenClaw 的自动化和多租户能力

**阅读顺序**：
1. `src/cron/` → 定时任务调度、isolated session 创建
2. `src/bindings/` → 消息路由规则（你最常遇到的问题）
3. `src/channels/` → 渠道接入抽象层
4. 钉钉插件代码 → 你用的钉钉渠道

**重点关注**：
- cron 任务如何创建 isolated session、执行、推送结果
- bindings 的优先级匹配逻辑（most-specific wins）
- 钉钉 Stream 连接的心跳和重连机制（你踩过的坑）
- delivery 失败的根因（channel vs last 的区别）

**产出**：理解你之前遇到的 delivery failed、模型 not allowed 等问题的根因

---

## 学习技巧

### 1. 用 DeepWiki 辅助阅读
`https://deepwiki.com/openclaw/openclaw` — AI 生成的代码解读，比硬读快很多

### 2. 用 Claude Code / Cursor 辅助
在项目目录里直接问：
- "这个文件是做什么的？"
- "这个函数的调用链是什么？"
- "从入口到这条消息被处理，经过了哪些文件？"

### 3. 从你踩过的坑出发
你已经踩过很多坑，带着问题看源码理解会深很多：
- 模型 "not allowed" → 看 `src/agents/` 和 `src/models/`
- delivery failed → 看 `src/cron/` 和 `src/channels/`
- compaction → 看 `src/sessions/`
- 钉钉重连循环 → 看钉钉插件的心跳机制

### 4. 不要试图全部看懂
OpenClaw 是几万行代码的成熟项目。聚焦标 🎯 的 5 个核心模块就够了。

---

## 对你 AI Agent 转型的价值

| 学到的能力 | 直接应用 |
|-----------|---------|
| 会话管理和上下文压缩 | 做自己的 Agent 系统时管理对话状态 |
| 工具系统（function calling） | LangGraph 中的 tool use 是同一套逻辑 |
| MCP 协议实现 | 开发自己的 MCP Server |
| 多 Agent 路由 | multi-agent 架构设计参考 |
| 定时任务编排 | Agent 自动化执行流程 |

---

## 补充资源

- 官方文档：https://docs.openclaw.ai
- DeepWiki：https://deepwiki.com/openclaw/openclaw
- Discord 社区：https://discord.com/invite/clawd
- GitHub：https://github.com/openclaw/openclaw

---

*创建时间: 2026-03-30*
*作者: Claw 🦞*
