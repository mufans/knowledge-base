---
title: "Claude Code Subagents 实战指南"
category: "sources"
tags: ["Claude-Code", "Subagent", "Agent-Orchestration", "Coding-Agent", "Parallel-Execution"]
rating: 9.0
description: "Anthropic官方指南：Claude Code子代理的使用时机、调用方式、自定义配置和自动化Hooks"
date: "2026-06-01"
---

# Claude Code Subagents 实战指南

> tags: #ClaudeCode #Subagent #AgentOrchestration #CodingAgent #ParallelExecution
> source: [How and when to use subagents in Claude Code](https://claude.com/blog/subagents-in-claude-code) | [2026-06-01-Claude博客](../../raw/inbox/2026-06-01-Claude博客.md)
> score: 技术深度9/10 | 实用价值10/10 | 时效性9/10 | 领域匹配10/10 | 综合 9.5/10

## 核心概念

Subagent是**拥有独立上下文窗口的隔离Claude实例**，接收任务后独立工作，仅返回结果给主会话。类似于浏览器的标签页——在独立空间追踪分支任务而不丢失主线上下文。多个Subagent可并行运行，各自拥有不同权限（如只读研究 vs 全编辑实现）。

## 设计原理

### 为什么需要Subagent

长会话积累的上下文导致两个问题：**响应变慢**（每次都需处理完整历史）和**Token成本上升**（所有历史都参与推理）。Subagent通过隔离上下文窗口解决这两个问题——只传递任务描述进去，只拿结构化结果出来。

### Subagent适用场景的识别信号

| 场景 | 信号 | 收益 |
|------|------|------|
| 研究型任务 | 需要读取10+文件 | 主会话保持干净，只接收摘要 |
| 多独立任务 | 子任务间无依赖 | 3个并行Subagent通常更快完成 |
| 需要新视角 | 需无偏见的审查 | 不继承主会话假设和盲点 |
| 提交前验证 | 需第二意见 | 捕获熟悉代码导致的疏忽 |
| 流水线工作 | 有明确交接的阶段 | 每阶段专注，无跨阶段噪声 |

**关键经验法则**：当任务需要探索10+文件或涉及3+独立工作块时，强烈建议使用Subagent。

## 关键实现

### 内置Subagent类型

- **General-purpose**：复杂多步骤任务
- **Plan agents**：先研究代码库再提出实施策略
- **Explore agents**：快速只读代码搜索

### 1. 会话式调用（最灵活）

```
Use subagents to explore this codebase in parallel:
1. Find all API endpoints and summarize their purposes
2. Identify the database schema and relationships
3. Map out the authentication flow
Return a summary of each, not the full file contents.
```

有效Prompt结构三要素：**定义独立任务** → **显式请求并行** → **指定输出格式**

Tips：
- 明确范围："Explore how payments work" 优于 "explore everything"
- 显式请求并行："these can run in parallel"
- 指定返回格式：摘要/具体发现/建议
- 需要无偏分析时："Use a subagent that does not see our previous discussion"
- `Ctrl+B` 将运行中的Subagent发送到后台；`/tasks` 查看后台任务

### 2. 自定义Subagent配置

文件位置：`.claude/agents/`（项目级，团队共享）或 `~/.claude/agents/`（用户级，跨项目）

```yaml
---
name: security-reviewer
description: Reviews code changes for security vulnerabilities, injection risks, auth issues, and sensitive data exposure. Use proactively before commits touching auth, payments, or user data.
tools: Read, Grep, Glob
model: sonnet
---
You are a security-focused code reviewer. Analyze the provided changes for:
- SQL injection, XSS, and command injection risks
- Authentication and authorization gaps
- Sensitive data in logs, errors, or responses
- Insecure dependencies or configurations
Return a prioritized list of findings with file:line references and a recommended fix for each.
```

**关键设计点**：`description`字段是Claude判断何时委派的核心依据。写触发条件而非能力描述——"Reviews code for security issues before commits" 比 "security expert" 路由更精准。

### 3. CLAUDE.md策略配置

```markdown
## Code review standards
When asked to review code, ALWAYS use a subagent with READ-ONLY access (Glob, Grep, Read only). The review should ALWAYS check for:
- Security vulnerabilities
- Performance issues
- Adherence to project patterns in /docs/architecture.md
Return findings as a prioritized list with file:line references.
```

区别：CLAUDE.md是**每次都加载的策略**，Custom Subagent是**按需委派的专家**。

### 4. Skills（按需加载的工作流）

```yaml
# .claude/skills/deep-review/SKILL.md
---
name: deep-review
description: Comprehensive code review that checks security, performance, and style in parallel. Use when reviewing staged changes before a commit or PR.
---
Run three parallel subagent reviews on the staged changes:
1. Security review - check for vulnerabilities, injection risks
2. Performance review - check for N+1 queries, memory leaks
3. Style review - check consistency with project patterns
Synthesize findings into a single summary with priority-ranked issues.
```

Skills vs CLAUDE.md：CLAUDE.md**每次交互都加载**，Skill**按需加载**（匹配description时或显式调用`/skill-name`时）。

### 5. Hooks（生命周期自动化）

```json
{
  "hooks": {
    "Stop": [{
      "hooks": [{
        "type": "command",
        "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/check-tests.sh"
      }]
    }]
  }
}
```

Stop Hook示例：Claude完成turn时触发测试脚本，测试失败则返回`decision: "block"`阻止Claude结束，形成自动修复循环。`stop_hook_active`守卫防止无限循环。

自动化程度排序：会话式调用 < CLAUDE.md策略 < Skills < Hooks

## 关联分析

- [Claude-Code-Source-Analysis](../entities/Claude-Code-Source-Analysis.md) — Claude Code源码级架构分析
- [Claude-Ecosystem-Tools](../concepts/Claude-Ecosystem-Tools.md) — Claude生态工具全景
- [Context-Window-Optimization](../concepts/Context-Window-Optimization.md) — 上下文窗口优化策略
- [Multi-Agent-Systems-Design](../concepts/Multi-Agent-Systems-Design.md) — 多Agent系统设计模式
- [Agent-Workflow-Patterns](../concepts/Agent-Workflow-Patterns.md) — Agent工作流模式

## 可执行建议

1. **立即实践**：在自己的项目中创建`.claude/agents/`目录，定义一个security-reviewer或test-writer
2. **配置CLAUDE.md**：将"代码审查必须用只读Subagent"写入项目CLAUDE.md，确保团队一致性
3. **识别并行机会**：当任务涉及3+独立文件/模块时，显式要求Claude并行派发Subagent
4. **渐进式自动化**：先用会话式调用验证模式，确认有效后升级为Custom Agent → CLAUDE.md策略 → Skills → Hooks
5. **成本控制**：研究型任务用只读Subagent（Glob/Grep/Read），实现型用全权限，避免不必要的Token消耗

## 自评

| 维度 | 分数 | 权重 | 加权 |
|------|------|------|------|
| 摘要质量 | 9 | 0.25 | 2.25 |
| 技术深度 | 9 | 0.25 | 2.25 |
| 相关性 | 10 | 0.20 | 2.00 |
| 原创性 | 8 | 0.15 | 1.20 |
| 格式规范 | 9 | 0.15 | 1.35 |
| **加权总分** | | | **9.05** |

> 评分理由：Anthropic官方权威指南，五层调用体系（会话/自定义/CLAUDE.md/Skills/Hooks）覆盖从手动到全自动的完整光谱，对Agent开发实践有直接指导价值。