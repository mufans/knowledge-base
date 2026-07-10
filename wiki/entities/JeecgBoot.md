---
title: "JeecgBoot"
category: "entities"
tags: ["GitHub", "OS", "工具"]
rating: 8.0
description: "tags: #Low-Code #AI #Java #Code-Generation #Spring-Boot #Vue3"
date: "2026-05-12"
---

# JeecgBoot

> tags: #Low-Code #AI #Java #Code-Generation #Spring-Boot #Vue3
> source: [jeecgboot/JeecgBoot](https://github.com/jeecgboot/JeecgBoot)
> project: [JeecgBoot](https://github.com/jeecgboot/JeecgBoot)
> score: 技术深度7/10 | 实用价值8/10 | 时效性8/10 | 领域匹配7/10 | 综合 7.5/10

## 核心概念

JeecgBoot 是一个 AI 驱动的低代码开发平台，支持「低代码 + 零代码」双模式：零代码 5 分钟搭建业务系统，低代码模式一键生成前后端代码。技术栈为 Spring Boot 3 + Vue3 + Ant Design Vue，内置 AI 聊天、知识库、流程编排、MCP 与插件，一句话即可画流程图、设计表单、生成完整系统。核心价值是解决 Java 项目 80% 的重复工作，同时保持手工编码的灵活性。

## 设计原理

JeecgBoot 的设计动机是**将 AI 生成与低代码配置融合**，在"纯代码"和"纯配置"之间找到平衡点：

- **AI生成→在线配置→代码生成→手工合并**的混合开发模式：先让AI生成基础代码，通过可视化配置调整，最后手工合并定制
- **双模式架构**：零代码模式面向业务人员（拖拽表单+流程），低代码模式面向开发者（生成源码+二次开发）
- **AI Skills 能力**：集成大模型做代码生成、流程设计、表单构建，支持多模型切换
- **企业级集成**：内置权限管理、工作流引擎、报表系统，开箱即用

Trade-off：低代码平台的通病——简单场景很快，复杂定制受限。但 JeecgBoot 的"代码生成+手工合并"模式比纯低代码灵活得多，生成的是标准 Spring Boot + Vue3 代码，不依赖运行时引擎。

## 关键实现

### 技术架构
| 层 | 技术 |
|---|---|
| 后端 | Spring Boot 3 + MyBatis Plus + Spring Security |
| 前端 | Vue3 + Ant Design Vue + Vite |
| 数据库 | MySQL/PostgreSQL/Oracle 多库支持 |
| 工作流 | Activiti/Flowable |
| AI 集成 | 多模型支持 + 知识库 + MCP 插件 |
| 部署 | Docker + docker-compose |

### AI 能力矩阵
- **AI 聊天**：集成大模型对话，支持代码问答
- **知识库**：RAG 式文档检索+问答
- **流程编排**：自然语言描述→流程图自动生成
- **表单设计**：一句话描述→表单自动生成
- **代码生成**：单表/一对多/树形结构一键生成前后端 CRUD

### 目录结构
```
jeecg-boot/          # 后端 Spring Boot 项目
jeecgboot-vue3/      # 前端 Vue3 项目
docker-compose.yml   # Docker 部署配置
```

## 关联分析

- 与 [Dify](Dify.md) 对比：Dify 偏 AI Agent 编排，JeecgBoot 偏企业级业务开发，定位不同但都集成了AI能力
- Spring Boot 技术栈对 Java 开发者友好，但与移动端/AI Agent 方向（Python/TypeScript 生态）有距离
- MCP 集成值得关注：低代码平台通过 MCP 连接外部工具，是 AI + 低代码融合的趋势

## 可执行建议

1. **Java 企业开发场景参考**：如果接手 Java 企业项目，JeecgBoot 的代码生成模式可大幅提升 CRUD 开发效率
2. **AI + 低代码趋势观察**：低代码平台集成 AI Skills 是 2026 年明显趋势，理解其设计模式对 AI 应用架构有启发
3. **不建议深度投入**：与 AI Agent 转型方向不完全一致，作为架构参考即可
4. **MCP 集成思路借鉴**：如果做自己的 AI 工具平台，JeecgBoot 的 MCP 插件化方案值得参考

## 自评
| 维度 | 分数 | 权重 | 加权 |
|------|------|------|------|
| 摘要质量 | 7 | 0.25 | 1.75 |
| 技术深度 | 7 | 0.25 | 1.75 |
| 相关性 | 7 | 0.20 | 1.40 |
| 原创性 | 7 | 0.15 | 1.05 |
| 格式规范 | 8 | 0.15 | 1.20 |
| **加权总分** | | | **7.15** |

> 评分说明：摘要覆盖了核心架构和AI集成方式；技术深度分析了混合开发模式trade-off；相关性适中（Java生态但AI方向有参考价值）；原创性体现在MCP集成思路的提炼。