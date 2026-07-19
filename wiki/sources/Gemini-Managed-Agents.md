---
title: "Gemini Managed Agents — 后台任务与远程MCP"
category: "sources"
tags: ["Gemini", "Managed-Agents", "MCP", "Background-Execution", "Google-AI"]
rating: 9.0
description: "tags: #Gemini #Managed-Agents #MCP #Background-Execution #Google-DeepMind"
date: "2026-07-19"
---

# Gemini Managed Agents — 后台任务、远程MCP与自定义函数

> tags: #Gemini #Managed-Agents #MCP #Background-Execution #Google-DeepMind
> source: [Google Blog — Expanding Managed Agents in Gemini API](https://blog.google/innovation-and-ai/technology/developers-tools/expanding-managed-agents-gemini-api/)
> score: 技术深度7/10 | 实用价值8/10 | 时效性9/10 | 领域匹配8/10 | 综合 8.0/10

## 核心概念

Google DeepMind 在 2026年7月7日宣布了 Gemini API 中 Managed Agents 的新能力：**后台执行**（Background Execution）、**远程MCP服务器集成**、**自定义函数调用**和**凭据自动刷新**。Managed Agents 通过单一端点调用，让 Gemini 在隔离的云端沙箱中处理推理、代码执行、包安装、文件管理和网络信息获取。

## 设计原理

### 后台执行的必要性

长时间运行的 Agent（如代码仓库分析、数据爬取）如果保持 HTTP 连接打开，会面临连接不稳定的问题。Gemini 引入 `background: true` 参数，服务端立即返回 interaction ID，客户端可轮询状态、流式获取进度，或在 Agent 完成后重新连接获取结果。

```javascript
// 启动后台任务
const interaction = await client.interactions.create({
  agent: "antigravity-preview-05-2026",
  input: "Clone repo, find all TODOs, categorize in markdown report.",
  environment: "remote",
  background: true,
});

// 轮询状态
let result = interaction;
while (result.status === "in_progress") {
  await new Promise((resolve) => setTimeout(resolve, 5000));
  result = await client.interactions.get(interaction.id);
}
```

### 远程MCP集成

关键能力：**无需编写自定义代理中间件**，Managed Agents 可直接连接远程 MCP 服务器访问私有数据库或内部 API。支持在 interaction 调用时传入 `mcp_server` tool，与 Google Search 和代码执行等内置能力混合使用。

### 凭据管理

支持跨交互的凭据自动刷新，解决长时间 Agent 运行中 token 过期的痛点。

## 关键实现

- **API 入口**：`client.interactions.create()` 是核心接口，传入 agent 名称、输入、environment 配置和 tools 列表
- **工具混合**：支持 MCP server + Google Search + 代码执行在同一 interaction 中并行使用
- **沙箱安全**：所有代码执行在隔离云端沙箱中进行，外部 MCP 调用遵循安全最佳实践
- **适用场景**：代码审查 Agent、内部运维告警响应、跨系统数据同步 Agent

## 关联分析

- [Anthropic-Agent-API](../entities/Anthropic-Agent-API.md) — 对比：Anthropic 的 Agent API 侧重 Computer Use 和 Tool Use，Gemini Managed Agents 侧重沙箱执行和外部 MCP 集成
- [MCP-Tunnel](../entities/MCP-Tunnel.md) — MCP 远程连接方案比较
- [Google-IO-2026-Agentic-Era](Google-IO-2026-Agentic-Era.md) — Google 全面 AI Agent 化的宏观背景
- [Google-Genkit-Agents-API](../entities/Google-Genkit-Agents-API.md) — Genkit 提供不同的 Agent 构建路径

## 可执行建议

1. **参考后台执行模式**：在设计端侧 Agent 时，可将异步任务 + 轮询的模式引入移动端，解决网络连接不稳定的问题
2. **MCP 集成思路**：移动端 Agent 可借鉴远程 MCP 设计，通过 MCP 协议连接企业后端服务，无需暴露完整 API
3. **关注竞品差异**：Gemini 的沙箱执行 vs Anthropic 的本地执行，理解不同路线有助于端侧 Agent 的策略选择

## 自评

| 维度 | 分数 | 权重 | 加权 |
|------|------|------|------|
| 摘要质量 | 7.5 | 0.25 | 1.88 |
| 技术深度 | 7.0 | 0.25 | 1.75 |
| 相关性 | 8.0 | 0.20 | 1.60 |
| 原创性 | 7.5 | 0.15 | 1.13 |
| 格式规范 | 8.5 | 0.15 | 1.28 |
| **加权总分** | | | **7.63** |