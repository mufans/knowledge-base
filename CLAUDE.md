# CLAUDE.md — 知识库规则配置

> 知识库的"大脑"，AI操作知识库时必须遵守的规则。

## 目录结构

```
knowledge/
├── CLAUDE.md          ← 本文件（规则配置）
├── README.md          ← 项目说明（GitHub首页）
├── log.md             ← 操作日志（append-only，每次操作必须追加）
├── raw/               ← 原始资源层（只读不改）
│   ├── inbox/         ← 每日采集的原始内容
│   │   └── archive/   ← 归档的旧日报
│   ├── projects/      ← 项目相关原始文档
│   └── assets/        ← 图片附件
└── wiki/              ← 知识提炼层（结构化知识）
    ├── concepts/      ← 概念页面（抽象的技术思想、方法论）
    ├── entities/      ← 实体页面（具体的项目、工具、产品）
    ├── sources/       ← 来源摘要（文章/论文的详细摘要）
    └── syntheses/     ← 综合分析（跨源对比、趋势分析）
```

## ⛔ 核心规则（最高优先级）

### 1. 层级权限
- **Raw层只读**：AI只能从 `raw/` 读取信息，绝不能修改原始文件
- **Wiki层可写**：AI可以创建、修改、合并 `wiki/` 下的文件

### 2. 操作日志
- **每次操作必须更新 `log.md`**：格式 `YYYY-MM-DD | 操作类型 | 涉及文件 | 简要说明`

### 3. 索引维护
- **每次创建新wiki页面必须更新对应目录的 `index.md`**
- 格式：`- [页面标题](文件名.md)`，链接必须包含 `.md` 后缀
- 禁止 `([](../dir/))dir/文件名.md` 错误格式
- 禁止 `[[]]` Obsidian wikilink格式

### 4. 链接规范
- 所有URL使用 `[名称](URL)` 格式，禁止裸URL
- 提到已有wiki条目时使用交叉链接：
  - 同目录：`[Self-RAG](Self-RAG.md)`
  - 跨目录：`[claude-context](../entities/claude-context.md)`
- 原始项目链接：`[项目名](https://github.com/xxx/xxx)`

## Wiki页面规范

### 页面模板

```markdown
# 标题

> tags: #tag1 #tag2 #tag3
> source: [采集文件名](链接)
> project: [项目名](GitHub URL)（如有）
> score: 技术深度X/10 | 实用价值X/10 | 时效性X/10 | 领域匹配X/10 | 综合 X.X/10

## 核心概念
（具体技术定义，不超过3句）

## 设计原理
（trade-off分析：为什么这样设计，放弃了什么）

## 关键实现
（代码片段、API、具体参数值）

## 关联分析
（使用markdown链接引用已有wiki页面）

## 可执行建议
（结合用户背景的具体行动项）
```

### 内容质量标准

**必须做到**：
- ✅ 避免泛泛而谈，体现具体技术细节（算法名、参数值、代码行、性能数据）
- ✅ 每个页面2-5个分类标签（英文技术术语，如 `#RAG #BM25 #LangGraph`）
- ✅ 底部包含多维度评分（技术深度/实用价值/时效性/领域匹配/综合）
- ✅ 每个维度至少包含一个具体数据或引用
- ✅ 中文输出，技术术语保留英文原文

**禁止行为**：
- ❌ 百科式描述（"XX是一种XX技术，由XX公司开发"）
- ❌ 功能罗列（"XX有A、B、C功能"）
- ❌ 编造信息（所有技术声明必须有据可查）
- ❌ 裸URL（`https://github.com/xxx`）
- ❌ Obsidian格式（`[[wikilink]]`）

### 分类判断标准

| 分类 | 目录 | 判断标准 | 举例 |
|------|------|---------|------|
| 概念 | concepts/ | 抽象的思想/方法/模式 | Self-RAG、Context-Window-Optimization |
| 实体 | entities/ | 具体的项目/工具/产品 | OpenClaw、claude-mem、ml-intern |
| 来源 | sources/ | 文章/论文的深度摘要 | Hermes-Agent-源码分析、推荐书单 |
| 综合 | syntheses/ | 跨源对比/趋势分析 | Hermes-vs-OpenClaw对比分析 |

**模糊时**：看内容侧重——分析技术原理 → concepts，分析项目本身 → entities

## purpose.md — 知识库方向（必读）

每次Ingest和提炼操作前，AI必须读取 `purpose.md` 确保方向一致：

```markdown
# purpose.md

## 目标
构建 AI Agent + 移动端开发交叉领域的个人技术知识图谱

## 关键问题
- AI Agent架构的最佳实践和设计模式？
- 移动端AI应用的技术栈选择和落地路径？
- 哪些开源项目/工具值得深度跟踪？

## 研究范围
AI Agent、LLM、RAG、MCP、移动端开发、鸿蒙AI、Vibe Coding

## 排除范围
纯时政、社会新闻、非技术内容、与用户背景无关的领域
```

**与CLAUDE.md的区别**：schema是结构规则（怎么做），purpose是方向意图（做什么）。

## Ingest流程（摄取新知识）

1. 读取 `purpose.md` 确认方向匹配
2. 读取新内容 → 判断是否有提炼价值（评分≥7.0/10）
3. **增量检查**：在 `log.md` 中搜索文件名，已处理过则跳过
4. 检查wiki中是否已有相关页面 → 避免重复
5. 不存在则新建，存在则补充新观点（标注更新日期）
6. 在相关页面之间建立交叉链接
7. 更新对应目录的 `index.md` 和根 `log.md`

## 增量缓存（避免重复处理）

- 每次提炼前在 `log.md` 中搜索文件名，已处理过则跳过
- 如果原始文件内容有重大更新（不是每日新增），手动触发重新提炼
- 日志格式确保可搜索：`YYYY-MM-DD | ingest | raw/inbox/2026-04-26-AI论文.md | 提炼3篇wiki页面`

## Lint审查（定期维护）

- 找出 `raw/inbox/` 中有但 `wiki/` 未提炼的"未处理资源"
- 找出 `wiki/` 中没有任何引用的"孤立页面"
- 找出内容高度相似可合并的"重复页面"
- 检查 `index.md` 是否列出所有实际文件
- 检查链接格式是否正确（`.md`后缀、无裸URL、无`[[]]`）
- 标记过时的内容

## GitHub Pages同步

### 同步范围
- `raw/inbox/` → `docs/raw/inbox/`
- `raw/projects/` → `docs/raw/projects/`
- `wiki/concepts/` → `docs/wiki/concepts/`
- `wiki/entities/` → `docs/wiki/entities/`
- `wiki/sources/` → `docs/wiki/sources/`
- `wiki/syntheses/` → `docs/wiki/syntheses/`
- `README.md` → `docs/index.md`
- `CLAUDE.md` → `docs/CLAUDE.md`
- `log.md` → `docs/log.md`

### 部署前检查
- 每个 `index.md` 列出所有实际文件
- 链接格式正确（`.md`后缀）
- `mkdocs.yml` 未被覆盖（被覆盖则 `git checkout mkdocs.yml`）
- `mkdocs build` 无 ERROR
