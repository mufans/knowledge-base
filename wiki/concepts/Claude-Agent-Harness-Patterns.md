---
title: "Claude Agent Harness设计模式"
category: "concepts"
tags: ["Claude", "Agent-Harness", "Design-Pattern", "AI-Engineering", "Prompt-Engineering"]
rating: 9.0
description: "Anthropic官方推荐的Agent Harness设计三原则：利用已有能力、持续减负、谨慎设界"
date: "2026-05-26"
---

# Claude Agent Harness设计模式

> tags: #Claude #Agent-Harness #Design-Pattern #AI-Engineering #Prompt-Engineering
> source: [Harnessing Claude's intelligence](https://claude.com/blog/harnessing-claudes-intelligence) (Apr 2026)
> score: 摘要质量9/10 | 技术深度8/10 | 相关性9/10 | 原创性9/10 | 格式规范8/10 | 综合 8.65/10

## 核心概念

Anthropic联合创始人Chris Olah提出一个深刻隐喻：**AI系统是"生长的"（grown）而非"构建的"（built）**。研究者设置生长条件来引导方向，但涌现的精确结构或能力并不总是可预测的。

这对Agent Harness设计有深远影响：Harness（控制层）编码了"Claude不能做什么"的假设，但随着Claude能力持续进化，这些假设会过时。即使这篇文章本身的教训也需要频繁重访。

Anthropic官方推荐三大设计模式：

### 1. Use What It Knows（利用已有能力）

用Claude已经熟悉的工具构建应用，而非设计全新工具。典型案例：Claude 3.5 Sonnet在2024年底仅用**bash工具+文本编辑器**就达到了SWE-bench Verified 49%的SOTA。Bash不是为构建Agent设计的，但Claude知道如何使用它，并且随时间推移用得越来越好。

**设计启示**：不要为Agent设计精美的定制工具，用LLM已经熟悉的基础工具（bash、文件编辑）反而效果更好。

### 2. Ask What to Stop Doing（持续减负）

随着模型能力增强，Harness中的一些辅助逻辑可能已经不必要了。定期审查："哪些guardrail可以去掉？哪些提示可以简化？"

**设计启示**：Harness不是越复杂越好。优秀的Harness随模型进化而**精简**。

### 3. Set Boundaries Carefully（谨慎设界）

边界设置需要平衡——过松导致失控，过紧限制能力。关键是只设置真正必要的边界，避免过度约束。

## 设计原理

### Claude Code成功的本质

Claude Code的成功不是因为它有复杂的工具集，恰恰相反——它的工具极其简洁（bash + 文件读写 + 搜索），但Claude对这些工具的理解极其深入。这验证了"**使用已有能力 > 设计新能力**"的原则。

### Harness设计的时间维度

```
时间轴 →

模型能力：  ████████░░░░  →  ██████████████  →  ████████████████████
Harness：  ████████████  →  ██████████░░░░  →  ████████░░░░░░░░░░
                                                        
            初始版本              能力增长            Harness需精简
            完整guardrail         部分guardrail       最小必要边界
```

随着模型能力增长，Harness需要同步**精简**，否则会成为能力释放的瓶颈。

### 反模式：过度设计的Harness

常见错误是为Agent设计大量定制工具（专门的代码分析器、特定的文件格式处理器等），期望通过工具复杂度弥补模型能力的不足。但结果是：
- 工具本身成为维护负担
- 模型需要学习使用这些陌生工具
- 工具设计者的假设可能限制模型发挥

## 关键实现

### 实际案例：Claude Code的极简工具集

Claude Code的工具集本质上只有：
- **Bash**：执行命令
- **Read/Write/Edit**：文件操作
- **Search**：代码搜索

没有复杂的AST分析器、没有定制的Git封装、没有专门的代码格式化器。但Claude通过bash调用了所有这些能力（`git diff`、`ast-grep`、`prettier`等），而且比使用定制工具更灵活。

### 与相关概念的关系

- [Claude-Code-Source-Analysis](../entities/Claude-Code-Source-Analysis.md) — Claude Code源码分析，验证了Harness极简主义
- [Claude-Ecosystem-Tools](Claude-Ecosystem-Tools.md) — Claude生态工具全景
- [everything-claude-code](../entities/everything-claude-code.md) — Claude Code深度指南

### 移动端开发者的启示

这条原则不仅适用于Claude Agent，也适用于任何AI Agent设计：
- 用Agent已经熟悉的接口（REST API、CLI），而非设计全新的通信协议
- 让Agent通过现有工具链（Gradle、adb、xcodebuild）完成工作，而非封装
- 信任模型能力，精简控制层

### 2026-05-31 更新：Seeing Like an Agent（工具设计视角）

来源：[Seeing like an agent: how we design tools in Claude Code](https://claude.com/blog/seeing-like-an-agent) (Apr 2026)

Claude Code团队分享了工具设计的核心框架：**给Agent的工具必须与其自身能力匹配**。

**能力匹配隐喻**：解数学题时需要什么工具？纸（基础但受限）、计算器（更好但需会操作）、计算机（最强但学习曲线陡）。Agent的工具设计同理——通用工具(bash) vs 专用工具(50个细粒度工具)的选择不是越多越好。

**工具增删判断**：
- 添加时机：观察到Agent反复用通用工具模拟某个专用操作时
- 移除时机：工具使用频率低且Agent用通用工具能等效完成时
- 判断方法：阅读Agent输出、实验验证——"learn to see like an agent"

**AskUserQuestion工具演进**：从"直接问"到"渐进式披露(progressive disclosure)"，只在真正需要用户输入时才提问，避免中断Agent工作流。

## 可执行建议

1. **Agent设计review**：检查你当前的Agent Harness，是否包含了"模型已经不需要"的辅助逻辑？
2. **工具选择原则**：新增工具前先问"现有工具（bash/API）能否完成？"只有明确不能时才引入新工具
3. **定期精简**：每次模型升级后，审查Harness中哪些guardrail可以去掉
4. **移动端Agent应用**：设计移动端AI Agent时，优先使用系统原生能力（Intent、ContentProvider），而非封装新的通信层

## 自评
| 维度 | 分数 | 权重 | 加权 |
|------|------|------|------|
| 摘要质量 | 9 | 0.25 | 2.25 |
| 技术深度 | 8 | 0.25 | 2.00 |
| 相关性 | 9 | 0.20 | 1.80 |
| 原创性 | 9 | 0.15 | 1.35 |
| 格式规范 | 8 | 0.15 | 1.20 |
| **加权总分** | | | **8.60** |