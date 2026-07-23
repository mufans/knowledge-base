---
title: "Agentic Resource Discovery (ARD) — AI Agent统一资源发现规范"
category: "concepts"
tags: ["MCP", "Agent-Infrastructure", "Tool-Discovery", "Standard-Protocol"]
rating: 8.5
description: "Google联合微软、GitHub等企业发布的开放标准，让AI Agent能够跨组织自动发现、验证和访问外部工具、API和服务"
date: "2026-07-23"
---

# Agentic Resource Discovery (ARD) — AI Agent统一资源发现规范

> tags: #MCP #Agent-Infrastructure #Tool-Discovery #Standard-Protocol #Google
> source: [Google ARD规范发布](https://developers.googleblog.com/announcing-the-agentic-resource-discovery-specification/)
> project: [Google ARD Spec](https://developers.googleblog.com/announcing-the-agentic-resource-discovery-specification/)
> score: 技术深度8/10 | 实用价值8/10 | 时效性9/10 | 领域匹配8/10 | 综合 7.8/10

## 核心概念

Agentic Resource Discovery（ARD）是 Google 联合微软、GitHub 等企业发布的开放规范，为 AI Agent 建立统一的跨组织资源发现机制。它定义了一套标准化流程，让 AI Agent 能够自动发现、验证并访问外部工具、API 和服务，而不依赖预先写死的集成逻辑或静态 Endpoint 列表。

## 设计原理

### 解决的核心问题

当前 AI Agent 基础设施中，MCP 等协议解决了"如何调用工具"的运行时问题，但缺乏"如何发现工具"的早期环节。ARD 填补了这一空白，关注 Agent 调用工具前更前置的环节——资源发现。

关键区别：MCP = 执行层（怎样调用），ARD = 发现层（在哪里找到可用的工具）。

### 核心设计

ARD 引入两个核心概念：

1. **Catalog（资源目录）**：
   - 组织在自己的域名下发布一个机器可读的 `ai-catalog.json` 文件
   - 描述可提供的能力：工具、API、Skill 以及 Agent Endpoint
   - 文件托管在组织自有域名下，基于域名归属验证真实性

2. **Registry（注册中心）**：
   - 负责聚合多个 Catalog
   - 允许 Agent 根据任务意图搜索所需能力
   - 兼容 MCP、OpenAPI 等现有执行标准

### 信任与验证

ARD 的信任机制是其设计的核心：
- **基于域名的资源归属**：资源声明由域名自然验证（DNSSEC 层级），类似 DKIM/SPF 的 DNS 验证模式
- **Agent 在建立连接前即可确认资源真实性**，降低自主 Agent 调用外部服务时的安全风险
- 安全与身份认证作为系统设计的一部分，而非事后补充

### Trade-off 分析

**优势**：
- **生态统一**：一个标准覆盖多个组织，降低开发者集成不同私有工具接口的成本
- **安全内置**：从设计层面考虑了 Agent 自主调用第三方服务的信任验证
- **与现有标准兼容**：不取代 MCP/OpenAPI，而是作为发现层的补充

**局限性**：
- **工具质量依赖**：资源发现的价值取决于可供发现工具的质量和访问模式
- **计费与访问控制**：规范定义了发现机制，但未解决工具的定价和访问权限管理
- **采纳门槛**：企业需要额外的维护工作来发布和更新 Catalog

## 关键实现

### ARD 工作流程

1. Agent 通过 Registry 发起搜索请求（描述任务意图）
2. Registry 查询各组织的 Catalog，返回匹配的资源列表
3. Agent 通过域名归属验证确认资源真实性
4. Agent 选择合适的工具，通过 MCP/OpenAPI 等协议调用

### 使用场景

| 场景 | 说明 |
|------|------|
| 跨组织工具发现 | Agent 发现外部企业的 API/工具/Agent Endpoint |
| 企业内部服务发现 | 大型组织内部各团队发布能力目录 |
| 动态能力扩展 | Agent 根据任务需求动态发现新工具，无需预配置 |

### 联合发布企业

- Google（主导）
- Microsoft
- GitHub
- 其他行业合作伙伴

## 关联分析

- 与 [Stork-MCP](../entities/Stork-MCP.md) 形成互补：Stork 关注 MCP 服务器发现，ARD 提供更通用的资源发现层
- 与 [Claude-Ecosystem-Tools](../concepts/Claude-Ecosystem-Tools.md) 在"工具生态标准化"方向一致
- 与 [GKE-Agent-Sandbox](../entities/GKE-Agent-Sandbox.md) 在企业级 Agent 基础设施方面有交叉
- 对 MCP 生态的系统性补充：MCP 定义"如何调用"，ARD 定义"何处发现"

## 可执行建议

1. **关注 ARD 规范进展**：如果后续开发需要 Agent 调用外部工具，ARD 的 Catalog 格式可能成为行业标准
2. **个人知识库的 ARD 同理**：在知识库设计中，可以考虑类似"发现层"的架构——区分"内容存储"和"内容检索"两个层次
3. **实验 Catalog 发布**：在自己的项目域名下发布 `ai-catalog.json`，体验 ARD 的资源声明机制

## 自评
| 维度 | 分数 | 权重 | 加权 |
|------|------|------|------|
| 摘要质量 | 8 | 0.25 | 2.00 |
| 技术深度 | 8 | 0.25 | 2.00 |
| 相关性 | 8 | 0.20 | 1.60 |
| 原创性 | 7 | 0.15 | 1.05 |
| 格式规范 | 8 | 0.15 | 1.20 |
| **加权总分** | | | **7.85** |

> 评分说明：InfoQ 文章和 Google 官方博客提供了充分的技术细节；Catalog/Registry 的概念分析和与 MCP 的区别对比清晰；信任机制的 DNS 验证思路具体；但规范尚在早期阶段，实际落地效果待验证