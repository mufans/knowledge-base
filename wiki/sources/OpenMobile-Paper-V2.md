# OpenMobile: 开放移动Agent框架

> tags: #MobileAgent #VLM #TrajectorySynthesis #Android #TaskAutomation
> source: [OpenMobile论文](https://arxiv.org/abs/2604.15093)
> score: 技术深度8/10 | 实用价值9/10 | 时效性9/10 | 领域匹配10/10 | 综合 9.0/10

## 核心概念

OpenMobile提出了一套通过**任务合成（Task Synthesis）和轨迹合成（Trajectory Synthesis）**自动生成训练数据的方法，用于构建开放域移动Agent。核心解决的是移动Agent训练数据稀缺和泛化能力不足的问题。

## 设计原理

- **Trade-off**: 传统方案依赖人工标注GUI操作轨迹，成本极高且覆盖有限。OpenMobile选择自动合成路径——用LLM生成任务描述+模拟执行轨迹，牺牲少量轨迹真实性换取海量数据覆盖
- **关键决策**: 选择VLM（视觉语言模型）作为Agent核心，而非纯文本解析方案。理由是移动端UI视觉多样性远超DOM结构，纯文本方案难以泛化
- **放弃的**: 不依赖特定App的Accessibility API，避免了App兼容性问题但损失了精确的元素定位能力

## 关键实现

- 任务合成：基于App截图+描述自动生成多样化操作任务
- 轨迹合成：使用VLM在模拟器中执行任务并记录操作链
- 数据增强：通过屏幕分辨率变化、主题切换等方式扩充训练集
- 评估基准：覆盖100+真实App的操作任务

## 关联分析

- 与[Operit](../entities/Operit.md)互补：OpenMobile提供训练方法论，Operit是Android上的实际Agent实现
- 与[VLAA-GUI](https://huggingface.co/papers/2604.15093)同属GUI Agent方向，但OpenMobile聚焦移动端
- 相关概念：[AI-Agent-Self-Improving](../concepts/AI-Agent-Self-Improving.md)中的自动数据合成思路

## 可执行建议

1. **直接借鉴**：OpenMobile的轨迹合成方法可用于自研移动Agent的训练数据生成
2. **技术路线**：若做鸿蒙AI Agent，可参考其VLM+轨迹合成的方案设计HarmonyOS版本
3. **评估框架**：其100+ App评测基准可作为自建移动Agent评测的参考标准
