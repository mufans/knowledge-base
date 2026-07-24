---
title: "Verification Loops — Agent编码的自动验证闭环"
category: "concepts"
tags: ["Claude-Code", "Verification", "Agent-Engineering", "CI-CD", "Skills"]
rating: 9.5
description: "Anthropic提出的Agent编码验证闭环模式：通过Skills将手动检查步骤编码为自动化验证流程，在Agent执行过程中自动校验并修复代码质量"
date: "2026-07-24"
---

# Verification Loops — Agent编码的自动验证闭环

> tags: #Claude-Code #Verification #Agent-Engineering #CI-CD #Skills
> source: [Building verification loops in Claude Code with skills](https://claude.com/blog/building-verification-loops-in-claude-code-with-skills)
> score: 技术深度8/10 | 实用价值9/10 | 时效性9/10 | 领域匹配10/10 | 综合 9.0/10

## 核心概念

Verification Loop（验证闭环）是 Claude Code 中的一种迭代流程：Agent 在生成代码后自动执行预设的检查规则，发现问题后自行修复并重新验证，直到全部通过或达到失败上限。核心思路是将开发者手动的检查步骤（lint、测试、审查规范等）编码为 Skills，让 Agent 完成"编码→检查→修复→再检查"的自主闭环。

传统 Agent 编码流程的验证主要依赖确定性信号（类型检查器、linter、运行时错误），而 Verification Loops 将**隐性的人工判断标准**（代码审查规范、设计约束、安全规则）也转化为可编程的验证逻辑。

## 设计原理

### 四种部署模式

Anthropic 团队从实践中总结出 Verification Loops 的四种使用模式，按自动化和集成深度排列：

| 模式 | 触发方式 | 适用场景 | 成本 |
|------|---------|---------|------|
| **Standalone**（独立） | 手动调用 | 跨领域通用检查（安全扫描、可访问性审计、License检查） | 最低 |
| **Embedded**（内嵌） | 自动随主Skill执行 | 特定工作流的固有检查（组件创建后跑eslint） | 中等 |
| **Chained**（链式） | Skills自动串联 | 多步骤流水线（代码审查→简化→验证→设计检查） | 较高 |
| **PR Gate**（PR门禁） | 自动在PR上触发 | 团队级质量门禁 | 最高 |

**设计权衡：**
- Standalone 灵活性最高但依赖开发者记忆触发，适合"偶尔需要但每次都要做"的检查
- Embedded 自动化最彻底但只能用于可修改的 Skill（不能修改内置Skill/插件管理的Skill）
- Chained 将多步验证打包为完整流水线，但 Token 消耗显著增加，需要测试后部署
- PR Gate 将个人习惯升级为团队契约，但流程仍在变化时不适合过早加固

### 核心架构设计原则

1. **Skill 是验证闭环的原子单元**：每个验证逻辑封装为一个 Skill，包含 name、description、allowed-tools 和验证指令
2. **验证指令必须明确**：描述"什么是对的"和"怎么修"，而非仅描述"要检查什么"
3. **类型检查器和 linter 是底线**：确定性信号（编译错误、lint 违规）应由工具而非 Agent 判断

### 与其他机制的关系

Verification Loops 与传统的 CI/CD 流水线本质上是互补关系：
- **CI/CD**：在代码提交后运行，有完善的 GC 和资源管理
- **Verification Loop**：在 Agent 编码过程中实时运行，反馈即时
- **最佳实践**：先用 Verification Loop 在 Agent 端捕获问题，再依赖 CI/CD 作为最终安全网

## 关键实现

### 最小验证 Skill 模板

```markdown
# .claude/skills/verify-log-hygiene/SKILL.md
---
name: verify-log-hygiene
description: Check that error logs include the request ID and never include 
  the request body. Use when the diff touches error handling or logging.
allowed-tools: [Read, Edit, Grep]
---
Read the error-handling paths in the current diff. For each log call on an 
error path, confirm it includes the request ID and does not pass the request 
body, headers, or any user-supplied payload. Report each violation with 
file:line, then fix it: add the request ID where it's missing and strip the 
payload from the log call.
```

### Embedded 模式实现

在已有 Skill 末尾追加验证步骤即可实现 Embedded：

```markdown
# .claude/skills/scaffold-component/SKILL.md
---
name: scaffold-component
description: Scaffold a new React component under src/components/, including 
  the component file, its co-located test, and an index export.
allowed-tools: [Read, Write, Edit, Bash, Glob]
---
# Scaffold a new React component
[组件创建逻辑...]

# After creating the component file, run eslint on it and address any 
# errors before reporting completion.
```

### Chained 模式实现

Chaining 通过一个 Wrapper Skill 调用多个子 Skill 实现端到端流水线：

```markdown
# .claude/skills/safe-refactor/SKILL.md
Run /simplify on the current diff first. When /simplify finishes, 
invoke /verify-no-public-api-changes.
```

### 四种模式的实用建议

- **Standalone** 适用的信号：单个 Skill 的上下文成本高，但跨多个工作流都有用
- **跳过 Embedded 的场景**：检查跨多个工作流而不仅是单个 Skill 所属的工作流
- **Chaining 的停止信号**：当步骤之间独立到有时只想运行其中一部分时，应停止链式调用
- **PR Gate 的启动时机**：Chained 流程稳定后，PR Gate 是自然演进

## 关联分析

- [Context-Engineering](Context-Engineering.md) — Verification Loops 是 Context Engineering 在代码质量领域的工程化落地
- [Agent-Skills-Architecture](../sources/Agent-Skills-Architecture.md) — Skills 是验证闭环的容器，Addy Osmani 的架构分析提供了理论基础
- [Vibe-Coding-Agent-Engineering-Convergence](Vibe-Coding-Agent-Engineering-Convergence.md) — Verification Loops 填补了 Vibe Coding 中"写代码 → 检查代码"的自动化闭环
- [Loop-Engineering](Loop-Engineering.md) — Verification Loop 是 Loop Engineering 在编码场景的具体应用（聚焦代码而非通用Agent行为）
- [Claude-Code-Routines](../entities/Claude-Code-Routines.md) — Routines 可部署 Verification Loops 在云端定时执行，替代本地手动触发

## 可执行建议

1. **立即实践**：从"Standalone"模式开始，为当前项目编写一个 log-hygiene 验证 Skill，体验 Verification Loop 的最小闭环
2. **逐步升级**：当某个验证检查形成习惯后（例如"每次改完代码跑eslint"），Embedded 到对应 Skill 中，减少手动步骤
3. **PR 门禁是远期目标**：先确保 Chained 流水线稳定运行一段时间，再配置 PR Gate
4. **Token 意识**：Chained Verification Loop 会增加 Token 消耗，建议先在本地测试闭环成本，再决定是否部署到团队范围。估算方法：统计每个 Skill 的平均 Token 消耗 × 链式调用的深度
5. **结合用户背景**：作为移动端开发者，可先将 Verification Loop 应用于 Android APK 构建验证、API 兼容性检查等移动端特有场景，验证其在移动端开发流程中的实用性

## 自评

| 维度 | 分数 | 权重 | 加权 |
|------|------|------|------|
| 摘要质量 | 9 | 0.25 | 2.25 |
| 技术深度 | 8 | 0.25 | 2.00 |
| 相关性 | 9 | 0.20 | 1.80 |
| 原创性 | 8 | 0.15 | 1.20 |
| 格式规范 | 9 | 0.15 | 1.35 |
| **加权总分** | | | **8.60** |

> 评分标准：摘要质量（四种模式+模板代码）| 技术深度（trade-off分析+架构原则+身份分类）| 相关性（直接匹配Agent Coding实践）| 原创性（独立结构划分+四模式适配策略）| 格式规范（5标签+5交叉链接+完整自评）