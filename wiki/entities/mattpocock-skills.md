# mattpocock/skills

> tags: #Claude-Code #Skills #Agent #Prompt-Engineering
> source: [2026-04-26-新闻热点](../raw/inbox/2026-04-26-新闻热点.md)
> project: [mattpocock/skills](https://github.com/mattpocock/skills)
> score: 技术深度7/10 | 实用价值9/10 | 时效性9/10 | 领域匹配9/10 | 综合 8.5/10

## 核心概念

前 React 核心团队成员 mattpocock 开源的 `.claude` 个人技能集，首日获 1139 star。这不是一个框架，而是一套精心设计的 Claude Code 提示词和工作流模板，展示了如何用"技能文件"持久化 AI 编程助手的行为规范。

## 设计原理

Skills 的核心思路：**把反复修正 AI 行为的过程固化为文件**。每次你发现 Claude Code 犯同样错误，就把修正规则写进 `.claude/` 目录。这本质上是 [Skill-Auto-Creation](../concepts/Skill-Auto-Creation.md) 的人工版。

Trade-off：手动维护 vs 自动生成——mattpocock 选择手写，质量可控但规模化困难。这恰好是 [OpenClaw](OpenClaw.md) 的 skill 系统要解决的问题。

## 关键实现

- 目录结构：`.claude/` 下的 Markdown 文件，每个文件定义一个"技能"
- 技能内容：代码风格偏好、架构决策规则、项目特定约定
- 与 Claude Code 的集成：Claude Code 自动读取项目 `.claude/` 目录作为上下文

## 关联分析

- 直接关联 [Skill-Auto-Creation](../concepts/Skill-Auto-Creation.md)：人工版 vs 自动版的对比案例
- 与 [OpenClaw](OpenClaw.md) 的 skill 系统理念一致，但实现方式不同
- 对 [Claude 生态工具](../concepts/Claude-Ecosystem-Tools.md) 的补充：技能持久化是 Agent 可靠性的关键

## 可执行建议

1. **直接学习其 skill 文件写法**：从 mattpocock 的仓库 fork，根据自己的技术栈（Kotlin/鸿蒙/TS）改写
2. **建立自己的 skill 库**：在项目中维护 `.claude/` 目录，把重复出现的修正规则沉淀为 skill
3. **对比 OpenClaw skill 格式**：两者理念相似但格式不同，选择适合自己工作流的方式
