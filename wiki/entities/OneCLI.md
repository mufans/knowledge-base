---
title: "OneCLI：Agent密钥安全网关"
category: "entities"
tags: ["Agent-Security", "Credential-Management", "MCP", "Rust", "Open-Source"]
rating: 9.0
description: "用代理模式拦截AI Agent请求并替换占位符为真实凭证的密钥安全网关，Rust编写，防止Agent泄漏敏感凭据"
date: "2026-07-28"
---

# OneCLI：Agent密钥安全网关

> tags: #Agent-Security #Credential-Management #MCP #Rust #Open-Source
> source: [HN Show HN 2026-07-28](../../raw/inbox/2026-07-28-社交媒体.md)
> project: [onecli/onecli](https://github.com/onecli/onecli)
> score: 技术深度7/10 | 实用价值8/10 | 时效性8/10 | 领域匹配7/10 | 综合 7.5/10

## 核心概念

OneCLI 是一个开源（Rust编写）的**Agent密钥安全网关**，通过代理模式拦截AI Agent发出的请求，自动将请求中的密钥占位符替换为真实凭据，再将请求转发到目标服务。核心价值：**Agent的prompt和上下文中永远不出现真实密钥**，从而防止密钥泄露——无论是通过日志、对话历史还是模型训练数据。

## 设计原理

### 代理拦截模式

OneCLI 作为中间代理运行在Agent和目标服务之间：

```
Agent → [占位符:{{API_KEY}}] → OneCLI Proxy → [真实密钥] → 目标API
```

工作流程：
1. 开发者在Agent的prompt中使用占位符（如 `{{GITHUB_TOKEN}}`）而非真实密钥
2. Agent发起请求时，请求经过OneCLI代理
3. OneCLI拦截请求，匹配占位符→真实密钥的映射表
4. 替换占位符为真实凭据，转发到目标服务
5. 响应原路返回，Agent始终看不到真实密钥

### 为什么不能只用环境变量或Secrets Manager

| 方案 | 核心问题 |
|------|---------|
| 环境变量注入Agent | Agent可能在工具调用中将环境变量值写回对话或日志 |
| Secrets Manager SDK | Agent代码中直接调用SDK获取密钥，泄漏面仍在Agent内 |
| Prompt中硬编码 | 最危险——密钥直接出现在模型训练数据中 |
| **OneCLI代理模式** | 密钥在Agent之外独立管理，Agent只知占位符 |

**Trade-off**：代理模式引入了一个额外的网络跳转（增加延迟），每个请求需要一次代理映射查询。但换来的是密钥和Agent的**物理隔离**——即使Agent被完全攻破，攻击者也只能拿到占位符。

### 技术实现

- **语言**：Rust（高性能、内存安全）
- **代理类型**：透明HTTP代理，支持拦截和修改请求内容
- **密钥存储**：本地加密存储（非远程服务，降低依赖面）
- **HN评分**：109分，社区认可度不错

## 关键实现

### 使用示例（概念）

```yaml
# onecli config
mappings:
  GITHUB_TOKEN: "ghp_xxxx"          # 实际密钥
  OPENAI_API_KEY: "sk-xxxx"          # 实际密钥
  DATABASE_URL: "postgres://..."     # 实际连接串
```

Agent prompt中只需使用占位符：
```
使用 {{GITHUB_TOKEN}} 访问GitHub API获取仓库信息
```

OneCLI在请求发出前自动替换。

## 关联分析

- [MCP-Tunnel](MCP-Tunnel.md) — MCP安全隧道解决MCP协议的传输安全，OneCLI解决Agent凭据的存储安全，两者互补
- [Anthropic-Agent-API](../entities/Anthropic-Agent-API.md) — Anthropic的Managed Agents内置了Vaults凭据管理，OneCLI是开源替代方案
- [Anthropic-CISO-Agent-Security-Guide](../sources/Anthropic-CISO-Agent-Security-Guide.md) — Agent安全指南，OneCLI实现了其中的凭据隔离原则
- [Zero-Trust-AI-Agents-Anthropic](../sources/Zero-Trust-AI-Agents-Anthropic.md) — 零信任Agent理念，OneCLI的代理隔离是零信任的具体实现

## 可执行建议

1. **在自己的Agent项目中考虑凭据隔离**：即使不用OneCLI，其"占位符+代理替换"模式可以参考实现——将密钥管理从Agent代码中分离出来
2. **与你的MCP开发相关**：如果你开发MCP工具涉及到API密钥，OneCLI模式的"占位符→代理替换"比在MCP server代码中硬编码密钥安全得多
3. **关注Rust生态**：OneCLI用Rust编写，反映了Agent安全工具向Rust迁移的趋势（性能和内存安全）。如果你考虑开发Agent基础设施工具，Rust值得评估
4. **轻量级、可自托管**：相比Anthropic的Vaults（绑定Claude生态），OneCLI是独立可部署的，适合自定义Agent系统

## 自评

| 维度 | 分数 | 权重 | 加权 |
|------|------|------|------|
| 摘要质量 | 7 | 0.25 | 1.75 |
| 技术深度 | 7 | 0.25 | 1.75 |
| 相关性 | 7 | 0.20 | 1.40 |
| 原创性 | 7 | 0.15 | 1.05 |
| 格式规范 | 8 | 0.15 | 1.20 |
| **加权总分** | | | **7.15** |