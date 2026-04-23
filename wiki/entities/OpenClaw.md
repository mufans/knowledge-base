# OpenClaw

> 多通道 AI Agent 网关平台，个人 AI 助手的运行时基础设施

## 基本信息

| 属性 | 值 |
|------|-----|
| 名称 | OpenClaw |
| 版本 | 2026.4.9 (CalVer) |
| 语言 | TypeScript (ESM) |
| 运行时 | Node.js v25+ |
| 许可证 | MIT |
| 仓库 | https://github.com/openclaw/openclaw |
| 入口 | `openclaw.mjs` → `dist/entry.js` |
| 构建工具 | Rollup (chunk splitting) |
| 安装方式 | `npm install -g openclaw` |

## 核心定位

OpenClaw 是一个**多通道 AI 网关**，将 LLM 能力桥接到各种聊天平台（钉钉、Telegram、Discord、Slack、飞书等 30+ 渠道），同时提供完整的 Agent 运行时：技能系统、定时任务、子 Agent、MCP 集成、记忆管理、浏览器控制等。

**核心理念**：Agent 主动服务用户 → 自动化工作流

## 架构概览

```
┌─────────────────────────────────────────────────┐
│                   CLI Layer                      │
│  openclaw gateway | cron | config | doctor ...   │
├─────────────────────────────────────────────────┤
│                 Gateway Daemon                   │
│  ┌──────────┐  ┌──────────┐  ┌──────────────┐  │
│  │ Channels │  │ Sessions │  │ Task Registry│  │
│  │(Plugins) │  │ (Store)  │  │  (SQLite)    │  │
│  └────┬─────┘  └────┬─────┘  └──────┬───────┘  │
│       │              │                │          │
│  ┌────▼──────────────▼────────────────▼───────┐ │
│  │           Agent Runtime (π-embedded)        │ │
│  │  System Prompt + Skills + Tools + Context   │ │
│  └────────────────┬───────────────────────────┘ │
│                   │                              │
│  ┌────────────────▼───────────────────────────┐ │
│  │         Plugin System (Extensions)          │ │
│  │  Providers │ Channels │ Tools │ Memory ...  │ │
│  └────────────────────────────────────────────┘ │
├─────────────────────────────────────────────────┤
│               State Layer                        │
│  ~/.openclaw/  │  SQLite (tasks/flows)  │  FS  │
└─────────────────────────────────────────────────┘
```

## 核心特性

### 1. 多通道网关（30+ 渠道）
- **内置渠道**：Telegram、Discord、Slack、WhatsApp、iMessage、Matrix、IRC、Nostr、飞书、QQ Bot、MS Teams、Nextcloud Talk、Google Chat、Line、Zalo、BlueBubbles、Mattermost 等
- **Webhook 入口**：外部自动化可驱动 TaskFlow
- **Channel 抽象层**：统一的 inbound/outbound pipeline，每个渠道是独立 npm 插件
- **消息格式化**：自动适配各平台的 Markdown/富文本限制

### 2. Agent 运行时
- 基于 `@mariozechner/pi-coding-agent` 嵌入式 Agent
- 支持 100+ 模型提供商（OpenAI、Anthropic、Google、Ollama、DeepSeek、Qwen 等）
- System Prompt 由 workspace 文件 + skills + 工具定义动态组装
- 上下文窗口保护（safeguard mode，硬性最小 16K tokens）
- 模型 fallback 链

### 3. 技能系统（Skills）
- 兼容 agentskills.io 规范
- 从 workspace、bundled、插件目录自动发现 SKILL.md
- 描述注入 system prompt，按需加载完整内容
- ClawHub CLI 搜索/安装/更新/发布
- 安全扫描（检测 exec、eval、数据外泄等）

### 4. 定时任务系统（Cron）
- 使用 `croner` 库进行 cron 表达式调度
- Isolated session：每个 cron 任务有独立会话
- Wake mode：任务完成后唤醒主会话通知
- SQLite 持久化的 Task Registry
- 支持 TaskFlow（多步骤编排）
- 连续错误跟踪和自动重试

### 5. 子 Agent 系统（Subagent）
- Session fork：从父会话分支创建子会话
- 支持 Codex CLI、Claude Code、Pi Agent 作为执行后端
- 完成后自动 announce 结果回父会话
- 孤儿恢复机制

### 6. MCP 集成
- 内置 MCP server（`plugin-tools-serve`），暴露插件注册的工具
- ACP (Agent Communication Protocol) 适配
- MCP 配置管理 CLI

### 7. 记忆系统
- 双文件记忆：MEMORY.md（长期）+ memory/YYYY-MM-DD.md（日记）
- Memory Core 插件 + LanceDB 向量搜索
- Wiki 记忆（结构化 claim/evidence）
- Dreaming 机制（REM 回填、grounded promotion）

### 8. 浏览器控制
- 原生 browser tool（基于 CDP）
- snapshot + act 流式交互
- 多 profile 支持（隔离/用户浏览器）
- SSRF 防护

### 9. Heartbeat 机制
- 定时轮询 HEARTBEAT.md 中的检查项
- 活跃时段控制（activeHours）
- 系统事件队列（邮件/日历等）
- 优先级调度（main session 优先）

## 版本历史

| 版本 | 日期 | 重点 |
|------|------|------|
| 2026.4.9 | 2026-04 | Memory dreaming 增强、QA lab、provider auth aliases、安全修复 |
| 2026.4.8 | 2026-04 | 打包修复、Slack proxy 支持 |
| 2026.4.7 | 2026-04 | CLI infer hub、记忆 wiki、webhook 插件、compaction 插件化、Gemma 4 |

## 技术栈

- **核心**：TypeScript ESM + Rollup (heavy chunk splitting)
- **Agent**：@mariozechner/pi-coding-agent（嵌入式）
- **状态存储**：JSON 文件 + SQLite (node:sqlite)
- **向量搜索**：LanceDB
- **调度**：croner
- **HTTP**：undici (Node 内置)
- **包管理**：npm（支持 pnpm/bun）
- **跨平台**：macOS、Linux、Windows、Android、iOS（companion app）
