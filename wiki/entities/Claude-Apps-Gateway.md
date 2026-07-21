---
title: "Claude Apps Gateway - 企业级AI访问控制网关"
category: "entities"
tags: ["Claude", "Gateway", "Enterprise", "OIDC", "SSO"]
rating: 9.0
description: "Anthropic为Claude Code推出的自托管控制网关，支持SSO登录、集中策略、角色权限和成本归属，可接入Amazon Bedrock和Google Cloud"
date: "2026-07-21"
---

# Claude Apps Gateway - 企业级AI访问控制网关

> tags: #ClaudeCode #Gateway #Enterprise #OIDC #SSO #CostManagement #Bedrock #GCP
> source: [Introducing the Claude apps gateway](https://claude.com/blog/introducing-the-claude-apps-gateway)
> score: 技术深度8/10 | 实用价值9/10 | 时效性9/10 | 领域匹配8/10 | 综合 8.5/10

## 核心概念

Claude Apps Gateway 是 Anthropic 为 Claude Code 推出的**自托管企业控制网关**，一个统计状态容器（Linux + PostgreSQL），部署在企业基础设施上，提供集中式 SSO 登录、策略管理和成本归属能力。支持接入 Amazon Bedrock、Google Cloud 或 Claude API 作为推理后端。

## 设计原理

**解决的问题**：在企业环境中管理 Claude Code 时，之前每个开发者都需要独立配置云凭据、手动同步设置到每台机器，且无法追踪个人使用成本。

**核心设计思路**：将身份、策略、路由、计费从客户端分离到网关层，实现：
- **身份标准化**：通过 OIDC 协议对接企业 IdP（Google Workspace、Microsoft Entra ID、Okta），开发者登录后获得短时效会话，开发者机器上不存储长期秘密
- **策略集中化**：管理员在服务端定义默认设置，客户端登录时自动应用，网关在每个请求上强制执行策略
- **可观测性**：客户端在每次请求上打上用量标记，网关通过 OTLP 协议传输到企业自建收集器，数据不出企业网络

**关键架构决策**：
- 网关和 Claude Code 客户端使用同一个 claude 二进制构建，确保 `/login` 流感知网关存在，客户端登录时自动应用托管设置
- 零信任设计：仅作为 OIDC 依赖方，不存储用户凭据，不向 Anthropic 发送推理流量（除非使用 Claude API 后端）
- 协议开源：Anthropic 公布了网关使用的协议，允许其他网关开发者实现相同功能

## 关键实现

### 架构
```
开发者机器 (claude CLI)
  ↓ OIDC 登录
Claude Apps Gateway (自托管容器 + PostgreSQL)
  ↓ 持上游凭据 + 执行策略
推理后端 (Claude API | Amazon Bedrock | Google Cloud)
  → 可选故障转移
```

### 功能清单
- **Identity**：OIDC relying party，接入 Google Workspace、Microsoft Entra ID、Okta
- **Policy**：集中管理模型选择和默认设置，每次请求强制检查
- **Telemetry**：OTLP 协议中继到企业自建收集器
- **Routing**：在上游凭据持有下路由到 Claude API/Bedrock/GCP，支持故障转移
- **Spend Caps**：按日/周/月设置限额，可应用于组织/组/用户级别

### 部署配置
```yaml
# gateway.yaml 示例
oidc:
  issuer: https://your-idp.example.com
  client_id: your-client-id
upstream: 
  credential: ... # 上游凭据
database:
  url: postgresql://gateway:password@localhost:5432/gateway
```

客户端配置 `managed-settings.json`：
```json
{
  "forceLoginMethod": "gateway",
  "forceLoginGatewayUrl": "https://gateway.your-company.com"
}
```

## 关联分析

- [Claude-Code-Routines](Claude-Code-Routines.md) — Routines 的云端执行与 Gateway 的企业控制层互补
- [Anthropic-Agent-API](Anthropic-Agent-API.md) — Anthropic 的 Agent 平台 API
- [Zero-Trust-AI-Agents-Anthropic](../sources/Zero-Trust-AI-Agents-Anthropic.md) — Anthropic 的零信任 Agent 安全策略
- [GKE-Agent-Sandbox](GKE-Agent-Sandbox.md) — Google Cloud 的 Agent 沙箱方案，与 Gateway 的企业部署场景互补

## 可执行建议

1. **个人项目不太需要**：Gateway 主要面向企业/组织级部署，个人开发者直接用 Claude Code 即可
2. **了解架构模式**：Gateway 的"网关+身份+策略"三层分离设计，可参考用于自建 AI 服务平台
3. **关注成本追踪能力**：OTLP 用量指标可集成到企业现有监控系统（Grafana、Datadog），对于需要TCO分析的场景很有价值
4. **协议开放性**：Gateway 协议开源意味着未来可能有第三方实现，值得跟踪生态发展

## 自评
| 维度 | 分数 | 权重 | 加权 |
|------|------|------|------|
| 摘要质量 | 8.0 | 0.25 | 2.00 |
| 技术深度 | 8.5 | 0.25 | 2.13 |
| 相关性 | 8.5 | 0.20 | 1.70 |
| 原创性 | 8.0 | 0.15 | 1.20 |
| 格式规范 | 8.5 | 0.15 | 1.28 |
| **加权总分** | | | **8.30** |