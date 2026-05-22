---
title: "Anthropic Agent API 新能力"
category: "entities"
tags: ["Anthropic", "Agent", "Code-Execution", "MCP", "Files-API", "Prompt-Caching"]
rating: 9.5
description: "Anthropic API 四大新能力：Code Execution Tool、MCP Connector、Files API、Extended Prompt Caching"
date: "2026-05-17"
---

# Anthropic Agent API 新能力

> tags: #Anthropic #AgentAPI #CodeExecution #MCP #FilesAPI #PromptCaching
> source: [New capabilities for building agents on the Anthropic API](https://claude.com/blog/agent-capabilities-api)
> score: 技术深度8/10 | 实用价值9/10 | 时效性9/10 | 领域匹配9/10 | 综合 8.8/10

## 核心概念

2025年5月，Anthropic在API层面推出四个Agent构建能力：Code Execution Tool（沙箱Python执行）、MCP Connector（零代码连接MCP服务器）、Files API（跨会话文件管理）、Extended Prompt Caching（1小时TTL缓存）。这些能力与 Claude Opus 4 / Sonnet 4 协同，让开发者无需自建基础设施即可构建端到端的AI Agent。

## 设计原理

四大能力的核心设计动机是**降低Agent开发的基础设施负担**：

- **Code Execution Tool**：将Claude从"代码生成器"升级为"数据分析师"。之前Claude只能输出代码片段让用户自行运行，现在可在沙箱环境直接执行Python，迭代可视化、清洗数据集、生成报表。每个组织每天有50小时免费额度，超出后 $0.05/hr/container。
- **MCP Connector**：此前连接MCP服务器需要自建client harness处理连接管理、工具发现、错误处理。现在API层自动完成这些操作——只需在请求中传入MCP server URL，Claude自动发现工具、选择调用、管理认证。支持 Zapier、Asana 等远程MCP服务器。
- **Files API**：解决"每次请求都要重新上传文件"的痛点。上传一次，跨会话引用。特别适合知识库、技术文档、数据集等大文件场景。Files API与Code Execution集成，Claude可在代码执行中直接读取上传的文件并生成图表。
- **Extended Prompt Caching**：标准TTL从5分钟扩展到1小时（12x提升），成本降低最高90%，延迟降低最高85%。对长时间运行的Agent工作流（多步骤任务、跨工具协调）意义重大。

## 关键实现

### Code Execution Tool

| 参数 | 值 |
|---|---|
| 执行环境 | 沙箱Python |
| 免费额度 | 50小时/天/组织 |
| 超额计费 | $0.05/hr/container |
| 支持场景 | 金融建模、科学计算、商业智能、文档处理、统计分析 |

### MCP Connector 工作流程

1. 在API请求中配置MCP server URL
2. API自动连接服务器并获取可用工具列表
3. Claude推理选择工具和参数
4. 自动执行工具调用直到获得满意结果
5. 管理认证和错误处理
6. 返回整合了外部数据的增强响应

### Files API 特性

- 上传文档一次 → 跨对话反复引用
- 与Code Execution集成 → 执行中直接访问上传文件
- 支持输出文件（图表、报表）作为响应的一部分

### Extended Prompt Caching

| 参数 | 标准缓存 | 扩展缓存 |
|---|---|---|
| TTL | 5分钟 | 1小时 |
| 成本降低 | 最高50% | 最高90% |
| 延迟降低 | 最高50% | 最高85% |

### 典型Agent工作流组合

项目管理Agent示例：MCP Connector（连接Asana获取任务）→ Files API（上传相关报告）→ Code Execution（分析进度和风险）→ Extended Caching（维持完整上下文）→ 全程保持低成本。

## 关联分析

- 与 [Claude-Code-Source-Analysis](Claude-Code-Source-Analysis.md) 对比：Claude Code的MCP客户端需要本地配置（stdio/sse/http），API层面的MCP Connector提供了云端原生方案
- 与 [Claude-Ecosystem-Tools](../concepts/Claude-Ecosystem-Tools.md) 互补：从工具生态层面分析了Claude的工具体系
- 对 [OpenClaw](OpenClaw.md) 的启示：OpenClaw的MCP集成可以参考API层的MCP Connector设计，简化用户配置
- Extended Prompt Caching 对Agent成本优化意义重大，与 [Context-Window-Optimization](../concepts/Context-Window-Optimization.md) 直接相关

### 2026-05-19 更新：Claude Platform on AWS 正式GA

Claude Platform on AWS于2026年5月11日正式GA，带来了一系列重要的新特性：

**核心新增能力**：

| 能力 | 说明 |
|---|---|
| **Claude Managed Agents** (beta) | 托管Agent服务，大规模部署Agent |
| **Advisor Strategy** (beta) | 顾问模型策略，让Agent通过咨询顾问模型获得"智力增强" |
| **Skills** (beta) | 可复用技能系统，教Claude最佳实践 |
| **MCP Connector** (beta) | 零代码连接远程MCP服务器 |
| **Code Execution** | 沙箱Python执行 |
| **Web Search/Fetch** | 实时网络数据获取 |
| **Files API** (beta) | 跨会话文件上传和引用 |
| **Prompt Caching** | 降低成本和延迟 |

**计费模式**：通过AWS IAM认证、CloudTrail审计、AWS账单统一结算，可抵扣现有AWS承诺金额。

**模型可用**：Claude Opus 4.7、Sonnet 4.6、Haiku 4.5，新模型同步上线。

**与Bedrock的区别**：
- Claude Platform on AWS = Anthropic运营，数据在AWS边界外处理，功能最全
- Claude on Amazon Bedrock = AWS运营，数据在AWS边界内处理，适合严格数据驻留要求

**Compliance API**（2026-03-30发布）：管理员可通过API获取组织级审计日志，追踪用户活动、配置变更，支持合规审查。

### 2026-05-22 更新：Self-Hosted Sandboxes + MCP Tunnels

Anthropic于5月19日发布Claude Managed Agents重大更新，新增**自托管沙箱**和**MCP隧道**两项核心能力：

| 能力 | 状态 | 说明 |
|---|---|---|
| Self-Hosted Sandboxes | Public Beta | Agent在用户自控沙箱中执行工具，编排仍在Anthropic基础设施 |
| MCP Tunnels | Research Preview | Agent连接企业私有MCP服务器，无需暴露到公网 |

**自托管沙箱架构**：
- Agent Loop（编排、上下文管理、错误恢复）→ Anthropic基础设施
- Tool Execution（文件操作、构建、数据处理）→ 用户自控环境
- 支持的沙箱提供商：Cloudflare、Daytona、Modal、Vercel，或自建基础设施
- 用户完全控制：网络策略、审计日志、安全工具、资源规格、运行时镜像

**核心意义**：此前Managed Agents的工具执行在Anthropic管理的沙箱中，企业无法完全控制敏感数据的边界。现在工具执行移至企业基础设施内，文件和代码库不离开企业边界。Agent从"实验工具"走向企业级部署的关键一步——安全边界问题得到实质性解决。

**MCP Tunnels**：允许Agent连接企业内部的MCP服务器，无需将服务暴露到公网。结合自托管沙箱，形成完整的"Agent在企业边界内工作"方案。

## 可执行建议

1. **立即评估Code Execution API**：如果SI项目需要数据分析能力，这比自建沙箱执行环境成本低得多（50小时/天免费）
2. **MCP Connector替代自建client**：目前连接MCP服务器需要写客户端代码，API层Connector可直接使用，减少维护成本
3. **Files API用于知识库场景**：知识库项目的文档可以上传一次反复使用，避免每次请求都传文件
4. **Extended Caching用于长流程Agent**：如果构建多步骤Agent工作流，1小时TTL缓存可大幅降低成本（最高90%）

## 自评
| 维度 | 分数 | 权重 | 加权 |
|------|------|------|------|
| 摘要质量 | 8 | 0.25 | 2.00 |
| 技术深度 | 8 | 0.25 | 2.00 |
| 相关性 | 9 | 0.20 | 1.80 |
| 原创性 | 8 | 0.15 | 1.20 |
| 格式规范 | 9 | 0.15 | 1.35 |
| **加权总分** | | | **8.35** |

> 评分说明：四大能力的API设计和计费模式覆盖完整；与已有页面的交叉分析有实质内容；对用户背景（Agent开发+成本控制）有具体可执行建议。