---
title: "EdgeDox - Android 离线文档 AI"
category: "entities"
tags: ["Android", "OnDevice-AI", "LLM", "Qwen", "Offline"]
rating: 8.5
description: "在 Android 上使用 Qwen3.5-0.8B 的离线文档 AI，完全本地运行"
date: "2026-05-17"
---

# EdgeDox - Android 离线文档 AI

> tags: #Android #OnDeviceAI #Qwen #OfflineLLM #DocumentAI #EdgeAI
> source: [EdgeDox on Google Play](https://play.google.com/store/apps/details?id=io.cyberfly.edgedox)
> score: 技术深度8/10 | 实用价值9/10 | 时效性9/10 | 领域匹配10/10 | 综合 9.0/10

## 核心概念

EdgeDox 是一个 Android 应用，使用 Qwen3.5-0.8B 模型在设备本地运行文档 AI，完全离线、无需网络连接。支持 PDF 问答、文档摘要、内容提取等功能。这是端侧 AI 在移动端的真实落地案例——在 2026 年，0.8B 参数的小模型已经可以在手机上运行并提供有价值的文档理解能力。

## 设计原理

设计动机是**在移动端实现隐私优先的文档AI**：

- **完全离线**：所有推理在设备本地完成，文档数据不离开手机。这是与云端方案（如ChatGPT文档问答）的核心差异
- **小模型路线**：Qwen3.5-0.8B 只有 8 亿参数，但经过针对性训练，在文档问答场景表现可用
- **零成本运行**：无API调用费用，模型推理完全免费
- **即时响应**：无网络延迟，本地推理速度可接受

Trade-off：0.8B模型的文档理解能力有天花板——复杂推理、跨文档分析、长上下文处理可能不如云端大模型。但隐私和离线场景是硬需求，这个Trade-off是合理的。

## 关键实现

### 技术参数
| 参数 | 值 |
|---|---|
| 模型 | Qwen3.5-0.8B |
| 参数量 | 8亿 |
| 运行环境 | Android设备本地 |
| 网络要求 | 完全离线 |
| 核心功能 | PDF问答、文档摘要、内容提取 |
| 包名 | io.cyberfly.edgedox |

### 端侧AI技术栈推测
基于当前Android端侧AI技术栈，EdgeDox可能使用：
- **推理引擎**：MediaPipe、ONNX Runtime、MLC-LLM 或 llama.cpp（Android NDK编译）
- **模型格式**：GGUF/ONNX量化（INT4/INT8降低内存占用）
- **内存优化**：0.8B模型INT4量化后约400-500MB，可在主流手机上运行
- **文档处理**：PDF解析 + 文本分块 + RAG式检索增强

### 端侧AI对比
| 方案 | 模型大小 | 离线能力 | 场景 |
|---|---|---|---|
| EdgeDox | 0.8B | 完全离线 | 文档问答 |
| Apple Intelligence | 3B | 端云混合 | 通用AI |
| Google Gemini Nano | 1.8B | 端侧优先 | 通用AI |
| [ExecuTorch](../entities/ExecuTorch.md) | 可变 | 完全离线 | 推理框架 |
| [NavixMind](../entities/NavixMind.md) | 可变 | 本地执行 | Android Agent框架 |
| [4B-Coding-Agent](../entities/4B-Coding-Agent.md) | 4B | 可离线 | Coding Agent |

## 关联分析

- 与 [Codex-Mobile](Codex-Mobile.md) 互补：Codex Mobile关注移动端编程Agent，EdgeDox关注文档AI，都是端侧AI的落地场景
- 与 [HarmonyOS-Ecosystem-2026-05](HarmonyOS-Ecosystem-2026-05.md) 直接相关：鸿蒙也在推进端侧AI能力，EdgeDox的Android实现可以作为参考
- 与 [Apple-Foundation-Models-Practice](../sources/Apple-Foundation-Models-Practice.md) 对比：Apple的端侧AI有系统级支持，Android端依赖第三方框架
- Qwen3.5-0.8B 的成功说明国产小模型在端侧场景有竞争力

## 可执行建议

1. **端侧AI方向验证**：EdgeDox证明了0.8B模型在移动端可以跑文档AI，验证了端侧AI的可行性
2. **参考技术栈**：如果做端侧AI项目，研究EdgeDox的推理引擎选择和模型量化方案
3. **鸿蒙迁移机会**：将类似方案迁移到鸿蒙平台，结合HarmonyOS的AI能力做差异化
4. **小模型+垂直场景**：0.8B参数+文档问答的"小模型+垂直场景"模式值得借鉴，不需要追求大模型

## 自评
| 维度 | 分数 | 权重 | 加权 |
|------|------|------|------|
| 摘要质量 | 8 | 0.25 | 2.00 |
| 技术深度 | 8 | 0.25 | 2.00 |
| 相关性 | 10 | 0.20 | 2.00 |
| 原创性 | 8 | 0.15 | 1.20 |
| 格式规范 | 9 | 0.15 | 1.35 |
| **加权总分** | | | **8.55** |

> 评分说明：端侧AI+Android+离线LLM是用户背景的精准匹配；0.8B模型成功运行的技术参考价值高；可执行建议包含鸿蒙迁移等具体方向。