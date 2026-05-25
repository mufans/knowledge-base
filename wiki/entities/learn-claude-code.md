---
title: "learn-claude-code：从零构建Agent Harness"
category: "entities"
tags: ["Agent-Harness", "Bash", "Education", "Architecture", "Claude-Code"]
rating: 9.0
description: "62k stars教学项目，用纯Bash从零实现一个类Claude Code的Agent Harness，深入理解Agent架构底层原理"
date: "2026-05-25"
---

# learn-claude-code：从零构建Agent Harness

> tags: #AgentHarness #Bash #Education #Architecture #ClaudeCode
> source: [2026-05-25-GitHub项目](../../raw/inbox/2026-05-25-GitHub项目.md) | [GitHub](https://github.com/shareAI-lab/learn-claude-code)
> score: 技术深度8/10 | 实用价值8/10 | 时效性8/10 | 领域匹配9/10 | 综合 8.2/10

## 核心概念

**learn-claude-code**（口号："Bash is all you need"）是一个62k stars的教学项目，用纯Bash脚本从零实现一个类Claude Code的Agent Harness。项目目标不是生产级工具，而是通过**最小化实现**揭示Agent系统的核心架构：prompt组装、工具调用循环、上下文管理、错误恢复。适合想深入理解Agent底层机制的开发者。

## 设计原理

### 最小化揭示本质

选择Bash而非Python/TypeScript的原因：
- **消除抽象层**：Python的类/装饰器/异步框架会掩盖Agent循环的本质——读prompt、调API、解析输出、执行动作、再循环
- **零依赖**：只需curl和jq就能运行，降低入门门槛
- **可读性**：Bash脚本的线性执行流天然映射Agent的循环逻辑

Trade-off：Bash不适合生产环境（错误处理弱、无类型系统），但作为教学工具，它迫使开发者直面Agent设计的每个细节决策。

### Agent Harness核心循环

项目展示了Agent的统一架构模式：
1. **System Prompt注入**：组装角色、约束、可用工具定义
2. **用户消息处理**：解析意图，构建对话上下文
3. **LLM调用**：发送完整上下文到API
4. **输出解析**：区分文本回复和工具调用指令
5. **工具执行**：沙箱化执行，捕获输出
6. **上下文更新**：将工具结果追加到对话历史
7. **循环/终止**：判断是否继续调用LLM

## 关键实现

- **工具定义格式**：使用JSON Schema描述工具参数，与MCP的tool定义格式一致
- **上下文窗口管理**：实现了简单的token计数和消息裁剪策略
- **错误恢复**：工具执行失败时将错误信息反馈给LLM，让LLM决定重试或换方案
- **多轮对话**：维护完整的message history，支持跨轮次的上下文引用

## 关联分析

- ECC Agent优化框架：[ECC](ECC.md)
- Agent控制流设计：[Agent-Control-Flow](../concepts/Agent-Control-Flow.md)
- Claude Code源码分析：[Claude-Code-Source-Analysis](Claude-Code-Source-Analysis.md)
- Agent技能架构：[Agent-Skills-Architecture](../sources/Agent-Skills-Architecture.md)

## 可执行建议

1. **学习路径**：先通读learn-claude-code的Bash实现，建立Agent循环的心智模型，再阅读Claude Code源码会更容易理解
2. **动手实践**：在本地clone项目，逐步添加自定义工具（如文件搜索、代码格式化），理解工具注册和调用机制
3. **架构对照**：对比ECC的模块化设计和learn-claude-code的极简设计，理解不同复杂度场景下的架构选择
4. **面试准备**：能用Bash解释Agent循环是面试中展示深度理解的好方法

## 自评

| 维度 | 分数 | 权重 | 加权 |
|------|------|------|------|
| 摘要质量 | 8.5 | 0.25 | 2.13 |
| 技术深度 | 8.0 | 0.25 | 2.00 |
| 相关性 | 9.0 | 0.20 | 1.80 |
| 原创性 | 7.5 | 0.15 | 1.13 |
| 格式规范 | 9.0 | 0.15 | 1.35 |
| **加权总分** | | | **8.40** |