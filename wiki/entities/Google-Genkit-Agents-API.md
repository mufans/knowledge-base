---
title: "Google Genkit Agents API — 统一Agent开发框架"
category: "entities"
tags: ["Agent-Framework", "Google", "Genkit", "Tool-Calling", "TypeScript"]
rating: 9.5
description: "Google Genkit推出的Agents API预览版，通过统一chat()接口封装对话、工具调用、状态持久化和分离式交互，支持TypeScript和Go"
date: "2026-07-19"
---

# Google Genkit Agents API — 统一Agent开发框架

> tags: #Agent-Framework #Google #Genkit #Tool-Calling #TypeScript #State-Management
> source: [谷歌 Genkit 推出 Agents API](https://www.infoq.cn/article/ckLEtt7bN6AAURuEjfFF)
> project: [Genkit](https://genkit.dev/)
> score: 技术深度8/10 | 实用价值7/10 | 时效性8/10 | 领域匹配7/10 | 综合 7.5/10

## 核心概念

Google Genkit（全栈式 AI 应用开源框架）推出 **Agents API 预览版**，核心设计是将消息历史、工具执行循环、流式传输、状态持久化和前端协议**全部封装在一个 chat() 接口背后**。无论 Agent 是进程内运行还是 HTTP 端点部署，chat() 接口的工作方式完全一致。

## 设计原理

### 核心抽象层

Genkit Agents API 的设计哲学是**一个抽象层实现扩容，无需更换底层组件**。这意味着同一个 Agent 对象可以处理：
- 一次性应答
- 流式多轮对话
- 需要人工确认的可中断工具调用
- 独立运行的长耗时任务

### 状态管理的两种模式

**服务端管理**：
- 配置会话存储后，消息、自定义状态和产物以快照形式持久化
- 客户端通过 sessionId 重新连接
- 内置存储：Firestore（生产）、内存（开发）、文件（测试）
- 支持可插拔自定义存储

**客户端管理**：
- 服务端返回完整状态，客户端在每轮对话中回传
- 优势：数据驻留在客户端，适用于临时会话和严格数据合规场景
- 代价：会话增长后网络负载增加

### 分离式交互（Detached Interaction）

Agent 任务可以在客户端断开后继续在服务端运行。客户端通过轮询获取结果：
- 无需 WebSocket
- 无需独立任务队列
- 适用于长时间运行的研究任务、多步骤规划

### 可中断工具（Interruptible Tool）

工具可被标记为"可中断"。Agent 在执行此类工具时会暂停，将待执行操作返回客户端等待用户确认。**防伪造保护**：运行时会结合会话历史校验恢复请求，防止工具被伪造输入诱导执行。

## 关键实现

### 分离式交互代码（TypeScript）

```typescript
const chat = reportAgent.chat({ sessionId: 'report-123' });
const task = await chat.detach('Write the quarterly market report.');
savePendingSnapshot(task.snapshotId);
for await (const snapshot of task.poll({ intervalMs: 1000 })) {
  renderStatus(snapshot.status);
  if (snapshot.status === 'completed') renderMessages(snapshot.state.messages);
}
```

### 可中断工具代码（Go）

```go
runShell := genkitx.DefineInterruptibleTool(g, "run_shell",
  "Run a shell command after a safety check.",
  func(ctx context.Context, input ShellInput, confirm *Confirmation) (ShellOutput, error) {
    if isRisky(input.Command) {
      if confirm == nil {
        return ShellOutput{}, tool.Interrupt(ShellInterrupt{
          Command: input.Command,
          Reason:  "The command can modify files.",
        })
      } else if !confirm.Approved {
        return ShellOutput{}, errors.New("user rejected shell command execution")
      }
    }
    return execute(input.Command)
  },
)
```

### 两种状态数据

| 数据类型 | 作用 | 示例 |
|---------|------|------|
| 自定义状态 | 驱动下一轮对话的强类型数据 | 工作流状态、任务列表、已选实体 |
| 产物 (Artifact) | 可供用户查看/下载/版本管理的输出 | 报告、代码补丁、旅行行程 |

### 多Agent编排

通过五月份发布的[中间件系统](https://developers.googleblog.com/announcing-genkit-middleware-intercept-extend-and-harden-your-agentic-apps/)，为每个子 Agent 注入委派调用工具：
- 编排主模型将请求拆分，分派给各专业子 Agent
- 子 Agent 可本地运行或 HTTP 接口部署
- 中间件支持：指数退避重试、跨提供商模型降级、工具人工审核、SKILL.md 注入

### 生态集成

- 官方插件：Gemini、Vertex AI、Anthropic、OpenAI、Ollama
- Vercel AI SDK 适配器
- 支持 TypeScript 和 Go（Python/Dart 计划中）
- 插件架构实现模型无关性

## 关联分析

- 与 [OpenClaw](OpenClaw.md) 对比：Genkit 更偏向云服务端 Agent 编排，而 OpenClaw 是本地 Agent 运行环境
- 与 [Anthropic-Agent-API](Anthropic-Agent-API.md) 对比：同为 Agent API，Genkit 强调状态管理和分离式交互，Anthropic 强调 Managed Agents 和 Task 模式
- 可中断工具的设计与 [Tool Calling 安全实践](../concepts/Client-Side-Tool-Calling.md) 高度相关

## 可执行建议

1. **可中断工具的安全模式值得借鉴**：在 Agent 执行破坏性操作前引入人工审批链，这是企业级 Agent 的标配
2. **分离式交互对移动端有意义**：Agent 任务可以触发后在云端持续运行，移动端随时轮询结果，不占用前台连接
3. **关注 Genkit 生态发展**：目前是预览版，后续稳定后可以和已有 Google Cloud 基础设施集成
4. **SKILL.md 注入**：与 OpenClaw 的 skill 机制相似，说明"以 Markdown 为 Agent 配置文件"是行业趋势

## 自评

| 维度 | 分数 | 权重 | 加权 |
|------|------|------|------|
| 摘要质量 | 8 | 0.25 | 2.00 |
| 技术深度 | 8 | 0.25 | 2.00 |
| 相关性 | 7 | 0.20 | 1.40 |
| 原创性 | 7 | 0.15 | 1.05 |
| 格式规范 | 9 | 0.15 | 1.35 |
| **加权总分** | | | **7.80** |