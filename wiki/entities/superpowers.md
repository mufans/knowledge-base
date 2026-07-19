---
title: "Superpowers — Agent编码技能框架与开发方法论"
category: "entities"
tags: ["Agent-Framework", "Coding-Agent", "Development-Methodology", "Skills", "Plugin"]
rating: 9.5
description: "Superpowers是一套完整的Agent编码开发方法论，集成技能框架、子Agent驱动开发、TDD和代码审查，支持Claude Code/Codex/Cursor等主流平台"
date: "2026-07-19"
---

# Superpowers — Agent编码技能框架与开发方法论

> tags: #Agent-Framework #Coding-Agent #Development-Methodology #Skills #Plugin #TDD
> source: [obra/superpowers](https://github.com/obra/superpowers)
> project: [obra/superpowers](https://github.com/obra/superpowers)
> score: 技术深度8/10 | 实用价值8/10 | 时效性8/10 | 领域匹配8/10 | 综合 8.0/10

## 核心概念

Superpowers 是一套**完整的 Agent 软件编码开发方法论**，以可组合的技能包为基础，搭配会话初始指令，让编码 Agent 在开发时自动遵循规范流程。支持 Claude Code、Codex、Cursor、Pi、Kimi Code、OpenCode 等主流编码 Agent 平台。

## 设计原理

### 核心设计动机

传统编程 Agent 的问题是：**缺乏流程管控**。Agent 接到任务后直接开始写代码，没有设计评审、没有测试先行、没有架构规划。结果质量完全取决于模型的随机发挥。

Superpowers 解决思路：**用规范化的开发流程约束 Agent 行为**，让 Agent 像资深工程师一样先设计、再计划、后编码、最后验证。

### 完整的开发工作流

1. **头脑风暴（Brainstorming）**：Agent 不会直接写代码，而是通过提问完善需求，展示设计方案供用户确认
2. **Git Worktree（using-git-worktrees）**：设计通过后，在隔离的 worktree 上创建新分支，运行项目初始化，验证测试基线
3. **编写计划（writing-plans）**：将设计拆解为 2-5 分钟的单任务，每个任务标注精确文件路径、完整代码和验证步骤
4. **子Agent驱动开发（subagent-driven-development）**：每个任务分配独立子 Agent 执行，执行完成后进行两阶段审查（规范一致性 + 代码质量）
5. **TDD（test-driven-development）**：强制 RED-GREEN-REFACTOR 循环——先写失败测试、再写最小实现、最后提交
6. **代码审查（requesting-code-review）**：任务间自动审查，按严重程度报告问题，关键问题阻塞进度

### 设计原则

- **YAGNI**（You Aren't Gonna Need It）：只实现当前需要的东西
- **DRY**：避免重复代码
- **子Agent隔离**：每个子Agent任务独立执行，互不干扰，降低 context window 压力
- **两阶段审查**：先检查是否符合规范，再检查代码质量

## 关键实现

### 支持的编码Agent平台

| 平台 | 安装方式 |
|------|---------|
| Claude Code | 官方插件市场 /plugin install superpowers |
| Codex App | 官方插件市场，Sidebar → Plugins |
| Codex CLI | /plugins → 搜索 superpowers |
| Cursor | /add-plugin superpowers |
| Pi | pi install git:github.com/obra/superpowers |
| Kimi Code | 插件管理器或 /plugins install |
| OpenCode | 执行 INSTALL.md 指令 |
| Factory Droid | droid plugin install |
| GitHub Copilot CLI | copilot plugin install |

### 核心技能（Skills）

| 技能 | 触发时机 | 作用 |
|------|---------|------|
| brainstorming | 编码前 | 通过提问细化需求，生成设计方案文档 |
| using-git-worktrees | 设计批准后 | 创建隔离工作区，设置分支和测试基线 |
| writing-plans | 设计批准后 | 将任务分解为2-5分钟的原子任务 |
| subagent-driven-development | 计划就绪后 | 按任务分派子Agent，两阶段审查 |
| test-driven-development | 实施中 | 强制 TDD 循环 |
| requesting-code-review | 任务间 | 审查代码质量，阻塞关键问题 |

### 架构特点

- 技能自动触发：Agent 在需要时自动调用对应技能，无需手动切换
- 可跨平台：同一套方法论在不同编码 Agent 上行为一致
- 子Agent并行：支持 Autonomous 运行数小时不偏离原始计划
- 审查闭环：每个任务出产代码都要经过审查

## 关联分析

- 与 [OpenClaw 的 skill 机制](OpenClaw.md) 同出一辙：都是通过 Markdown/技能文件约束 Agent 行为。Superpowers 更侧重编码方法论，OpenClaw 侧重 Agent 运行环境
- 其子Agent驱动开发模式与 [Claude Code 的 hook 机制](../sources/Claude-Code-Hooks-Guide.md) 形成对比：一为代码级 hook，一为方法论级约束
- 两阶段审查（规范+质量）可以用于 [AppSmartInspector](../entities/AppSmartInspector.md) 的审查流程设计
- TDD 强制循环与 [Loop-Engineering](../concepts/Loop-Engineering.md) 的检测-修复循环理念一致

## 可执行建议

1. **方法论可借鉴**：superpowers 的核心价值不是代码，而是"用制度约束 Agent 行为"的思想——在写 Agent 指令文件时，明确流程比明确代码更重要
2. **子Agent模式值得验证**：将大任务拆分为子Agent独立执行+审查，可以显著降低单个 Agent 的 Context 压力
3. **关注跨平台设计**：一套方法论适配 8 个编码 Agent，这提示了 SKILL.md 作为跨平台 Agent 配置标准的潜力
4. **可以尝试在 Claude Code 中安装**：通过 `/plugin install superpowers@claude-plugins-official` 安装体验

## 自评

| 维度 | 分数 | 权重 | 加权 |
|------|------|------|------|
| 摘要质量 | 8 | 0.25 | 2.00 |
| 技术深度 | 8 | 0.25 | 2.00 |
| 相关性 | 8 | 0.20 | 1.60 |
| 原创性 | 7 | 0.15 | 1.05 |
| 格式规范 | 9 | 0.15 | 1.35 |
| **加权总分** | | | **8.00** |