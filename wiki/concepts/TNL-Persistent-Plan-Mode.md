# TNL: Typed Natural Language — Agent持久化规划

> tags: #Coding-Agent #Plan-Mode #Persistence #Agent-Memory #Compliance
> source: [2026-05-03-社交媒体](../../raw/inbox/2026-05-03-社交媒体.md)
> project: [TNL](https://github.com/janaraj/tnl)
> score: 技术深度9/10 | 实用价值9/10 | 时效性8/10 | 领域匹配9/10 | 综合 8.9/10

## 核心概念

TNL（Typed Natural Language）解决Coding Agent跨Session丢失规划信息的问题。核心思路是将项目规范定义为"持久化的英文合约"——使用MUST/SHOULD/MAY语义标注，由Agent提出、用户审批、后续所有Session自动遵守。A/B测试数据：Claude Opus 4.7准确率从83%提升到100%（35/35），Codex GPT-5.4从74%提升到91%。

## 设计原理

当前Coding Agent的核心痛点：每次新Session都"从零开始"，不记得之前的架构决策、代码规范、项目约束。CLAUDE.md等文件是静态的，无法表达复杂的条件逻辑。

TNL的设计：
- **语义分级**：MUST（必须遵守）/ SHOULD（推荐）/ MAY（可选），类似RFC 2119的关键词定义
- **持久化合约**：规则以结构化英文编写，存储为项目文件，所有Session共享
- **双向协作**：Agent可以主动提出新规则（如"发现项目中使用了XXX模式，建议将其规范化"），用户审批后生效
- **Hook集成**：通过PreToolUse Hook在Agent执行操作前自动检查合规性

**Trade-off分析**：
- 增加了初始设置成本（需要定义规则集），但显著减少后续Session的"重新理解项目"开销
- 规则过多会约束Agent的灵活性，需要在覆盖率和自由度之间平衡
- 依赖Agent的理解能力——规则写得模糊可能导致误判

## 关键实现

- **规则文件格式**：类似自然语言的Markdown，但带有MUST/SHOULD/MAY标记
- **PreToolUse Hook**：在Agent调用工具（如写文件、执行命令）前触发规则检查
- **MCP Server集成**：可作为MCP工具提供给Agent，支持运行时规则查询
- **效果验证**：A/B测试框架，对比有/无TNL规则集的Agent表现
- **具体数据**：
  - Claude Opus 4.7: 83% → 100% (+17pp, n=35)
  - Codex GPT-5.4: 74% → 91% (+17pp)

## 关联分析

- Agent记忆系统：[Memory-Management](../concepts/Memory-Management.md) 讨论了Agent记忆的层次结构
- CLAUDE.md模式：TNL可视为CLAUDE.md的增强版，增加了语义分级和自动合规检查
- Skills系统：[Skill-Auto-Creation](../concepts/Skill-Auto-Creation.md) 关注Agent能力扩展，TNL关注Agent行为约束

## 可执行建议

1. **立即应用**：在你的项目中创建TNL规则文件，将CLAUDE.md中的关键规范迁移为MUST/SHOULD/MAY格式
2. **渐进式定义**：从最重要的5-10条规则开始，不要一次性定义过多
3. **数据驱动**：记录应用TNL前后的Agent准确率变化，量化ROI
4. **移动端项目**：鸿蒙/Android项目中，将架构约束（如"必须使用XX基类"、"禁止直接操作UI线程"）定义为MUST规则

## 自评
| 维度 | 分数 | 权重 | 加权 |
|------|------|------|------|
| 摘要质量 | 9 | 0.25 | 2.25 |
| 技术深度 | 9 | 0.25 | 2.25 |
| 相关性 | 9 | 0.20 | 1.80 |
| 原创性 | 8 | 0.15 | 1.20 |
| 格式规范 | 9 | 0.15 | 1.35 |
| **加权总分** | | | **8.85** |

> 评分标准：摘要质量（含具体A/B数据）| 技术深度（Hook/MCP集成分析）| 相关性（直接解决Coding Agent痛点）| 原创性（CLAUDE.md增强视角）| 格式规范（5标签/3交叉链接/完整自评）
