---
title: "用约束用户的思路约束LLM"
category: "sources"
tags: ["LLM-Safety", "Token-Constraints", "Structured-Output", "vLLM", "Grammar-Guided"]
rating: 8.0
description: "Andrew Godwin提出将传统用户输入约束方法论应用于LLM输出控制，通过token概率采样约束和CFG/正则实现确定性输出"
date: "2026-06-04"
---

> tags: #LLM-Safety #Token-Constraints #Structured-Output #vLLM #Grammar-Guided
> source: [Constraining LLMs Just Like Users](https://www.aeracode.org/2026/06/01/constraining-llms/)
> score: 技术深度8/10 | 实用价值8/10 | 时效性7/10 | 领域匹配7/10 | 综合 7.5/10

## 核心概念

核心观点：**不要信任LLM输出，就像不要信任用户输入一样**。与其在prompt中堆砌约束指令（仅降低违规概率），不如在推理层面对输出token做数学级约束——**从根本上禁止违规token被采样**。

## 设计原理

### 传统方法的问题
- Prompt engineering约束 = 概率性防护，可被注入攻击绕过
- Post-inference验证 = 浪费推理资源，可能多次重试仍失败

### Token级约束方案
- LLM每步从概率表采样下一个token，只需**限制可采样token集合**即可
- 例：限定输出必须是"cheese"或"onion"，则采样器只考虑`che`和`onion`开头的token
- 这不是概率约束，是**数学约束**——模型物理上无法输出其他内容

### 实现方式
- JSON Schema约束：主流推理引擎均支持
- **vLLM扩展**：支持正则表达式和上下文无关文法（CFG）约束，比JSON Schema更高效
- 推理成本与token数大致线性相关，约束越精确越省钱

## 关键实现

```python
# vLLM grammar-guided generation 示例
from vllm import LLM, SamplingParams
# 通过 regex 或 grammar 限制输出格式
params = SamplingParams(temperature=0.0, guided_regex=r"(cheese|onion)")
```

## 关联分析

- [PrefixGuard](../concepts/PrefixGuard.md)：两者都关注LLM输出安全性，但本篇侧重推理层约束，PrefixGuard侧重前缀攻击防御
- [Agent-Control-Flow](../concepts/Agent-Control-Flow.md)：Agent输出约束是Agent安全的基础层

## 可执行建议

1. **生产环境必须用token级约束**：仅靠prompt约束不足以防御注入攻击
2. **vLLM的grammar功能值得关注**：正则/CFG约束比JSON Schema更灵活高效
3. **移动端场景**：端侧LLM推理更应采用约束输出，因为端侧重试成本更高

## 自评
| 维度 | 分数 | 权重 | 加权 |
|------|------|------|------|
| 摘要质量 | 8 | 0.25 | 2.00 |
| 技术深度 | 8 | 0.25 | 2.00 |
| 相关性 | 7 | 0.20 | 1.40 |
| 原创性 | 7 | 0.15 | 1.05 |
| 格式规范 | 8 | 0.15 | 1.20 |
| **加权总分** | | | **7.65** |