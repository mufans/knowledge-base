# Hermes Agent

> **一个自改进的 AI Agent 框架**，由 Nous Research 开发

## 基本信息

| 项目 | 详情 |
|------|------|
| 仓库 | https://github.com/NousResearch/hermes-agent |
| 开发者 | Nous Research |
| 版本 | v0.11.0 |
| 语言 | Python (≥3.11) |
| 许可证 | MIT |
| 安装 | `pip install hermes-agent` 或脚本安装 |

## 核心定位

Hermes Agent 是一个 **Self-Improving AI Agent**，其核心差异化在于内置的**学习闭环**：

1. **Memory** — 持久化记忆系统（MEMORY.md + USER.md）
2. **Skills** — 过程性记忆（从经验中创建/改进技能）
3. **Nudge Engine** — 定期自我审查，主动持久化知识和技能

## 架构概览

```
hermes-agent/
├── agent/              # 核心引擎
│   ├── prompt_builder.py    # System prompt 构建
│   ├── context_engine.py    # 上下文管理
│   ├── context_compressor.py # 上下文压缩
│   ├── memory_manager.py    # 外部记忆 provider 桥接
│   └── transports/          # 多模型适配层 (Anthropic, Bedrock, OpenAI, Codex)
├── gateway/            # 消息网关
│   ├── platforms/      # Telegram, Discord, Slack, WhatsApp, Signal, DingTalk...
│   ├── session.py      # 会话管理
│   └── config.py       # 配置管理
├── tools/              # 工具集 (40+)
│   ├── memory_tool.py      # 记忆工具 (MemoryStore)
│   ├── skills_tool.py      # 技能浏览/加载
│   ├── skill_manager_tool.py # 技能创建/编辑/删除
│   ├── terminal_tool.py    # Shell 执行
│   ├── browser_tool.py     # 浏览器自动化
│   └── ...
├── run_agent.py        # 主 Agent 循环 (AIAgent, 12000+ 行)
├── hermes_cli/         # CLI 入口
├── plugins/            # 插件系统
│   └── memory/         # 记忆插件 (Honcho, Mem0, Holographic, Hindsight...)
├── environments/       # 终端后端 (Local, Docker, SSH, Daytona, Modal, Singularity)
├── cron/               # 定时任务调度器
└── skills/             # 内置技能库
```

## 核心特性

### 1. 自改进闭环 (Self-Improving Loop)

这是 Hermes 与其他 Agent 框架的最大区别：

- **Memory Nudge**: 每 N 个 user turns（默认 10），后台 fork 一个 Agent 审查对话，主动保存用户偏好/环境信息
- **Skill Nudge**: 每 N 次工具调用迭代（默认 10），后台审查是否有值得保存为新技能的方法
- **Skill Self-Improvement**: 技能在使用中被 patch 更新，包含 pitfall、错误修正等

### 2. 多平台支持

Telegram, Discord, Slack, WhatsApp, Signal, 钉钉, 飞书, 企业微信, Matrix, Mattermost, Email, SMS, Webhook — 全部通过一个 Gateway 进程。

### 3. 多模型支持

Nous Portal, OpenRouter (200+ 模型), NVIDIA NIM, OpenAI, Anthropic, Bedrock, Gemini, Kimi/Moonshot, MiniMax, Ollama — 通过 transport 层适配。

### 4. 运行环境多样性

6 种终端后端：Local, Docker, SSH, Daytona, Singularity, Modal。支持 $5 VPS 到 GPU 集群。

### 5. 插件生态

- 记忆插件：Honcho (用户建模), Mem0, Holographic, Hindsight, RetainDB, SuperMemory
- 图片生成：OpenAI, xAI, Codex
- Context Engine 插件
- Skills Hub (agentskills.io 标准)

## Self-Improving 闭环详解

### Memory 系统

- 文件持久化：`~/.hermes/memories/MEMORY.md` + `USER.md`
- 字符限制：Memory 2200 chars, User 1375 chars（非 token，模型无关）
- 冻结快照：session 启动时加载，会话中不更新 system prompt（保持 prefix cache）
- 安全扫描：正则匹配注入/外泄模式
- 并发安全：fcntl/msvcrt 文件锁

### Skill 系统

- 遵循 agentskills.io 开放标准
- YAML frontmatter + Markdown body
- 6 种操作：create, edit, patch, delete, write_file, remove_file
- fuzzy_find_and_replace：9 级模糊匹配策略
- 安全校验：skills_guard 扫描（默认关闭）

### Nudge Engine

- **Memory Nudge**: 每 `_memory_nudge_interval` 个 user turns 触发
- **Skill Nudge**: 每 `_skill_nudge_interval` 次工具迭代触发
- 后台线程 fork 一个完整 AIAgent（独立模型调用）
- 使用专用 review prompt 引导审查
- 完成后输出 💾 摘要（如 "Memory updated · Skill 'deploy-api' created"）

## 与 OpenClaw 的关系

Hermes Agent 是 OpenClaw 的 **商业 fork/替代品**，由同一团队（Nous Research）开发。两者架构高度相似：
- 都有 Gateway + Agent + Tools 三层架构
- 都支持 Telegram/Discord/WhatsApp 等平台
- 都有 SOUL.md / AGENTS.md 的人格系统
- 都有 Skills 系统（agentskills.io 兼容）
- 都有 Memory 系统
- 都有 Cron 调度

Hermes 的独特增量：更完善的 Self-Improving 闭环（Nudge Engine）、更丰富的记忆插件生态、内置 RL 训练支持、更多终端后端。

## 参考链接

- 文档: https://hermes-agent.nousresearch.com/docs/
- Discord: https://discord.gg/NousResearch
- 技能标准: https://agentskills.io
