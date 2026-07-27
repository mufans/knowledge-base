---
title: "Claude Fable 5"
category: "entities"
tags: ["Claude", "Anthropic", "Frontier-Model", "Agent-Architecture"]
rating: 9.2
description: "Anthropic前沿推理模型，采用自适应推理机制，在Claude Cowork中支持目标导向委托模式，在Cursor/Cognition/乐天验证了自验证、Taste Alignment和长时无人值守Agent运行能力"
date: "2026-07-27"
---

# Claude Fable 5：Anthropic 前沿推理模型

> tags: #Claude-Fable-5 #Anthropic #Adaptive-Reasoning #Max-Effort #Frontier-Model
> source: [Artificial Analysis](https://artificialanalysis.ai/models/claude-fable-5) | [OpenAI GPT-5.6发布引用](https://openai.com/index/gpt-5-6/)
> project: [Anthropic](https://www.anthropic.com)
> score: 技术深度9/10 | 实用价值9/10 | 时效性9/10 | 领域匹配9/10 | 综合 9.0/10

## 核心概念

Claude Fable 5 是 Anthropic 于 2026 年 6 月发布的前沿大语言模型，在 Artificial Analysis Intelligence Index 上排名 **#1/186**。其核心特色是 **Adaptive Reasoning（自适应推理）**——模型根据任务复杂度自动调整推理深度，在简单问题上快速响应，在复杂问题上投入更多计算。

## 设计原理

### Adaptive Reasoning 机制

Fable 5 采用了一种混合推理策略：
- **简单问题**：快速直出，节省 token 和延迟
- **困难问题**：自动激活深度推理链，投入更多计算
- **中间状态**：介于两者之间，根据置信度动态调整

这与 GPT-5.6 的 `medium→ultra` 手动选择的思路形成对比——Fable 5 是自动调节，GPT-5.6 是用户手动选择投入级别。

### Max Effort 模式

Fable 5 还提供 **Max Effort** 模式，用于应对极端困难的任务。在这个模式下，模型可以进行更长时间的推理、多次尝试和自我修正。

### Opus 4.8 Fallback

Fable 5 配备 Opus 4.8 作为备选方案，当自适应推理不确定或任务类型更适合时，可以回退到 Opus 4.8 的输出风格。

## 关键数据

### 价格

| 指标 | 数值 |
|------|------|
| 输入价格 | $10.00/1M tokens |
| 输出价格 | $50.00/1M tokens |
| Cache 写入 | $12.50/1M tokens |
| Cache 命中 | $1.00/1M tokens (-90%) |
| 输出速度 | 2.9 tokens/s |
| AI Index 排名 | #1/18660 |

### 与 GPT-5.6 Sol 对比

| 维度 | Fable 5 | GPT-5.6 Sol |
|------|---------|-------------|
| AA Intelligence Index | #1 | 接近 #1 |
| Coding Agent Index | 77.2 | **80** (领先2.8分) |
| Agent' Last Exam | 40.5 | **53.6** (+13.1) |
| 成本 | 基准 | **~1/2** (同等或更强结果) |
| 推理模式 | 自适应(自动) | 分级可调(手动) |
| 发布月份 | 2026-06 | 2026-07 |

### 2026-07-23 更新：Jacobian 猜想反例与数学推理突破

Claude Fable 在 2026 年 7 月给出了 Jacobian 猜想的反例——数学界数十年未解的难题。菲尔兹奖得主陶哲轩（Terence Tao）随后使用 ChatGPT 深入分析验证了这一结果。

**事件意义**：
- Fable 5 展示了超越语言模型的数学推理能力——不仅是"计算"，而是"发现"和"证明"
- 陶哲轩使用 ChatGPT 验证结果，标志着 AI 辅助数学研究的实际落地
- 与 [GPT-5.6](GPT-5.6.md) 的 Agent 编程和代码生成能力形成对比：不同模型在"智能"的侧重点上各有长短，Fable 在数学/科学推理上有独特优势

### 2026-07-25 更新：Cursor与Cognition的企业级信任验证

两大AI编程工具厂商在Claude Blog上分享了Fable 5在生产环境中的信任验证结果：

**Cursor（Nate Schmidt，模型评估负责人）**：Nate的工作就是评估前沿模型处理长期、真实工程问题的能力。Cursor为Fable 5设计了CoderBench，专门测试模型在长耗时（多轮次）复杂编码任务上的表现。Fable 5在CoderBench上达成绩效基准，扩展了Cursor对Agentic coding的能力边界。核心信号：**Fable 5能够处理最难的1%编码问题**。

**Cognition Devin（Silas Alberti，研究SVP）**：Silas在Devin（Cognition的AI软件工程师产品）中测试了几乎所有Claude模型，**Fable 5是第一个他愿意留下运行一整夜（8小时无人值守）并交付生产级代码的模型**。这意味着Fable 5在长时间自主运行的可靠性上达到了质变——经过验证可以信任模型独立完成复杂工程任务。

**事件意义**：
- Fable 5的可靠性已通过两个顶级AI编程产品（Cursor和Devin）的生产验证
- 从"需要人工监督"到"可无人值守"——这是Agent可靠性的一个关键门槛突破
- 与Sol在编程bench上的领先形成互补：Sol在评估指标上领先，Fable 5在长时间自主运行的稳定性上得到业界验证

### 2026-07-26 更新：Rakuten企业级Agent实战——自验证与Taste Alignment

Rakuten在Claude Blog上分享了使用Claude Fable 5构建企业级Agent的实战案例，揭示了Fable 5区别于前代模型的三项核心行为特征：

**1. 自验证（Self-Verification）**：Fable 5在任务执行过程中持续检查自己的假设和中间结果。当任务状态中途发生变化时，Fable 5能自主发现并纠正错误的第一假设，而不是沿着错误路径执行数小时后才被发现。Rakuten AI总经理Yusuke Kaji描述："Fable 5在我凌晨2点指出之前就发现了自己的错误——所以我能安心睡觉。"

**2. Taste Alignment（品味对齐）**：Kaji提出的新概念，指模型在模糊决策上做出的判断与团队偏好高度一致，即使只给出极简的指导。"Taste alignment with Fable is smoother than any previous model——比任何此前模型的对齐都要顺畅。"这意味着部署时不再需要事无巨细地定义每一条规则。

**3. 回归第一性原理**：Fable 5会在每一步重新验证原始意图，而不是机械执行计划。当发现路径偏离时，自动回到first principles重新导航到正确结果，无需人工介入调整方向。

**对Agent工程化的影响**：

| 维度 | 此前模式 | Fable 5模式 |
|------|---------|-------------|
| 任务时长 | 分钟级（需监督） | 小时级→天级（无人值守） |
| 委托单位 | 子任务（拆分好的chunk） | 完整任务（端到端） |
| 人工介入 | 频繁的中途纠偏 | 最终决策签字，中途免干预 |
| 工作模式 | 人分派→Agent执行→人检查 | 人做决策→Agent完成任务→人确认结果 |
| 错误处理 | 人工发现并纠正偏差 | 模型自检自修，人只处理系统级问题 |

**成本策略**：Rakuten采用任务完成率（task completion ratio）与单任务成本（cost per task）两项指标并行衡量，将Fable 5分配给那些额外能力能改变结果的任务，简单任务留给小模型。Fable 5的优势在于：用更少的tokens和更少的错误转向完成更多任务，且需要的人工指导更少。

**Agent跨会话记忆**：Rakuten的Agent在运行间携带记忆——"Our agents with memory remember what went wrong in past sessions and avoid repeating those mistakes." 这使错误不再累积，团队需要关注的真正需要人处理的任务保持在可控水平。

> 参考：[Rakuten案例](https://claude.com/blog/working-at-the-frontier-rakuten) | [Verification-Loops](../concepts/Verification-Loops.md) — Fable 5的自验证机制是Verification Loops理念的模型级实现

### 2026-07-27 更新：Claude Cowork 中的 Fable 5 使用指南

Anthropic 发布了 Claude Cowork 中 Fable 5 的官方使用指南，标志着Fable 5的交互模式从"写prompt让模型执行"进化为"像委托同事一样授权任务"。

**1. 模型选择策略**：Fable 5不是Cowork的默认模型。默认是Sonnet 5（日常快速任务），Opus适合确定性的深度工作，**Fable 5专为最复杂、最模糊、此前模型无法完成的项目保留**。官方建议在以下场景使用Fable 5：需要用到多个工具、需要一系列判断决策、错误代价高的工作。

**2. Effort设置与Fable 5的配合**：
- **更高effort**：启动前更多规划，运行时更多检查——适合Claude独立完成的多步项目
- **更低effort**：更快响应，保留Fable 5前沿智能——适合简单步骤组成的Agent任务
- 关键发现：**Fable 5低effort ≥ 前代模型最高effort性能**

**3. 上下文策略转变**：指导方式从"规则列表"变为"同事情境交代"——constraint只管不要做什么，context告诉工作为什么做。模型遇到决策点自行从context找答案。长对话消耗更多usage，建议新任务开新会话。

**4. 委托模式升级**：
- **委托方法**：给素材描述目标，模型自行决定执行路径
- **委托流程**：Skills编码团队流程，Fable 5自动选Skill组合
- **委托时机**：描述期望输出，模型自动创建周期性任务
- 核心变化：从"写步骤让Claude执行"变为"描述目标让Claude自行规划"

**5. 安全分类器机制**：Fable 5新增网络安全/生物学/化学分类器，触发时回退到Opus 4.8处理——会话级回退。设计保守，偶有无害请求误伤。

**6. 思维过程可视化**：Cowork侧面板实时展示计划、文件、工具和skills使用情况，可早期发现问题并一句话纠正。

> 参考：[Working with Claude Fable 5 in Claude Cowork](https://claude.com/blog/working-with-claude-fable-5-in-claude-cowork) | [Claude-Code-Effort-Model-Guide](../sources/Claude-Code-Effort-Model-Guide.md)

## 关联分析

- **[GPT-5.6](GPT-5.6.md)**：直接竞品，Anthropic与OpenAI的最新旗舰对决
- **Adaptive Reasoning vs 分级推理**：两种设计哲学——自动 vs 手动，各有优劣
- Fable 5在AI Index排名#1但被Sol在多个bench上超越
- **CursorBench vs Terminal-Bench**：不同评测环境设计差异反映Agent评估碎片化

## 可执行建议

1. **选择策略**：Fable 5配低effort是性价比最优组合——保留前沿智能同时节省成本
2. **任务委托**：从step-by-step prompt转向goal-oriented描述，给Fable 5更多自主规划空间
3. **上下文策略**：提供对比样本（初稿vs终稿）让模型自建质量标准，减少显式约束
4. **成本考量**：Sol在代码场景成本优势明显（~1/3），纯编程任务优先Sol，复杂知识工作场景用Fable 5

1. **Fable 5 在综合推理上仍然是 SOTA**，特别是需要自适应深度推理的复杂知识工作场景
2. **成本考量**：Sol 在代码生成场景下成本优势明显（约 1/3），纯编程任务优先考虑 Sol
3. **关注后续迭代**：Anthropic 可能很快推出竞品响应版本，保持关注

## 自评

| 维度 | 分数 | 权重 | 加权 |
|------|------|------|------|
| 摘要质量 | 8 | 0.25 | 2.00 |
| 技术深度 | 8 | 0.25 | 2.00 |
| 相关性 | 9 | 0.20 | 1.80 |
| 原创性 | 8 | 0.15 | 1.20 |
| 格式规范 | 9 | 0.15 | 1.35 |
| **加权总分** | | | **8.35** |