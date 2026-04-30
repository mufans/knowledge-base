# GoClick

> tags: #GUI-Agent #Mobile-AI #VLM #On-Device #Element-Grounding
> source: [2026-04-30-AI论文.md](../../raw/inbox/2026-04-30-AI论文.md)
> project: [GoClick Paper](https://arxiv.org/abs/2604.23941)
> score: 技术深度9/10 | 实用价值9/10 | 时效性9/10 | 领域匹配10/10 | 综合 9.3/10

## 核心概念

GoClick是一个仅230M参数的轻量级GUI元素定位模型（GUI Element Grounding），用于根据自然语言指令在截图上精确定位界面元素。在移动端等资源受限设备上，它能以端云协作框架的形式运行：本地GoClick完成元素定位，云端大模型负责任务规划，两者协同实现低延迟的GUI Agent交互。

## 设计原理

**核心trade-off：encoder-decoder vs decoder-only架构选择**

作者发现简单缩小现有decoder-only VLM（如缩小Qwen-VL）在230M参数量级效果不佳。原因是decoder-only在小参数规模下，self-attention的计算预算不足以同时处理视觉特征和文本指令的对齐。GoClick选择encoder-decoder架构，encoder专注视觉特征提取，decoder专注指令-元素对齐，两者分工明确，在小模型上效率更高。

**Progressive Data Refinement（渐进式数据精炼）**

从10.8M原始GUI数据中，通过任务类型过滤和数据比例调整，精炼出3.8M高质量核心训练集。小模型的容量有限，数据质量比数据量更重要——噪声数据在230M参数模型上会严重干扰学习。

## 关键实现

- **模型规模**：230M参数（对比主流方案≥2.5B，缩小10倍+）
- **架构**：Encoder-Decoder（非主流的Decoder-Only）
- **训练数据**：3.8M核心集（从10.8M精炼，约35%保留率）
- **端云协作模式**：设备端GoClick定位元素 → 返回坐标给云端大模型 → 云端规划下一步操作
- **推理速度**：230M参数量使得移动端实时推理成为可能（论文未公开具体延迟数据）

## 关联分析

- GUI Agent基础设施：与[trycua-cua](../entities/trycua-cua.md)（CUA计算机使用Agent）互补，GoClick解决的是"在哪里点击"的底层定位问题
- 移动端AI方向：与[DeepSeek-V4](../entities/DeepSeek-V4.md)的端侧部署趋势一致，但GoClick更专注于GUI交互子任务
- 轻量化AI：与[Context-Window-Optimization](../concepts/Context-Window-Optimization.md)的核心理念相通——在有限资源下最大化模型能力

## 可执行建议

1. **移动端AI交互落地参考**：如果开发移动端AI助手（如鸿蒙AI应用），GoClick的端云协作架构值得借鉴——轻量模型做感知，大模型做推理
2. **数据精炼思路**：训练小模型时，不要迷信大数据集。花时间做数据质量筛选（任务类型过滤+比例调整），3.8M高质量数据可能优于10.8M原始数据
3. **架构选择启发**：小模型（<500M）场景下，encoder-decoder可能比decoder-only更适合视觉-语言对齐任务，这与当前主流LLM趋势相反

## 自评
| 维度 | 分数 | 权重 | 加权 |
|------|------|------|------|
| 摘要质量 | 9 | 0.25 | 2.25 |
| 技术深度 | 9 | 0.25 | 2.25 |
| 相关性 | 10 | 0.20 | 2.00 |
| 原创性 | 8 | 0.15 | 1.20 |
| 格式规范 | 8 | 0.15 | 1.20 |
| **加权总分** | | | **8.90** |

> 评分标准：摘要质量（具体技术细节）| 技术深度（trade-off分析）| 相关性（purpose匹配）| 原创性（独立见解）| 格式规范（标签/链接/评分）
