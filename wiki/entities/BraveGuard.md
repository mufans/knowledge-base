---
title: "BraveGuard — Computer-Use Agent自适应安全防护框架"
category: "entities"
tags: ["Agent-security", "guard-model", "computer-use", "trajectory-safety", "adaptive-defense"]
rating: 9.0
date: "2026-06-04"
description: "自进化防御框架，从开放世界威胁信号训练Guard模型，AgentHazard准确率从38.79%提升至82.38%"
---

# BraveGuard — Computer-Use Agent自适应安全防护框架

> tags: #Agent-security #guard-model #computer-use #trajectory-safety #adaptive-defense
> source: [BraveGuard: From Open-World Threats to Safer Computer-Use Agents](https://arxiv.org/abs/2606.01166) (arXiv:2606.01166)
> score: 技术深度8/10 | 实用价值7/10 | 时效性8/10 | 领域匹配8/10 | 综合7.8/10

## 核心概念

BraveGuard是一个**自进化防御框架**，用于训练Guard模型保护Computer-Use Agent（可操作文件/终端/浏览器/工具的Agent）。核心思路：从开放世界研究文献中挖掘新兴威胁 → 实例化为可执行的Computer-Use任务 → 收集Agent轨迹 → 生成轨迹级监督信号 → 训练Guard模型。形成**自适应防御闭环**，而非基于静态benchmark的训练。

## 设计原理

### 为什么传统Guard模型不够

Computer-Use Agent的安全威胁不同于普通对话模型：
1. **多步执行轨迹中的隐蔽危害**：单步操作看起来无害，但多步组合可造成实际损害（如逐步泄露文件内容）
2. **静态benchmark滞后**：威胁不断演化，固定的安全分类体系无法覆盖新攻击模式
3. **Prompt级别检测不足**：传统Guard只检查输入/输出文本，不检查Agent的执行轨迹

### 自适应防御闭环

```
开放世界文献挖掘 → 威胁实例化(可执行任务) → Agent Rollout收集
→ 轨迹级监督信号 → Guard模型训练 → 部署检测 → 新威胁反馈 → 循环
```

核心创新：**从Research Papers到Executable Threats的自动化Pipeline**。新威胁出现后，系统自动挖掘论文中的攻击模式，构建测试任务，验证现有Guard的有效性，并补充训练数据。

### 性能数据

在AgentHazard benchmark上：
- 基线Guard模型准确率：38.79%
- BraveGuard训练后准确率：**82.38%**
- 提升幅度：+43.59个百分点（平均Guard模型设置下）

## 关键实现

### 技术架构

- **Guard模型**：支持多种backbone——Qwen3-Guard、Llama-Guard变体
- **威胁挖掘**：自动化扫描近期安全研究文献，提取攻击模式
- **轨迹级监督**：不是判断单条prompt是否安全，而是判断整条Agent执行轨迹是否安全
- **可重复Pipeline**：新威胁出现时自动迭代，无需人工干预

### 关键区分：Prompt级 vs 轨迹级安全

| 维度 | 传统Guard | BraveGuard |
|------|----------|------------|
| 检测粒度 | 单条prompt | 完整执行轨迹 |
| 训练数据 | 合成prompt对 | 真实Agent rollouts |
| 威胁覆盖 | 固定分类体系 | 开放世界挖掘+自适应 |
| 更新方式 | 人工标注 | 自动化pipeline |

## 关联分析

- 与 [LLMs-Secure-Source-Code](../sources/LLMs-Secure-Source-Code.md) 互补——后者是用Agent审计代码，BraveGuard是保护Agent自身安全
- 与 [CISA-NSA-Agent-Security](../sources/CISA-NSA-Agent-Security.md) 相关——CISA-NSA侧重政策框架，BraveGuard侧重技术实现
- 与 [AI-Agent沙箱方案讨论](../sources/AI-Agent沙箱方案讨论.md) 相关——BraveGuard的轨迹级检测是沙箱之外的补充防护层
- 与 [Agent-Skills-Architecture](../sources/Agent-Skills-Architecture.md) 相关——技能包的安全性也需要类似的Guard机制

## 可执行建议

1. **端侧Agent安全架构参考**：移动端Computer-Use Agent（如AppSmartInspector）需要类似的多步轨迹安全检测，BraveGuard的框架可参考
2. **Guard模型思路用于Skill安全审计**：第三方Agent技能包执行前，用Guard模型检查其操作轨迹是否安全
3. **自适应防御 > 静态规则**：安全规则不应是固定的，而应随威胁演化自动更新——这个理念适用于所有Agent安全设计
4. **关注论文开源代码**：如果BraveGuard开源其pipeline代码，可直接复用于构建自己的Agent安全检测系统

## 自评
| 维度 | 分数 | 权重 | 加权 |
|------|------|------|------|
| 摘要质量 | 8 | 0.25 | 2.00 |
| 技术深度 | 8 | 0.25 | 2.00 |
| 相关性 | 8 | 0.20 | 1.60 |
| 原创性 | 7 | 0.15 | 1.05 |
| 格式规范 | 9 | 0.15 | 1.35 |
| **加权总分** | | | **8.00** |

> 评分标准：摘要质量（自适应闭环+38.79%→82.38%数据）| 技术深度（架构设计+Prompt级vs轨迹级对比）| 相关性（Agent安全+端侧AI直接相关）| 原创性（端侧Agent安全建议+Skill审计思路）| 格式规范（完整标签链接评分）