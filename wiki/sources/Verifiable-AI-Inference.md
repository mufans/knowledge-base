---
title: "Verifiable AI Inference — 可验证AI推理"
category: "sources"
tags: ["Verifiable-Inference", "ZK-Proof", "Trusted-Execution", "AI-Accountability", "Security"]
rating: 8.0
description: "blog.vrypan.net 关于可验证AI推理的讨论，通过签名认证让AI输出可被第三方验证其来源和完整性的方法"
date: "2026-07-29"
---

# Verifiable AI Inference — 可验证AI推理

> tags: #Verifiable-Inference #ZK-Proof #Trusted-Execution #AI-Accountability #Security
> source: [Verifiable AI inference — blog.vrypan.net](https://blog.vrypan.net/2026/07/14/verifiable-ai-inference/)
> 来源摘要自 ai-knowledge-base v4 2026-07-29 采集

## 核心问题

AI Agent 越来越多用于代码审查、文档总结、合同分析和问答。在这些场景中，**结果的真实性比结果本身更重要**。(Fact)

假设 Alice 想分享一份 AI 生成的安全审查报告给 Bob，Bob 需要验证：
1. 报告确实是由特定 Agent 在特定输入下生成的
2. 报告没有被篡改
3. 无需 Bob 自己再花 token 和时间重新运行 (Fact)

## 当前方案：可信权威签名

最简单可行的方案是依赖可信权威签名体系：

```
证书内容：
Agent: OpenAI Code Security Review
Model: GPT-5.5
Agent version: v3
Input hash: SHA256(...)
Output hash: SHA256(...)
Timestamp: ...
Signature: ...
```

这并不证明模型执行了正确的推理，而是证明**可信权威认证**了该输出是由该输入产生的。和软件签名或 HTTPS CA 机制本质相同。(Fact)

## 可执行实体

- **AI Provider**：模型服务商可发布签名认证的推理结果 (Hypothesis)
- **代码托管平台**：GitHub 等平台可对 AI 生成的 PR 评论进行签名，类似于 [GitNexus](../entities/GitNexus.md) 中讨论的可信提交验证机制 (Inference)
- **独立审计方**：第三方认证机构运行 Agent 并签名结果 (Hypothesis)

## 高级方案

文章也提到更严格的方案——使用保证型执行环境或零知识证明来证明模型确实按预期执行了推理，但这些方案实现复杂度高，目前仍处于研究阶段。(Fact)

## 对用户的价值

- **Agent 输出可信度**：如果能在 [AppSmartInspector](https://github.com/mufans/AppSmartInspector) 这类诊断工具中加入验证输出的功能，可显著提升结果的可信度和可复现性 (Hypothesis)
- **移动端 AI 验证**：端侧推理结果的可验证性是一个空白领域，结合 MobileMoE 等技术，实现端到端可信推理链路 (Hypothesis)
