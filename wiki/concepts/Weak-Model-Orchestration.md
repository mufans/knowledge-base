# 弱模型协作架构

> tags: #Multi-Agent #Token-Cost #Model-Orchestration #Prompt-Engineering #LLM-Architecture
> source: [2026-04-30-社交媒体.md](../../raw/inbox/2026-04-30-社交媒体.md)
> project: [Three Cobblers Blog](https://markhuang.ai/blog/three-cobblers-one-zhuge-liang-ai-architecture)
> score: 技术深度8/10 | 实用价值9/10 | 时效性8/10 | 领域匹配9/10 | 综合 8.5/10

## 核心概念

通过架构设计让多个低成本LLM（如Haiku级模型）以专业化分工的方式协作完成复杂任务，达到接近高端模型（如Opus）的效果，同时大幅降低Token成本。核心理念：用一个宽泛判断替换为多个窄判断，减少每个模型需要"记住"的信息量。

## 设计原理

**Giant Prompt Trap（巨型Prompt陷阱）**

默认做法是把所有需求、示例、边界条件、约束塞进一个Prompt发给最强模型。这对小模型致命——小模型的注意力容量有限，长Prompt中第二个、第三个约束极易被遗忘。不是小模型能力不够，而是工作流设计假设它应该能处理所有事情。

**三步优化策略**

1. **System/User Prompt分离**：System Prompt定义角色、优先级、约束、输出格式和评估视角；User Prompt只承载任务数据。对弱模型而言，这个分离的效果显著——System Prompt充当"轨道"，在模型看到数据前锚定行为模式
2. **专业分工（三臭皮匠）**：将一个复杂任务拆分为多个窄任务，每个子任务由独立的小模型session处理。例如代码审查：一个session检查需求覆盖、一个检查边界情况、一个提取事实、一个检查矛盾、一个润色语气。每个session只需在自己的专业角落表现合格
3. **Hub-and-Spoke编排**：一个session作为编排器（Orchestrator），不直接解决问题，而是决定哪个专家检查哪部分。编排器传递结构化摘要（非模糊印象），收集回复，在输出冲突时追问或升级到更强模型

**Temperature控制**

- 严格管道任务（分类、提取、验证）：低温度（0-0.3），追求确定性
- 创意探索任务（头脑风暴、方案生成）：中等温度（0.5-0.7）
- 编排器session：中等温度，需要判断力但不该过于发散

## 关键实现

**并行化场景**：安全审查、UX审查、成本审查、事实提取——子任务独立，可并行调用
**链式场景**：分类→提取→验证→摘要——前一步输出作为后一步输入，串行执行

编排器关键原则：
- 传递结构化摘要，不传模糊印象
- 保留分歧而非抹平差异
- 冲突时升级到更强模型或明确标注

## 关联分析

- Token成本优化：与[Context-Window-Optimization](Context-Window-Optimization.md)互补——后者优化单次调用的Token效率，本文优化多次调用的编排策略
- 多Agent协作：与[AI-Agent-Self-Improving](AI-Agent-Self-Improving.md)的Agent自改进架构理念相通，都强调专业化分工
- 编码Agent：对[Claude-Code-Source-Analysis](../entities/Claude-Code-Source-Analysis.md)等编码Agent的改进有直接参考价值——当前编码Agent多为单模型单session，可拆分为规划/编码/审查/修复等专门session

## 可执行建议

1. **审查现有Agent工作流**：检查是否有"巨型Prompt"问题。如果Prompt超过2000 token且包含多种角色/约束，考虑拆分
2. **成本敏感场景优先尝试**：在token账单高的场景（如批量文档处理、大规模代码审查），先试点弱模型协作架构，预期成本降低50-80%
3. **自建编排器模式**：Hub-and-Spoke模式可以用LangChain/LangGraph实现，编排器使用中等模型（如Sonnet），专家节点使用小模型（如Haiku）

## 自评
| 维度 | 分数 | 权重 | 加权 |
|------|------|------|------|
| 摘要质量 | 9 | 0.25 | 2.25 |
| 技术深度 | 8 | 0.25 | 2.00 |
| 相关性 | 9 | 0.20 | 1.80 |
| 原创性 | 8 | 0.15 | 1.20 |
| 格式规范 | 8 | 0.15 | 1.20 |
| **加权总分** | | | **8.45** |

> 评分标准：摘要质量（具体技术细节）| 技术深度（trade-off分析）| 相关性（purpose匹配）| 原创性（独立见解）| 格式规范（标签/链接/评分）
