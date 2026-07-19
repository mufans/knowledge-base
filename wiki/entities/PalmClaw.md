---
title: "PalmClaw — 原生端侧移动Agent框架"
category: "entities"
tags: ["Mobile-Agent", "On-Device-AI", "Agent-Framework", "Tool-Calling"]
rating: 8.5
description: "PalmClaw是开源原生移动端Agent框架，直接在设备上管理会话、记忆、技能和工具调用，相比GUI操作方案任务成功率提升11.5%、耗时降低94.9%"
date: 2026-07-19
---

# PalmClaw — 原生端侧移动Agent框架

> tags: #Mobile-Agent #On-Device-AI #Agent-Framework #Tool-Calling #Android
> source: [PalmClaw论文 (arXiv)](https://arxiv.org/abs/2607.13027)
> project: [PalmClaw (arXiv)](https://arxiv.org/abs/2607.13027)
> score: 技术深度8/10 | 实用价值9/10 | 时效性9/10 | 领域匹配10/10 | 综合 8.5/10

## 核心概念

PalmClaw 是一个**原生运行在移动手机上的开源 Agent 框架**，彻底抛弃了传统的 GUI 操作方式（tap/swipe/type），而是将设备能力暴露为具有显式参数和结构化结果的**设备工具（Device Tools）**。Agent 框架直接在设备上管理会话（sessions）、记忆（memory）、技能（skills）、工具（tools）和 Agent 循环（agent loop），无需桌面或服务器中转。

## 设计原理

### 现有移动Agent的两大痛点

1. **GUI操作的序列过长且不稳定**
   - 现有方案（如 AppAgent、Mobile-WebAgent）通过截图+坐标定位驱动 UI
   - 每次操作需要截图→分析→定位→执行的循环，形成长而脆弱的执行链
   - 截图分辨率变化、UI版本更新都会导致流程断裂

2. **执行边界模糊**
   - GUI操作难以区分"这个UI操作属于哪个功能模块"
   - Agent 在执行过程中不知道当前在哪一步，缺乏明确的执行边界

### PalmClaw 的核心设计决策

**设计动机**：直接将设备底层能力（传感器、API、系统服务）封装为结构化的工具函数，让 Agent 像调用 API 一样操作手机，而非模拟人类手指。

**Trade-off 分析**：
- **粗粒度 vs 细粒度**：GUI操作是细粒度的（点击每个按钮），PalmClaw 的设备工具是粗粒度的（"发送短信"是一个工具）。这减少了工具调用次数，但要求每个工具的定义足够通用
- **兼容性**：设备工具依赖于系统 API 版本，不如 GUI 方案的跨版本兼容性好。但换来了更高的执行效率和确定性
- **抽象层级代价**：开发者需要为设备能力手动封装工具，不能做到"开箱即用"

## 关键实现

### 架构组件

| 组件 | 功能 |
|------|------|
| Session Manager | 管理 Agent 会话生命周期，支持中断恢复 |
| Memory Store | 设备本地记忆存储，持久化 Agent 状态 |
| Skill Registry | 注册和发现设备工具 |
| Tool Executor | 执行设备工具并返回结构化结果 |
| Agent Loop | 主循环：推理→工具选择→执行→观察→推理 |

### 性能数据

- **任务成功率**：相比最强基线提升 **11.5%**
- **完成时间**：降低 **94.9%**（从分钟级到秒级）
- **部署负担**：显著降低，无需服务器/桌面中转
- **执行边界**：每个工具调用都有明确的输入输出和执行范围

### 工具示例（推测）
```
// 设备工具示例
device.sendSms(phoneNumber: String, message: String) → { success: Boolean, messageId: String }
device.getLocation() → { latitude: Double, longitude: Double, accuracy: Float }
device.getContacts(query: String) → [{ name: String, phone: String, email: String }]
device.openApp(packageName: String, action: String) → { success: Boolean }
```

## 关联分析

- 与 [EdgeAgent](EdgeAgent.md) 对比：EdgeAgent侧重云端协作的数据透传，PalmClaw是纯端侧独立运行
- 与 [Codex-Mobile](Codex-Mobile.md) 对比：Codex-Mobile是移动端AI编程，PalmClaw是移动端Agent操作框架
- 端侧Agent是 **AI Agent + 移动端开发** 的最佳交叉方向，PalmClaw提供了从GUI驱动到API驱动的范式转换
- 设备工具设计理念与 [MCP](MCP.md) 的 Tool Calling 思路一致，只是运行环境从桌面/服务器换到了移动端

## 可执行建议

1. **作为端侧Agent架构参考**：PalmClaw 的设备工具设计模式（Device as Tool Provider）可以直接用于 Android/HarmonyOS 端侧 Agent 开发
2. **关注HF/github发布**：论文提及是开源框架，后续开源后可以研究其 Tool Executor 和 Memory Store 的具体实现
3. **结合自身移动端背景**：12年移动端开发经验 + PalmClaw 的设计理念，可以直接在移动端 Agent 方向找到切入点
4. **警惕兼容性问题**：设备工具方案对系统版本和设备型号敏感，设计时需考虑降级策略

## 自评

| 维度 | 分数 | 权重 | 加权 |
|------|------|------|------|
| 摘要质量 | 8 | 0.25 | 2.00 |
| 技术深度 | 8 | 0.25 | 2.00 |
| 相关性 | 10 | 0.20 | 2.00 |
| 原创性 | 7 | 0.15 | 1.05 |
| 格式规范 | 9 | 0.15 | 1.35 |
| **加权总分** | | | **8.40** |
