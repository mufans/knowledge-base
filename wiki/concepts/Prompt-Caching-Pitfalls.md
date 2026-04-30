# Prompt Caching陷阱

> tags: #Token-Cost #Prompt-Caching #AWS-Bedrock #LLM-Infrastructure #Cost-Optimization
> source: [2026-04-30-社交媒体.md](../../raw/inbox/2026-04-30-社交媒体.md)
> score: 技术深度8/10 | 实用价值9/10 | 时效性7/10 | 领域匹配9/10 | 综合 8.3/10

## 核心概念

2026年4月HN热议案例：开发者使用Droid→LiteLLM→AWS Bedrock→Claude Opus 4.6的Agent工作流，因prompt caching未生效产生$37,901.73账单，涉及64.7亿uncached input tokens。暴露了Agent场景下prompt caching的配置复杂性和验证缺失问题——开发者以为缓存生效，实际所有请求都以全价计费。

## 设计原理

**Prompt Caching的脆弱性**

Prompt caching依赖精确的prefix匹配。Agent场景中，每次请求的system prompt可能因工具调用结果、上下文窗口滚动、动态插入的内容而微妙变化，导致缓存失效。更隐蔽的是：中间层（如LiteLLM代理）可能在转发请求时修改了prompt格式或添加了元数据，进一步破坏缓存命中条件。

**多层代理的缓存陷阱**

开发者的调用链是Droid→LiteLLM→AWS Bedrock→Claude Opus 4.6。每一层都可能：
- LiteLLM：重组prompt格式、添加system prompt前缀、修改API参数
- AWS Bedrock：有自身的缓存机制和prefix匹配规则
- Claude API：要求精确的cache_control标记和prefix顺序

三层叠加后，即使开发者在某一层正确配置了缓存标记，其他层的修改也可能导致缓存完全失效。而且没有任何一层会明确报错"缓存未命中"——你只会看到正常的API响应和持续增长的账单。

## 关键实现

**事故关键数据**：
- 账单金额：$37,901.73
- Uncached input tokens：6,470,000,000（64.7亿）
- 调用链：Droid → LiteLLM → AWS Bedrock → Claude Opus 4.6
- 根因：prompt caching配置在多层代理间失效

**防御措施**：
1. 在每层添加缓存命中率监控（AWS Bedrock提供cache hit/miss指标）
2. 设置API层面的硬性费用上限（hard budget cap）
3. 直接调用模型API，减少中间层
4. 定期审计token使用量，设置异常告警阈值

## 关联分析

- Token成本优化：与[Context-Window-Optimization](Context-Window-Optimization.md)直接相关——缓存是降低token成本的关键手段，但本案例展示了其配置脆弱性
- Claude生态：与[Claude-Code-Source-Analysis](../entities/Claude-Code-Source-Analysis.md)相关，Claude Code自身也有缓存机制，需确保配置正确
- Agent基础设施：与[Weak-Model-Orchestration](Weak-Model-Orchestration.md)互补——弱模型协作从架构上降低单次调用成本，prompt caching从机制上降低重复token计费

## 可执行建议

1. **立即检查你的Agent缓存状态**：如果使用AWS Bedrock/Anthropic API，检查CloudWatch或API metrics中的cache_hit_rate。如果命中率低于预期，逐层排查
2. **设置费用告警**：在AWS Budgets或对应平台设置每日/每月费用上限告警，阈值设为正常日均的2-3倍
3. **减少代理层**：Agent调用链中的每一层都是缓存失效的风险点。如果不需要LiteLLM的模型路由功能，直接调用目标API
4. **缓存验证脚本**：在部署前编写测试脚本，发送两次相同请求，对比 billed tokens 是否有显著差异

## 自评
| 维度 | 分数 | 权重 | 加权 |
|------|------|------|------|
| 摘要质量 | 9 | 0.25 | 2.25 |
| 技术深度 | 8 | 0.25 | 2.00 |
| 相关性 | 9 | 0.20 | 1.80 |
| 原创性 | 7 | 0.15 | 1.05 |
| 格式规范 | 8 | 0.15 | 1.20 |
| **加权总分** | | | **8.30** |

> 评分标准：摘要质量（具体技术细节）| 技术深度（trade-off分析）| 相关性（purpose匹配）| 原创性（独立见解）| 格式规范（标签/链接/评分）
