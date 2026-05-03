# Client-Side Tool Calling

> tags: #Tool-Calling #Privacy #Edge-AI #BYOK #Client-Server
> source: [2026-05-03-社交媒体](../../raw/inbox/2026-05-03-社交媒体.md)
> project: [SimplePDF Copilot](https://copilot.simplepdf.com/)
> score: 技术深度8/10 | 实用价值9/10 | 时效性8/10 | 领域匹配7/10 | 综合 8.1/10

## 核心概念

Client-Side Tool Calling是一种将LLM工具调用的"意图生成"和"执行"分离的架构模式：LLM在云端生成Tool Call意图（函数名+参数），但实际执行发生在客户端（浏览器/移动端）。数据永不离开用户设备，LLM只接收执行结果。

## 设计原理

传统Tool Calling流程：用户数据 → 发送给LLM → LLM决定调用工具 → 服务端执行 → 返回结果。问题：敏感数据（PDF、文档、照片）必须上传到LLM服务端。

Client-Side模式重新定义了信任边界：
- **LLM只做决策**：生成结构化的工具调用意图（JSON格式）
- **客户端执行**：浏览器/移动端解析意图并本地执行（读取文件、填充表单、操作DOM）
- **只回传结果**：执行结果（成功/失败/摘要）回传给LLM，原始数据不离开设备

**Trade-off分析**：
- 放弃了服务端对执行环境的完全控制，换来隐私保障和零服务端存储成本
- 客户端执行能力受限（浏览器API限制 vs 服务端无限制），但现代Web API已覆盖大部分场景
- 延迟更低（无文件上传等待），但首次调用需要额外的协议协商

## 关键实现

以SimplePDF Copilot为例的架构：
- **协议层**：LLM输出标准Tool Call格式（function name + arguments），客户端解析器映射到本地API
- **BYOK（Bring Your Own Key）**：用户自带API Key，可指向任何LLM提供商（默认DeepSeek V4 Flash）
- **本地运行**：支持完全本地化运行（通过LM Studio等工具），实现零外部依赖
- **安全边界**：沙箱化的执行环境，Tool Call只允许操作预定义的API集合

对移动端的启示：这种模式天然适配移动端AI应用——敏感数据（照片、通讯录、位置）留在设备上，LLM只处理脱敏后的语义信息。

## 关联分析

- Agent安全：[CISA-NSA-Agent-Security](../sources/CISA-NSA-Agent-Security.md) 的最小权限原则在此模式中得到体现
- 苹果本地AI：Apple Foundation Models框架（macOS 26）提供了类似的本地执行能力
- MCP协议：Model Context Protocol的服务端Tool Calling与此模式的客户端执行形成互补

## 可执行建议

1. **移动端应用**：在移动端AI应用中优先考虑此模式——用户隐私数据（照片、文档）本地处理，只发送语义请求给LLM
2. **PDF/文档工具**：参考SimplePDF实现文档处理工具的客户端执行层
3. **混合架构**：设计Agent系统时，区分"决策层"（LLM）和"执行层"（客户端/服务端），敏感操作走客户端
4. **BYOK设计**：支持用户自带API Key，降低平台数据存储责任，提升用户信任

## 自评
| 维度 | 分数 | 权重 | 加权 |
|------|------|------|------|
| 摘要质量 | 9 | 0.25 | 2.25 |
| 技术深度 | 8 | 0.25 | 2.00 |
| 相关性 | 7 | 0.20 | 1.40 |
| 原创性 | 8 | 0.15 | 1.20 |
| 格式规范 | 9 | 0.15 | 1.35 |
| **加权总分** | | | **8.20** |

> 评分标准：摘要质量（完整架构流程描述）| 技术深度（trade-off：控制权vs隐私）| 相关性（移动端AI应用核心模式）| 原创性（移动端适配视角分析）| 格式规范（5标签/3交叉链接/完整自评）
