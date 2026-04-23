# Knowledge Base

> 个人技术知识库，基于 Karpathy LLM Wiki 方法构建。

## 📌 关注领域

- AI Agent 与多智能体系统
- LLM 与大模型应用
- 移动端开发
- 云原生与后端架构
- 开源项目与开发者工具

## 📂 结构

```
├── CLAUDE.md      ← 规则配置（AI操作知识库的指令）
├── index.md       ← 索引表（所有内容的花名册）
├── log.md         ← 操作日志（append-only）
├── raw/           ← 原始资源层（只读不改）
│   ├── inbox/     ← 每日采集
│   ├── projects/  ← 项目文档
│   └── assets/    ← 附件
└── wiki/          ← 维基层（AI提炼的结构化知识）
    ├── concepts/  ← 概念页面
    ├── entities/  ← 实体页面
    ├── sources/   ← 来源摘要
    └── syntheses/ ← 综合分析
```

## 🔍 在线访问

- GitHub Pages: https://mufans.github.io/knowledge-base/
- GitHub 仓库: https://github.com/mufans/knowledge-base

## 📝 使用方式

- **摄取**：发文章链接给AI → 自动保存到raw + 提炼到wiki
- **搜索**：说"搜知识库 xxx" → AI先查index再精准读取
- **审查**：每周自动Lint → 找孤立页面、重复内容
