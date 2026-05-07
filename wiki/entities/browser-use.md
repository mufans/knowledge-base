---
title: "browser use"
category: "entities"
tags: ["GitHub", "框架"]
rating: 8.0
description: "tags: #BrowserAgent #ComputerUse #Playwright #Python"
date: "2026-05-07"
---

# browser-use

> tags: #BrowserAgent #ComputerUse #Playwright #Python
> source: [ai-knowledge-base/articles/2026-04-29-browser-usebrowser-use.json](https://github.com/browser-use/browser-use)
> project: [browser-use](https://github.com/browser-use/browser-use)
> score: 技术深度7/10 | 实用价值9/10 | 时效性8/10 | 领域匹配9/10 | 综合 8.25/10

## 核心概念

browser-use 是一个开源 Python 框架，让 LLM Agent 能够通过 Playwright 控制浏览器执行网页操作任务。核心思路是将浏览器 DOM 抽象为 LLM 可理解的结构化状态（元素角色、名称、坐标），让模型决定下一步操作（点击、输入、滚动等），形成"观察→决策→执行"的闭环。

## 设计原理

**分层架构**：Browser-Use 将浏览器控制分为三层——Playwright（底层浏览器控制）、Agent（任务规划与状态管理）、LLM（决策引擎）。这种分离使得底层可以独立演进（支持 stealth、proxy rotation），上层可以灵活切换不同 LLM。

**Open Source vs Cloud 策略**：开源版本适合需要自定义 tools 和深度集成的场景，Cloud 版本（托管）在 100 个真实浏览器任务 benchmark 上成功率显著更高（内置 captcha solving、proxy rotation、persistent memory）。这种双轨策略既保证了社区传播，又通过 Cloud 变现。

**DOM 抽象方式**：不同于 naive 的 screenshot→VLM 方案，browser-use 将页面解析为结构化的 accessibility tree（元素角色+名称），大幅降低 token 消耗同时保留足够的操作信息。这是性能和成本的关键 trade-off。

## 关键实现

```python
from browser_use import Agent, Browser, ChatBrowserUse
import asyncio

async def main():
    browser = Browser()
    agent = Agent(
        task="Find the number of stars of the browser-use repo",
        llm=ChatBrowserUse(),  # 内置模型，也支持 ChatGoogle/ChatAnthropic
        browser=browser,
    )
    await agent.run()
```

- 支持自定义 tools：继承 `BaseTool` 扩展 Agent 能力
- 支持 Cloud Browser 远程连接：`use_cloud=True` 实现反检测和代理轮换
- CLI 模式：`browser-use open https://example.com` 提供命令行交互
- Benchmark：100 个真实浏览器任务的开源评估集 [browser-use/benchmark](https://github.com/browser-use/benchmark)
- 模板系统：`uvx browser-use init --template advanced` 快速生成配置

## 关联分析

- 与 [OpenClaw](../entities/OpenClaw.md) 的 browser 工具对比：browser-use 更专注浏览器自动化，OpenClaw 是全功能 Agent 框架
- 与 [trycua-cua](../entities/trycua-cua.md) 对比：CUA 更通用的 Computer Use，browser-use 专注 Web 场景，DOM 级控制更精细
- 相关概念：[Self-RAG](../concepts/Self-RAG.md)（检索增强决策）

## 可执行建议

1. **评估 browser-use 作为 Web Agent 基座**：如果需要构建网页自动化 Agent（爬虫、表单填写、数据采集），browser-use 是目前最成熟的开源方案
2. **自定义 tools 扩展**：继承 `BaseTool` 添加业务特定操作（如数据提取、登录流程封装），比纯 prompt 指令更可靠
3. **Cloud vs 自建决策**：需要反检测/大规模并发 → Cloud；需要数据隐私/深度定制 → 开源自建
4. **参考 benchmark 方法论**：其 100 任务评估集可作为 Web Agent 能力评估的参考标准

## 自评
| 维度 | 分数 | 权重 | 加权 |
|------|------|------|------|
| 摘要质量 | 8 | 0.25 | 2.00 |
| 技术深度 | 7 | 0.25 | 1.75 |
| 相关性 | 9 | 0.20 | 1.80 |
| 原创性 | 7 | 0.15 | 1.05 |
| 格式规范 | 9 | 0.15 | 1.35 |
| **加权总分** | | | **7.95** |
