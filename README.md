# 个人技术知识库

> AI Agent · 移动端开发 · 开源项目分析

## 关于

这个知识库通过 **Signal → Research Dossier → 独立评审 → 发布或拒绝** 的知识编译流程，持续构建 AI Agent × 移动端开发方向的公开知识资产。OpenClaw 负责确定性采集和调度，Hermes 负责正反分析与实验设计；公开页面必须通过引用、增量、重复和链接门禁。

## 设计理念

基于 [Karpathy LLM Wiki 方法论](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) 构建，参考 [nashsu/llm_wiki](https://github.com/nashsu/llm_wiki) 桌面应用的增强设计。

**核心理念**：
- **编译一次，持续复用** — 知识提炼一次，永久累积，而非每次查询从头检索（vs 传统RAG）
- **Raw只读，Wiki可写** — 原始数据不可篡改，提炼层自由演进
- **人策展，AI维护** — 方向和最终公开决策由人掌握，AI 提供证据与候选
- **结构化积累** — 通过页面类型、声明类型、证据与交叉链接形成知识图谱
- **不发布也是成功** — 没有明确知识增量或证据不足时，流水线正常停止

**与RAG的区别**：

| | RAG | LLM Wiki |
|---|------|----------|
| 知识存储 | 向量数据库 | 结构化Markdown文件 |
| 查询方式 | 每次检索+拼凑 | 直接读取已有页面 |
| 知识演进 | 无累积 | 持续增长+关联 |
| Token消耗 | 每次查询大量消耗 | 提炼一次，查询低消耗 |

## 知识库结构

```
knowledge/
├── CLAUDE.md          ← 规则配置（AI操作知识库时必须遵守）
├── log.md             ← 操作日志（append-only）
├── raw/               ← 原始资源层（只读不改）
│   ├── inbox/         ← 每日自动采集的原始内容
│   └── projects/      ← 项目相关文档
└── wiki/              ← 知识提炼层（结构化知识）
    ├── concepts/      ← 概念：抽象的技术思想和方法论
    ├── entities/      ← 实体：具体的项目、工具、产品
    ├── sources/       ← 来源：文章和论文的详细摘要
    └── syntheses/     ← 综合：跨源对比分析
```

### 目录说明

| 目录 | 权限 | 说明 | 举例 |
|------|------|------|------|
| `raw/inbox/` | 只读 | 每日采集的原始新闻、论文、GitHub项目 | `2026-04-26-AI论文.md` |
| `raw/projects/` | 只读 | 项目相关原始文档 | OpenClaw功能推荐报告 |
| `wiki/concepts/` | 可写 | 技术概念、设计模式、方法论 | [Self-RAG](wiki/concepts/Self-RAG.md)、[Context-Window-Optimization](wiki/concepts/Context-Window-Optimization.md) |
| `wiki/entities/` | 可写 | 具体项目、工具、产品 | [OpenClaw](wiki/entities/OpenClaw.md)、[claude-mem](wiki/entities/claude-mem.md) |
| `wiki/sources/` | 可写 | 文章/论文的深度摘要 | [OpenClaw-源码分析](wiki/sources/OpenClaw-源码分析.md) |
| `wiki/syntheses/` | 可写 | 跨源对比、趋势分析 | [Hermes-vs-OpenClaw对比分析](wiki/syntheses/Hermes-vs-OpenClaw对比分析.md) |

### 分类判断标准

- **概念**（concepts/）— "这是什么思想/方法"，抽象的、通用的
- **实体**（entities/）— "这是什么东西"，具体的、有明确边界的
- **来源**（sources/）— "这篇文章/论文说了什么"，对原始内容的精炼
- **综合**（syntheses/）— "A和B比怎么样"，跨源对比分析

## 采集流程

每日自动从以下信息源采集：

| 任务 | 时间 | 模型 | 方式 | 说明 |
|------|------|------|------|------|
| 新闻热点 | 08:00 | deepseek/deepseek-v4-flash | LLM | AI/大模型、编程工具、移动端、云原生、开源 |
| 技术动态 | 10:00 | deepseek/deepseek-v4-flash | LLM | InfoQ、OSChina等技术社区 |
| AI论文 | 11:00 | - | **Python脚本** | HuggingFace Daily Papers（0 token消耗） |
| GitHub项目 | 12:00 | - | **Python脚本** | GitHub Search API（0 token消耗） |
| 社交媒体 | 13:00 | deepseek/deepseek-v4-flash | LLM | AI技术动态筛选 |
| 晚间总结 | 21:00 | deepseek/deepseek-v4-flash | LLM | 当日采集内容回顾 |

## 知识编译流程

1. **Signal** — OpenClaw 将采集内容转换成带稳定 ID、时间和哈希的输入
2. **Research Dossier** — Hermes 区分 Fact、Inference、Hypothesis，并整理支持与反方证据
3. **Wiki Candidate** — Knowledge Compiler 先判断是否有增量、应更新旧页面还是创建综合分析
4. **独立评审** — 检查事实引用、数字/API 追溯、限制与反例、重复、链接和研究方向
5. **决策** — 发布、等待人工判断或拒绝；拒绝原因进入后续采集和实验反馈

## Hermes 个人机会发现系统

知识库之上运行一层个人机会发现系统，目标是持续发现方向、累积正反证据和设计低成本实验，而不是把信息范围锁定在某个项目或预设技术路线。

| 层 | 原生责任 | 本系统的薄适配 |
|---|---|---|
| OpenClaw | 广域信息采集、Cron 调度、重试、钉钉交付与失败告警、网关重启 | 只注册带所有权标记的机会发现任务 |
| Hermes | Profile、Session、Memory、Skill、Curator 与自我改进审批 | 固定 `opportunity-discovery` Profile 与最小工具集 |
| Opportunity OS | — | 机会卡、实验、方向组合、技术新鲜度、脱敏知识库输出和只读仪表盘 |

生产节奏由 OpenClaw 唯一调度：工作日 18:30 执行每日发现，周日 19:00 执行每周复盘，每 10 分钟执行聚合健康检查。实时热点保留在 Frontier；只有官方稳定发布、文档完整、最小兼容测试、无严重已知问题和有回滚路径全部满足后，才进入 Stable 建议。

常用本地状态入口：

```bash
openclaw gateway status
openclaw cron list --all
hermes -p opportunity-discovery dashboard --status
launchctl print gui/501/com.opportunity-os.dashboard
uv run --directory integrations/hermes-opportunity-os python -m opportunity_os.deployment ngrok-status
```

## 质量规范

- 页面按 concept、entity、source、synthesis 使用不同最低结构，不填充空章节
- Fact、Inference、Hypothesis 必须明确区分，重要结论同时保留支持与反方证据
- 数字、版本、性能和 API 声明引用覆盖率为 100%，其他重要事实目标不低于 90%
- 发布时 Wiki broken links 必须为 0，优先更新已有页面并增加 synthesis
- 历史自评分仅作浏览元数据，不再决定发布或默认排序
- 所有链接使用 `[名称](URL)`；禁止裸 URL、`[[]]` 和不可验证的实现细节

## MCP Server

知识库提供了一个 MCP Server，支持通过 MCP 协议查询知识库内容，可接入 Claude Code、OpenCode、Cursor 等工具。

### 工具列表

| 工具 | 说明 |
|------|------|
| `search_kb` | 全文搜索知识库（支持分类过滤、评分阈值） |
| `get_entity` | 获取指定知识页面的完整内容 |
| `list_recent` | 列出最近更新的知识页面 |

### Claude Code 配置

在 `~/.claude/settings.json` 中添加：

```json
{
  "mcpServers": {
    "knowledge": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/path/to/knowledge/mcp_server",
        "python",
        "server.py"
      ]
    }
  }
}
```

> **注意**: Claude Code 的 stdio MCP 不支持 `cwd` 字段，需使用 `uv run --directory` 指定工作目录。

### 技术栈

- **自动化平台**: [OpenClaw](https://github.com/openclaw/openclaw) — AI Agent网关
- **采集脚本**: Python 3（GitHub API + HuggingFace API）
- **知识提炼**: DeepSeek V4 Flash（分析+采集）
- **静态站点**: MkDocs Material（GitHub Pages部署）
- **知识库地址**: [mufans.github.io/knowledge-base](https://mufans.github.io/knowledge-base/)
- **MCP Server**: Python stdio（支持 Claude Code / OpenCode / Cursor）

---

*由 OpenClaw、Hermes 与 Knowledge Compiler 协作维护 · 最后更新：2026-07-29*
