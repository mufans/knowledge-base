# trycua/cua — Computer-Use Agent 基础设施

> tags: #Computer-Use #Agent #Sandbox #Desktop-Automation
> source: [2026-04-26-新闻热点](../raw/inbox/2026-04-26-新闻热点.md)
> project: [trycua/cua](https://github.com/trycua/cua)
> score: 技术深度8/10 | 实用价值8/10 | 时效性8/10 | 领域匹配7/10 | 综合 7.8/10

## 核心概念

开源的 Computer-Use Agent 基础设施，提供沙箱环境、SDK 和基准测试，支持 macOS/Linux/Windows 全平台桌面控制。本质上是把"AI 操作电脑"这件事标准化了。

## 设计原理

CUA 解决的核心问题：**如何安全地让 AI 控制桌面**。三层架构：
- **Sandbox 层**：隔离的虚拟桌面环境，AI 操作不会影响真实系统
- **SDK 层**：统一的 API 抽象，屏蔽平台差异（macOS/Linux/Windows）
- **Benchmark 层**：标准化的评估框架，衡量 Agent 在真实桌面任务上的表现

Trade-off：全平台支持意味着每个平台的深度可能不如专用方案，但标准化带来的生态效应更重要。

## 关键实现

- 沙箱基于容器化技术，支持快速启停
- SDK 提供屏幕截图、鼠标键盘操作、窗口管理等原子操作
- Benchmark 涵盖文件操作、浏览器任务、应用交互等场景
- 支持多种 VLM 作为决策核心（GPT-4o、Claude 等）

## 关联分析

- 与 [OpenClaw](OpenClaw.md) 的 browser control 能力互补：OpenClaw 控制浏览器，CUA 控制整个桌面
- Computer-Use Agent 是 [AI Agent 自我改进](AI-Agent-Self-Improving.md) 的重要测试床
- 与移动端 Agent（如 OpenMobile 论文）形成桌面端对应

## 可执行建议

1. **作为 Agent 评估工具**：用 CUA 的 benchmark 评估不同模型在桌面任务上的能力，选择最适合的
2. **构建自动化流水线**：结合 OpenClaw + CUA，实现从 Web 到桌面的全链路自动化
3. **关注安全模型**：桌面控制的安全边界比浏览器更关键，学习其沙箱设计
