---
title: "Continue"
category: "entities"
tags: ["GitHub", "工具", "开源项目"]
rating: 8.0
description: "tags: #AICodeReview #CI-CD #TypeScript #DeveloperTools"
date: "2026-05-07"
---

# Continue

> tags: #AICodeReview #CI-CD #TypeScript #DeveloperTools
> source: [ai-knowledge-base/articles/2026-04-29-continuedevcontinue.json](https://github.com/continuedev/continue)
> project: [Continue](https://github.com/continuedev/continue)
> score: 技术深度7/10 | 实用价值8/10 | 时效性8/10 | 领域匹配8/10 | 综合 7.75/10

## 核心概念

Continue 是一个开源的 AI 代码审查和辅助开发工具（32k+ GitHub stars），支持 CLI 和 IDE 集成。核心能力是通过 AI 在 CI 流程中自动执行代码审查，提供可配置的审查规则和自动化检查。它代表了 AI 辅助开发从"写代码"向"审代码"的延伸。

## 设计原理

**CLI-first + IDE 集成**：Continue 以 CLI 为核心（`continue` 命令），同时提供 VS Code / JetBrains 插件。CLI-first 的选择使得 Continue 可以无缝集成到 CI/CD 管道中，而不仅仅局限于 IDE 内使用。

**可配置审查规则**：不同于固定的 lint 规则，Continue 的 AI 审查规则可以自然语言定义（如"检查是否处理了空指针"），并通过 `.continuerc` 配置文件版本化管理。Trade-off 是 AI 审查的非确定性，同一代码不同时间可能得到不同结果。

**模型无关**：支持 OpenAI、Anthropic、本地模型等多种 LLM 后端，用户可根据成本和隐私需求选择。

## 关键实现

- **AI Code Review**：在 PR 中自动添加 review comments，支持自定义审查维度
- **Tab 补全**：IDE 内的 AI 代码补全
- **Chat 模式**：与代码库上下文交互的对话模式
- **`.continuerc` 配置**：定义允许/禁止的操作、审查规则、模型选择
- **CI 集成**：通过 GitHub Actions 等 CI 系统自动触发审查

## 关联分析

- 与 [Claude-Code-Source-Analysis](../entities/Claude-Code-Source-Analysis.md) 对比：Claude Code 更侧重代码生成和重构，Continue 更侧重代码审查和辅助
- 与 [OpenClaw](../entities/OpenClaw.md) 的关系：OpenClaw 的 coding-agent skill 可以使用 Continue 作为子 Agent
- 相关概念：[Vibe Coding](../concepts/)、[AST-Driven-AI-Editing](../concepts/AST-Driven-AI-Editing.md)

## 可执行建议

1. **CI 中的 AI Code Review**：在 GitHub Actions 中集成 Continue，为每个 PR 自动添加 AI 审查意见
2. **自定义审查规则**：根据团队编码规范，配置针对性的审查维度（安全、性能、可读性）
3. **本地模型降低成本**：对于大型代码库，使用本地模型（Ollama）避免 API 成本过高

## 自评
| 维度 | 分数 | 权重 | 加权 |
|------|------|------|------|
| 摘要质量 | 7 | 0.25 | 1.75 |
| 技术深度 | 7 | 0.25 | 1.75 |
| 相关性 | 8 | 0.20 | 1.60 |
| 原创性 | 7 | 0.15 | 1.05 |
| 格式规范 | 9 | 0.15 | 1.35 |
| **加权总分** | | | **7.50** |