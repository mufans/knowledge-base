---
title: "EdgeAgent：轻量级端侧AI Agent"
category: "entities"
tags: ["EdgeAgent", "OnDevice-AI", "Mobile-Agent", "Lightweight-LLM", "Edge-Computing"]
rating: 8.0
description: "面向移动计算的轻量级端侧AI Agent框架，解决移动设备上LLM Agent的部署和推理效率问题"
date: "2026-05-21"
---

# EdgeAgent：轻量级端侧AI Agent

> tags: #EdgeAgent #OnDeviceAI #MobileAgent #LightweightLLM #EdgeComputing
> source: [EdgeAgent: Lightweight On-Device AI for Mobile Computing](https://huggingface.co/papers/2605.15921)
> project: [arXiv 2605.15921](https://arxiv.org/abs/2605.15921)
> score: 技术深度7/10 | 实用价值9/10 | 时效性8/10 | 领域匹配10/10 | 综合 8.4/10

## 核心概念

EdgeAgent 是一个面向移动计算的轻量级AI Agent框架，解决移动设备上部署LLM Agent的核心挑战：模型大小、推理延迟和能耗。移动设备的爆发式增长催生了在端侧直接运行AI Agent的需求，而非依赖云端API调用。

## 设计原理

端侧Agent面临三重约束：内存（通常<8GB可用）、算力（移动GPU/NPU有限）和电池续航。EdgeAgent的设计思路：

- **分层Agent架构**：轻量级规划和调度在端侧执行，复杂推理按需卸载到云端
- **模型量化与剪枝**：将LLM压缩到1-3B参数级别，适配移动NPU加速
- **工具调用优化**：端侧工具（摄像头、GPS、传感器）直接调用，云端工具通过API

Trade-off：端侧Agent牺牲了推理能力和工具丰富度，换取了隐私保护、低延迟和离线可用性。对于移动场景（导航、拍照理解、本地搜索），端侧优势明显。

## 关键实现

- 论文地址：[arXiv 2605.15921](https://arxiv.org/abs/2605.15921)
- 核心关联：与[ExecuTorch](../entities/ExecuTorch.md)、[Codex-Mobile](../entities/Codex-Mobile.md)形成端侧AI技术栈
- 直接对标鸿蒙端侧AI能力，可参考其Agent分层架构设计

## 关联分析

- [ExecuTorch](../entities/ExecuTorch.md)：底层推理框架，EdgeAgent的上层Agent能力可基于ExecuTorch构建
- [MobileVLN](../entities/MobileVLN.md)：同为端侧AI论文，MobileVLN聚焦导航，EdgeAgent聚焦通用Agent能力
- [Multi-Agent-Systems-Design](../concepts/Multi-Agent-Systems-Design.md)：EdgeAgent的端云协同属于分布式Agent设计

## 可执行建议

1. **直接对标鸿蒙端侧AI**：EdgeAgent的分层架构（端侧规划+云端推理）可映射到鸿蒙小艺的端云协同方案
2. **模型量化方案复用**：1-3B参数级别的量化方案可直接用于移动端Agent demo开发
3. **端侧工具调用设计**：参考其端侧工具优先策略，设计鸿蒙/Android平台的本地Agent工具链

## 自评

| 维度 | 分数 | 权重 | 加权 |
|------|------|------|------|
| 摘要质量 | 8 | 0.25 | 2.00 |
| 技术深度 | 7 | 0.25 | 1.75 |
| 相关性 | 10 | 0.20 | 2.00 |
| 原创性 | 8 | 0.15 | 1.20 |
| 格式规范 | 9 | 0.15 | 1.35 |
| **加权总分** | | | **8.30** |

> 评分说明：端侧Agent直接命中移动端+AI Agent交叉领域（相关性满分）。技术细节受限于论文全文未获取，但架构分析和落地建议充分。