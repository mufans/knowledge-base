# 个人技术知识库

> AI Agent · 移动端开发 · 开源项目分析

## 关于

这个知识库通过 **采集 → 分析 → 提炼** 的自动化流水线，持续构建结构化的个人技术知识图谱。由 OpenClaw Agent 自动维护，每日从多个信息源采集、筛选、提炼高价值技术内容。

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
| 新闻热点 | 08:00 | glm-4.7-flash | LLM | AI/大模型、编程工具、移动端、云原生、开源 |
| 技术动态 | 09:30 | glm-4.7-flash | LLM | InfoQ、OSChina等技术社区 |
| AI论文 | 10:00 | - | **Python脚本** | HuggingFace Daily Papers（0 token消耗） |
| GitHub项目 | 10:30 | - | **Python脚本** | GitHub Search API（0 token消耗） |
| 社交媒体 | 11:00 | glm-4.7-flash | LLM | AI技术动态筛选 |
| 晚间总结 | 21:00 | glm-4.7-flash | LLM | 当日采集内容回顾 |

## 提炼流程

每日00:00由 glm-5.1 执行深度知识提炼：

1. **读取** — 加载当日采集文件 + 已有wiki内容
2. **筛选** — 评估每条内容的价值（技术深度、实用价值、时效性、领域匹配）
3. **提炼** — 高价值内容生成wiki页面（5个维度：概念→原理→实现→关联→建议）
4. **质量检查** — 覆盖度、摘要质量、评分合理性、链接格式、信息真实性
5. **输出** — 保存到wiki/ + 更新index.md + 同步GitHub Pages

## 质量规范

### 每篇wiki页面必须包含

```markdown
# 标题

> tags: #tag1 #tag2 #tag3
> source: [采集文件名](链接)
> project: [项目名](GitHub URL)（如有）
> score: 技术深度X/10 | 实用价值X/10 | 时效性X/10 | 领域匹配X/10 | 综合 X.X/10

## 核心概念
## 设计原理
## 关键实现
## 关联分析
## 可执行建议
```

### 核心约束

- ✅ 避免泛泛而谈，必须体现具体技术细节（算法名、参数值、代码行、性能数据）
- ✅ 所有链接使用 `[名称](URL)` 格式，禁止裸URL
- ✅ 提到已有wiki条目时使用交叉链接 `[Self-RAG](Self-RAG.md)`
- ✅ 禁止 `[[]]` Obsidian格式，mkdocs不支持
- ✅ 技术术语使用英文原文作为标签
- ✅ 每个页面2-5个分类标签 + 多维度评分
- ❌ 禁止百科式描述（"XX是一种XX技术"）
- ❌ 禁止功能罗列（"XX有A、B、C功能"）
- ❌ 禁止编造信息，所有技术声明必须有据可查

## 技术栈

- **自动化平台**: [OpenClaw](https://github.com/openclaw/openclaw) — AI Agent网关
- **采集脚本**: Python 3（GitHub API + HuggingFace API）
- **知识提炼**: GLM-5.1（深度分析）+ GLM-4.7-Flash（采集）
- **静态站点**: MkDocs Material（GitHub Pages部署）
- **知识库地址**: [mufans.github.io/knowledge-base](https://mufans.github.io/knowledge-base/)

---

*由 OpenClaw 每日自动化流水线维护 · 最后更新：2026-04-26*
