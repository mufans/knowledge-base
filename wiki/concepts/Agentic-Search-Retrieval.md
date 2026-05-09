---
title: "Agentic Search 检索范式"
category: "concepts"
tags: ["RAG", "Agentic-Search", "Retrieval", "Information-Extraction"]
rating: 7.5
description: "论文提出超越语义相似度的Agent检索新范式，通过直接语料交互替代传统向量匹配"
date: "2026-05-09"
---

# Agentic Search 检索范式

> tags: #RAG #Agentic-Search #Retrieval #Information-Extraction
> source: [Beyond Semantic Similarity: Rethinking Retrieval for Agentic Search](https://huggingface.co/papers/2605.05242)
> score: 技术深度8/10 | 实用价值8/10 | 时效性9/10 | 领域匹配9/10 | 综合 8.5/10

## 核心概念

传统检索系统（无论是词汇匹配BM25还是语义向量检索）都将语料暴露为一个"文档接口"——返回文档列表，让下游模型去理解。这篇论文提出一个根本性转向：Agentic Search中，检索不应是"找相似文档"，而应是让Agent直接与语料交互，提取结构化信息。

## 设计原理

传统RAG的瓶颈：embedding相似度 ≠ 信息相关性。一篇文档可能包含关键答案但语义上与查询不相似（例如数值数据、事实性断言）。论文提出Direct Corpus Interaction（DCI），让检索从"返回文档"变为"从语料中提取答案片段"。

Trade-off：直接语料交互的计算成本远高于向量检索（需要逐段处理），但在Agent场景中，准确性的提升可以抵消成本——因为Agent可以减少多轮检索-重试循环。

## 关键实现

- 摒弃传统的top-k文档检索 → 改为语料级别的细粒度信息提取
- Agent可以在检索过程中执行多步推理，而非一次性返回结果
- 适用于需要精确事实提取的任务（如数据分析、事实核查）

## 关联分析

- 与 [Self-RAG](../concepts/Self-RAG.md) 互补：Self-RAG让模型判断"是否需要检索"，DCI重新定义"检索到的是什么"
- 对移动端AI的影响：更精准的检索意味着更少的token消耗和更低的延迟
- 可与 [RAGFlow](../entities/RAGFlow.md) 的文档解析能力结合，提升端到端准确率

## 可执行建议

1. **评估当前RAG方案的检索准确率**：如果top-k召回率不理想，DCI是值得尝试的替代方案
2. **关注论文开源实现**：如果作者释放代码，可直接替换现有RAG pipeline中的检索层
3. **权衡成本**：DCI适合高价值查询（如医疗、法律），对大规模低成本场景需评估ROI

## 自评
| 维度 | 分数 | 权重 | 加权 |
|------|------|------|------|
| 摘要质量 | 8 | 0.25 | 2.00 |
| 技术深度 | 8 | 0.25 | 2.00 |
| 相关性 | 9 | 0.20 | 1.80 |
| 原创性 | 7 | 0.15 | 1.05 |
| 格式规范 | 9 | 0.15 | 1.35 |
| **加权总分** | | | **8.20** |