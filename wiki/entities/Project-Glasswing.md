---
title: "Project Glasswing：AI驱动的软件安全漏洞发现"
category: "entities"
tags: ["Security", "Vulnerability-Discovery", "Anthropic", "Mythos", "AI-Safety"]
rating: 8.5
description: "Anthropic的Project Glasswing使用Mythos Preview模型，一个月内发现超过1万个高/严重级别漏洞，AI安全能力质的飞跃"
date: "2026-05-23"
---

# Project Glasswing：AI驱动的软件安全漏洞发现

> tags: #Security #VulnerabilityDiscovery #Anthropic #Mythos #AISafety
> source: [Project Glasswing: An Initial Update](https://www.anthropic.com/research/glasswing-initial-update) | [2026-05-23-每日技术新闻](../../raw/inbox/2026-05-23-每日技术新闻.md)
> score: 技术深度8/10 | 实用价值7/10 | 时效性9/10 | 领域匹配7/10 | 综合 7.8/10

## 核心概念

Anthropic于2025年4月启动Project Glasswing，联合约50个合作伙伴，使用**Claude Mythos Preview**模型扫描全球最重要的开源软件项目。一个月内发现**超过1万个高/严重级别安全漏洞**。多个合作伙伴报告漏洞发现速度提升10倍以上。这一进展标志着AI在网络安全领域从"辅助工具"进化为"主力发现引擎"。

## 设计原理

### AI安全能力的范式转变
传统安全审计受限于人类审计员的速度。Glasswing改变了这个瓶颈：**安全进展的限制从"发现漏洞的速度"变成了"验证、披露和修补漏洞的速度"**。AI产生的漏洞数量远超人类修复能力。

### 漏洞披露策略
采用90天延迟披露策略（行业标准）：发现漏洞后90天披露，或补丁发布后45天披露。这意味着公开数据是AI能力的滞后指标。

## 关键实现

### 核心数据
- **Cloudflare**：发现2,000个bug（400个高/严重级别），误报率优于人类测试员
- **Mozilla Firefox 150**：发现并修复271个漏洞，比Firefox 148使用Claude Opus 4.6发现的多10倍以上
- **UK AI Security Institute**：Mythos Preview是首个端到端解决其两个网络靶场（多步网络攻击模拟）的模型

### 独立评估验证
- XBOW安全平台报告Mythos Preview在攻防评估中表现突出
- 合作伙伴普遍报告漏洞发现速度提升10倍+

## 关联分析

- [Claude-Code-Source-Analysis](Claude-Code-Source-Analysis.md)：同属Anthropic生态，AI代码能力的另一面
- [Real-world-AI-Applications](../concepts/Real-world-AI-Applications.md)：AI实际应用的典型案例
- [SmartPerfetto](SmartPerfetto.md)：性能分析工具，安全+性能是移动端质量保障的双支柱

## 可执行建议

1. **安全审计实践**：AI漏洞发现能力可用于个人项目的安全扫描，关注MCP生态中的安全工具
2. **移动端安全**：鸿蒙/Android应用的安全漏洞检测是AI Agent的潜在应用方向
3. **职业方向参考**：AI+安全交叉领域是高价值赛道，值得持续关注

## 自评

| 维度 | 分数 | 权重 | 加权 |
|------|------|------|------|
| 摘要质量 | 8.5 | 0.25 | 2.13 |
| 技术深度 | 7.5 | 0.25 | 1.88 |
| 相关性 | 7.5 | 0.20 | 1.50 |
| 原创性 | 7.5 | 0.15 | 1.13 |
| 格式规范 | 8.5 | 0.15 | 1.28 |
| **加权总分** | | | **7.91** |