---
title: "Google AI Edge Gallery：端侧AI应用生态平台"
category: "entities"
tags: ["On-device-AI", "Gemma", "Google", "Mobile-AI"]
rating: 7.5
description: "Google推出的端侧AI应用展示平台，支持Gemma 4 MTP推理，提供Android/iOS本地模型运行能力"
date: "2026-05-20"
---

# Google AI Edge Gallery：端侧AI应用生态平台

> tags: #On-device-AI #Gemma #Mobile-AI #MTP
> source: [Google AI Edge Gallery v1.0.14](https://reddit.com/r/LocalLLaMA/comments/1ti0g0k/google_ai_edge_gallery_v1013_v1014_updates_gemma/)
> project: [Google AI Edge Gallery](https://github.com/google-ai-edge-gallery)
> score: 技术深度7/10 | 实用价值8/10 | 时效性9/10 | 领域匹配8/10 | 综合 7.9/10

## 核心概念

Google AI Edge Gallery是一个端侧AI应用展示和开发平台，最新v1.0.14版本支持**Gemma 4 Multi-Token Prediction（MTP）**推理，标志着移动端AI从简单的图片分类/文本生成向复杂推理任务演进。Reddit 55↑ 27c，端侧AI社区关注度持续上升。

## 设计原理

- **端侧优先**：所有模型推理在设备本地完成，不依赖云端API，零延迟、零费用、数据完全本地
- **MTP集成**：v1.0.14引入Gemma 4的MTP支持，利用[MTP多Token预测](../concepts/MTP-Multi-Token-Prediction.md)加速端侧推理，对移动端算力受限场景尤为重要
- **生态定位**：不是通用推理框架（如llama.cpp/MLC-LLM），而是展示"端侧AI能做什么"的Gallery应用，降低开发者入门门槛

## 关键实现

- **支持模型**：Gemma 4（含MTP变体）、MediaPipe内置模型（图像分类/目标检测/文本生成）
- **平台**：Android + iOS
- **底层框架**：基于Google MediaPipe和LiteRT（原TensorFlow Lite），非ExecuTorch
- **版本进展**：v1.0.13→v1.0.14，主要更新为Gemma 4 MTP推理支持和性能优化

## 关联分析

- [MTP-Multi-Token-Prediction](../concepts/MTP-Multi-Token-Prediction.md) — 端侧应用MTP推理加速技术的首个移动端落地案例
- [Client-Side-Tool-Calling](../concepts/Client-Side-Tool-Calling.md) — 端侧AI能力扩展的另一个方向
- 与ExecuTorch（PyTorch端侧框架）、Nexa SDK构成端侧AI工具链竞争格局

## 可执行建议

1. **移动端AI入门**：clone AI Edge Gallery，体验Gemma 4在手机上的实际推理速度和质量，评估端侧AI是否满足业务需求
2. **鸿蒙端侧对标**：对比HarmonyOS的端侧AI能力（如基础认证课程内容），看Google方案是否可借鉴到鸿蒙开发
3. **MTP实测**：对比开启/关闭MTP的推理速度差异，量化MTP在移动端的实际加速效果
4. **架构参考**：研究其MediaPipe+LiteRT的技术栈选择，理解为何Google在端侧不用ExecuTorch

## 自评
| 维度 | 分数 | 权重 | 加权 |
|------|------|------|------|
| 摘要质量 | 7 | 0.25 | 1.75 |
| 技术深度 | 7 | 0.25 | 1.75 |
| 相关性 | 8 | 0.20 | 1.60 |
| 原创性 | 7 | 0.15 | 1.05 |
| 格式规范 | 9 | 0.15 | 1.35 |
| **加权总分** | | | **7.50** |