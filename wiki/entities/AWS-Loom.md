---
title: "AWS Loom：企业级AI Agent管理平台"
category: "entities"
tags: ["AWS", "Agent-Platform", "Identity-Propagation", "MCP", "A2A", "Enterprise"]
rating: 9.0
description: "AWS开源的企业级Agent管理参考平台，内置身份传播、基于标签的治理、Agent注册表集成和人工审核工作流"
date: "2026-07-28"
---

# AWS Loom：企业级AI Agent管理平台

> tags: #AWS #Agent-Platform #Identity-Propagation #MCP #A2A #Enterprise
> source: [InfoQ 2026-07-27](https://www.infoq.cn/article/JDgONrm19ROF1qHzfOQO) | [技术动态2026-07-28](../../raw/inbox/2026-07-28-技术动态.md)
> project: [AWS Labs Loom](https://github.com/awslabs/loom)
> score: 技术深度7/10 | 实用价值7/10 | 时效性8/10 | 领域匹配7/10 | 综合 7.25/10

## 核心概念

AWS Loom 是亚马逊云科技发布的**开源AI代理管理参考平台**，定位为企业构建自有Agent平台的参考实现（而非托管服务）。基于Strands Agents SDK构建Agent，在Amazon Bedrock AgentCore运行时上运行，解决了企业级Agent部署的七大挑战：资源标记、访问控制、部署蓝图、部署前验证、身份传播、代理泛滥管理和人工审核。

## 设计原理

### 核心架构决策

Loom采用**"代码不变，仅配置变化"**的部署模型：

- Agent使用Strands Agents编写为**预定义的可配置Python代理**
- 部署时注入行为准则、记忆资源和MCP/A2A配置
- 不同部署间代码保持一致，仅配置变化
- 平台团队扫描一次代码，添加企业级自定义设置（日志等），即可在每次部署中重复使用

**Trade-off**：这种设计牺牲了Agent的灵活性（不能运行时动态生成代码），换来了安全性和可审计性——企业安全团队可以提前审查所有可能的Agent行为路径。

### 身份传播（Identity Propagation）——最难的挑战

Loom解决的核心工程难题是**委派链上的身份传播**：

```
用户 → Agent → MCP Server → REST API → 下游系统
```

每个环节都需要能追溯到原始用户身份的访问令牌。Loom实现了：
- **完整授权码流程**（Authorization Code Flow）用于用户交互
- **RFC 8693 令牌交换流程**（Token Exchange）——最终用户和Agent的身份都传递到下游访问令牌
- **可视化跳点**：从Agent→MCP Server→API Gateway的每个跳点都有独立的代行令牌，可审查

### 治理机制

1. **标签配置文件**：每个部署资源必须包含三个必填标签（`loom:application`、`loom:group`、`loom:owner`），支持可选自定义标签（如成本中心）
2. **双层访问控制**：角色类型（Role Type）决定权限和可见范围，组标签（Group Tag）决定可查看的资源
3. **人工审核**：通过Strands Agents钩子框架实现，敏感工具调用在执行前暂停等待批准

### 密钥管理

密钥和凭据**完全不存储在Loom中**，而是保存在AWS Secrets Manager，仅在需要时调用（入站/出站认证由AgentCore Identity管理）。

## 关键实现

### 技术栈

- **Agent SDK**：Strands Agents
- **运行时**：Amazon Bedrock AgentCore
- **身份认证**：AgentCore Identity（支持RFC 8693令牌交换）
- **密钥存储**：AWS Secrets Manager
- **代理发现**：AWS Agent Registry（A2A代理卡规范 + MCP工具架构）

### 与竞品对比

| 维度 | AWS Loom | Anthropic Claude应用网关 |
|------|---------|------------------------|
| 定位 | 参考实现（需自建） | 托管产品 |
| 层次 | Agent平台层 | 访问/成本控制层 |
| 身份传播 | 完整令牌交换链 | 网关层控制 |
| 成熟度 | 演示级（AWS Labs） | 生产级 |
| 开放性 | 开源 | 闭源 |

社区评价：一位早期评测者指出"大概一周就能构建出自己的版本"，反映了Loom的参考实现性质——它更像一个"企业Agent平台该长什么样"的示范，而非拿来即用的产品。

## 关联分析

- [Claude-Apps-Gateway](Claude-Apps-Gateway.md) — Anthropic的Agent访问控制层，与Loom处于不同层级：Gateway控制"谁能用Agent"，Loom管理"Agent本身怎么部署和治理"
- [MCP-Tunnel](MCP-Tunnel.md) — MCP的安全隧道，Loom的身份传播链与此互补
- [Agent-Distributed-Infrastructure](../sources/Agent-Distributed-Infrastructure.md) — 分布式Agent基础设施的讨论，Loom提供了参考架构
- [Anthropic-CISO-Agent-Security-Guide](../sources/Anthropic-CISO-Agent-Security-Guide.md) — Agent安全指南，Loom提供了工程实现

## 可执行建议

1. **作为企业Agent平台的参考蓝图**：即使不用AWS生态，Loom解决的七大挑战（特别是身份传播和代理泛滥管理）是所有企业级Agent平台都必须面对的。可作为架构设计checklist
2. **身份传播链设计值得学习**：RFC 8693令牌交换 + 可视化跳点是当前Agent身份管理的最佳工程实践
3. **标签治理模式可复用**：即使在自己的Agent系统中，用标签（application/group/owner）管理资源归属是一个低成本但有效的治理方案
4. **暂不适合个人项目**：依赖AWS生态（Bedrock、Secrets Manager等），学习成本和运维成本对个人开发者偏高。关注其设计思路而非直接使用

## 自评

| 维度 | 分数 | 权重 | 加权 |
|------|------|------|------|
| 摘要质量 | 8 | 0.25 | 2.00 |
| 技术深度 | 7 | 0.25 | 1.75 |
| 相关性 | 7 | 0.20 | 1.40 |
| 原创性 | 7 | 0.15 | 1.05 |
| 格式规范 | 8 | 0.15 | 1.20 |
| **加权总分** | | | **7.40** |