---
title: "Claude Cowork：企业级AI协作平台"
category: "entities"
tags: ["Claude", "Cowork", "Enterprise-AI", "Plugins", "Agent-Platform", "Sales-Automation"]
rating: 9.5
description: "Anthropic推出的企业级AI协作平台，支持插件化定制、私有市场和跨应用编排，将Claude Code能力扩展到非技术用户"
date: "2026-05-24"
---

# Claude Cowork：企业级AI协作平台

> tags: #Claude #Cowork #Enterprise-AI #Plugins #Agent-Platform
> source: [Making Claude Cowork ready for enterprise](https://claude.com/blog/cowork-for-enterprise) | [Customize Cowork with plugins](https://claude.com/blog/cowork-plugins) | [Cowork and plugins for teams](https://claude.com/blog/cowork-plugins-across-enterprise) | [Contribution metrics](https://claude.com/blog/contribution-metrics) | [How one Anthropic seller rebuilt his team's workflows with Claude Code](https://claude.com/blog/how-anthropic-uses-claude-gtm-engineering)
> score: 技术深度8/10 | 实用价值9/10 | 时效性9/10 | 领域匹配8/10 | 综合 8.5/10

## 核心概念

Claude Cowork是Anthropic将Claude Code能力泛化到**非技术用户**的企业协作产品。2026年4月GA（Generally Available）后，核心差异在于**插件系统**——允许企业将skills、connectors、slash commands和sub-agents打包成角色专属AI助手，并通过**私有市场**在企业内部分发。Claude还可以跨Excel和PowerPoint编排工作流，端到端传递上下文。

## 设计原理

**从"通用AI助手"到"角色专属Agent"的演进：**

Cowork的设计思路是：让Claude Code的Agent能力（自主规划、工具调用、多步执行）对非开发者可用。插件系统解决了通用AI在企业场景的适配问题：

- **Skills**：定义AI"会什么"（如销售流程、法律审核标准）
- **Connectors**：连接外部数据源（CRM、知识库、内部系统）
- **Slash Commands**：预定义常用工作流的快捷入口
- **Sub-agents**：复杂任务的子任务委派

**Trade-off分析：**
- **放弃的**：完全自由的对话式交互，用户被引导到预定义流程中
- **获得的**：企业级的一致性和可控性，降低AI使用的"随机性"
- **风险**：插件质量参差不齐可能导致AI表现不稳定

**企业管控层：**
- Role-based access controls（RBAC）
- Group spend limits（部门级别费用控制）
- OpenTelemetry集成（可观测性）
- Admin console统一管理

## 关键实现

### 插件架构
```
Plugin = Skills + Connectors + Slash Commands + Sub-agents
  ↓
角色/部门专属AI助手
  ↓
Private Marketplace（企业内部分发）
```

### 贡献度量（Contribution Metrics）
- 通过GitHub集成追踪Claude Code辅助的PR和代码提交
- Anthropic内部数据：Claude Code采用后PR合并率**提升67%**
- 70-90%的代码由Claude Code辅助编写
- 仅计算"高置信度"的AI辅助代码（保守统计）

### 跨应用编排
- Excel ↔ PowerPoint端到端工作流
- 上下文在应用间自动传递
- 暗示Anthropic在构建**OS级别的AI Agent层**

## 关联分析

- [Claude-Ecosystem-Tools](../concepts/Claude-Ecosystem-Tools.md) — Claude生态工具全景
- [Context-Window-Optimization](../concepts/Context-Window-Optimization.md) — Cowork底层依赖的context管理
- [Agent-Workflow-Patterns](../concepts/Agent-Workflow-Patterns.md) — 插件中的Agent工作流模式

### 2026-07-10 更新：Government FedRAMP 部署

2026年7月，Claude Code 和 Claude Cowork 在 **Claude for Government Desktop** 中公开 Beta 上线，基于 FedRAMP High 授权环境运行：

- **政府级部署**：与商用版相同的应用，通过 FedRAMP High 授权环境交付
- **会话历史本地存储**：对话数据存储在机构管理的设备上，不离开设备边界
- **推理在云内**：推理运行在 FedRAMP High 授权环境内，非本地推理
- **适配 USA 拨款模式的计费**：按固定增量购买，设置硬性不超上限
- **层级化管理**：部门级管理员分配 seats 和预付费用量，子机构可自行管理用户
- **SCIM 组映射**：按 seat tier 配置速率限制、金额上限和允许的模型
- **分层配置**：为子机构设置默认配置，包括 Claude 可连接的内容、可用功能和交互指令
- **防篡改审计日志**：所有管理操作记录在 hash-chained 审计日志中
- **双向审批**：Anthropic 侧敏感操作需两个人审批
- **MDM 部署**：通过标准机构 MDM 平台分发

**对 Agent 企业部署的启示**：FedRAMP 合规架构提供了 Agent 企业级部署的参考模板——本地存储 + 云端推理 + 层级化权限 + 防篡改审计。这一模式同样适用于金融、医疗等高合规要求场景。

### 2026-07-19 更新：Anthropic CISO指南中的Cowork安全控制

Anthropic Deputy CISO Jason Clinton在企业Agent安全指南中详细说明了Claude Cowork的安全控制架构（五层控制）：

1. **身份来自IdP**：SAML/OIDC登录 + SCIM同步。Enterprise计划支持自定义角色，按IdP组圈定能力范围
2. **Connector白名单（双重门控）**：管理员在组织级启用connector（MCP），用户在个人级单独授权。支持per-role connector控制——启用后对该角色下的所有用户可用。Admin可限制connector中的特定动作（如"允许起草文档但禁止自动发送"）
3. **逐工具逐动作审批**：移除connector中的特定动词（如delete verb），Agent永远不会尝试不在tool list中的操作。如果担心"数据库被删"，直接从Agent的世界里移除delete动词
4. **沙盒执行**：Agent loop在Anthropic管理的隔离临时沙盒中运行。Connector授权token不进入沙盒——通过反向代理注入真实凭据，沙盒内无任何可泄露的凭据
5. **出口白名单**：控制Agent执行环境的所有出口流量，是对抗prompt injection的最强控制

**核心结论**：截至2026年7月，Anthropic超50%的PR代码由内部Claude Tag类系统编写，全部在临时VM中生成、与生产key和账号分离。模型升级曾触发Agent自主产生"Agent-to-Agent通信"行为——这证明安全边界必须基于最坏情况设计，而非当前模型能力上限。

与 [Anthropic-CISO-Agent-Security-Guide](../../sources/Anthropic-CISO-Agent-Security-Guide.md) 详细对比。

## 可执行建议

1. **企业AI落地参考**：Cowork的插件架构可作为企业内部AI平台设计的参考模板——Skills+Connectors+Commands的分层设计值得借鉴
2. **移动端AI Agent的启示**：插件系统将通用AI"角色化"的思路，同样适用于移动端AI助手的产品设计
3. **关注跨应用编排能力**：Excel↔PowerPoint的上下文传递是AI Agent从"单工具"向"工作流编排"演进的信号，移动端也应关注跨App的AI编排
4. **贡献度量体系**：Anthropic的PR追踪方法可借鉴用于量化AI工具对团队效率的实际影响

## 自评
| 维度 | 分数 | 权重 | 加权 |
|------|------|------|------|
| 摘要质量 | 8.5 | 0.25 | 2.13 |
| 技术深度 | 7.5 | 0.25 | 1.88 |
| 相关性 | 9.0 | 0.20 | 1.80 |
| 原创性 | 8.5 | 0.15 | 1.28 |
| 格式规范 | 8.5 | 0.15 | 1.28 |
| **加权总分** | | | **8.36** |

### 2026-05-26 更新

Anthropic销售主管Travis Bryant分享了Claude Cowork在企业场景的深度实践：
- **4000账户管理**：用Claude Cowork为一本4000账户的客户手册打分，过去需要RevOps/FP&A/Marketing跨团队数百小时，一晚完成
- **五维度评分模型**：分别为Tech和Industries客户定义不同评分维度（如Tech关注agent opportunity、AI commitment；Industries关注knowledge-worker density）
- **自动日报/周报**：每日自动扫描Calendar订会议室、客户会前自动拉取BigQuery消费数据+Salesforce pipeline状态生成Brief
- **交互式Dashboard**：Claude Cowork自动生成按AE territory分片排序的Dashboard，悬浮显示用例和案例

这一实践展示了Claude Cowork的**Scheduler+Skills组合**在企业非技术场景的巨大潜力——从数据拉取到报告生成到Dashboard构建，全链路自动化。

### 2026-06-06 更新

Anthropic GTM产品经理Jared Sires的案例进一步验证了**非技术人员用Claude Code构建生产工具**的可行性：
- **CLAFTS（Claude Drafts）**：销售出身、从未写代码的Jared，用Claude Code构建了Gmail内嵌的邮件自动回复工具，每天节省2-3小时
- **24小时内传播**：Slack分享后，整个销售组织在一天内开始使用
- **角色转型**：Jared从Account Executive转为GTM Product Manager，专职为销售团队构建Claude驱动的解决方案
- **技术栈**：Claude API + Claude Cowork插件系统，打包为销售团队可复用的插件
- **关键洞察**："the most empowering thing I've ever experienced"——非技术人员的Agent开发体验，验证了Cowork降低AI工具构建门槛的产品定位

### 2026-07-20 更新：移动端与 Web 端上线

2026年7月7日，Claude Cowork 开始向 **移动端和 Web 端** 滚动上线：

- **多端同步**：工作会话和文件跨设备同步，手机/平板/浏览器均可访问
- **后台持续运行**：交给 Claude 的任务在关闭笔记本后继续执行，决策仍需用户确认
- **分批开放**：Beta 优先面向 Max 用户开放，后续逐步扩大到更多计划

**核心意义**：Cowork 从桌面 CLI 扩展到移动+Web 是题中应有之义。但对用户而言，真正的增量价值是后台持续运行的能力——"close the laptop, work keeps going" 意味着 Agent 从"实时协作者"升级为"后台自主执行者"。对经常移动办公的用户而言，这是 AI Agent 从桌面工具向全天候助手的自然演进。
