---
title: "Claude Code Hooks 配置指南"
category: "sources"
tags: ["Claude-Code", "Hooks", "Automation", "Workflow"]
rating: 8.0
description: "Claude Code官方Hooks配置详解，8种Hook类型实现自动化工作流、规则执行和动态上下文注入"
date: "2026-05-29"
---

# Claude Code Hooks 配置指南

> tags: #ClaudeCode #Hooks #Automation #WorkflowCustomization #DeveloperTools
> source: [Claude Blog: How to configure hooks](https://claude.com/blog/how-to-configure-hooks)
> score: 技术深度8/10 | 实用价值9/10 | 时效性8/10 | 领域匹配9/10 | 综合 8.5/10

## 核心概念

Hooks是Claude Code的自定义Shell命令触发机制，在特定事件（如文件写入、权限请求、会话启动）发生时自动执行。本质上是对Claude Code行为的**AOP（面向切面编程）**——不修改工具本身，通过外部钩子注入自定义逻辑。

## 设计原理

Claude Code工作流中的三类摩擦问题：
1. **重复操作**：每次写文件后手动跑Prettier、每次npm test重复授权
2. **规则执行**：依赖人记住检查危险命令、验证文件路径
3. **上下文缺失**：每次新会话都要手动提供项目状态

Hooks通过事件驱动解决这三类问题。设计上的trade-off：用配置复杂度换取自动化程度——简单场景用默认配置即可，复杂项目才需要深度定制。

## 关键实现

### 8种Hook类型

| Hook | 触发时机 | 典型用途 |
|------|---------|---------|
| PreToolUse | 工具执行前 | 拦截危险命令、验证路径 |
| PermissionRequest | 权限弹窗前 | 自动批准测试命令 |
| PostToolUse | 工具完成后 | 自动格式化、触发lint |
| PreCompact | 上下文压缩前 | 备份关键对话 |
| SessionStart | 会话开始时 | 注入git status、TODO |
| Stop | Claude完成响应后 | 验证任务、跑测试 |
| SubagentStop | 子Agent完成时 | 验证子Agent输出 |
| UserPromptSubmit | 用户提交prompt时 | 注入sprint上下文 |

### 配置结构
```json
{
  "hooks": {
    "PostToolUse": [{
      "matcher": "Write|Edit",
      "command": "npx prettier --write $FILE_PATH"
    }],
    "PermissionRequest": [{
      "matcher": "npm test",
      "command": "exit 0"
    }]
  }
}
```

### 信息传递机制
- 通过stdin接收事件信息（JSON格式）
- 通过exit code通信（0=允许/继续，2=阻断）
- 通过stdout输出注入上下文

## 关联分析

- 与 [Claude-Code-Source-Analysis](Claude-Code-Source-Analysis.md) 互补：源码分析揭示内部架构，Hooks是外部定制接口
- 与 [everything-claude-code](everything-claude-code.md) 关联：Hooks是Claude Code高级用法的核心
- 与 [Skill-Auto-Creation](../concepts/Skill-Auto-Creation.md) 关联：Hooks可自动化Skill的触发和执行

## 可执行建议

1. **必配Hook**：PostToolUse自动格式化（Prettier/ESLint），PermissionRequest自动批准npm test
2. **团队项目**：用SessionStart注入项目CONVENTIONS.md，确保每次会话遵守团队规范
3. **安全加固**：用PreToolUse拦截对生产环境配置文件的写入操作
4. **CI集成**：用Stop Hook在任务完成后自动运行测试套件

## 自评
| 维度 | 分数 | 权重 | 加权 |
|------|------|------|------|
| 摘要质量 | 9 | 0.25 | 2.25 |
| 技术深度 | 8 | 0.25 | 2.00 |
| 相关性 | 9 | 0.20 | 1.80 |
| 原创性 | 7 | 0.15 | 1.05 |
| 格式规范 | 9 | 0.15 | 1.35 |
| **加权总分** | | | **8.45** |