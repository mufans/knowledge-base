---
title: "Revision Prompting — 基于diff的增量输出更新"
category: "concepts"
tags: ["Prompt-Engineering", "Token-Optimization", "Industrial-LLM", "Diff"]
rating: 8.0
description: "tags: #Prompt-Engineering #Token-Optimization #Industrial-LLM #Diff"
date: "2026-08-09"
---

# Revision Prompting — 基于diff的增量输出更新

> tags: #Prompt-Engineering #Token-Optimization #Industrial-LLM #Diff
> source: [Revision Prompting](https://revisionprompting.info/)（2026，作者联系邮箱 robert.hoenig@pqt.ch，页面声明"human wrote this page"）

## 核心思想

工业提示（Industrial Prompting）指自动化流水线中用**同一指令**反复处理不同输入的场景，典型如发票结构化抽取、文档批量翻译。当输入被更新时，朴素做法是对 `UpdatedInput` 完整重跑指令，产生两个问题：

1. **一致性缺失**：LLM 非确定性导致 `UpdatedOutput` 与原始 Output 的差异远超输入变化本身 (Fact)
2. **全量成本**：即使输入只改了一小部分，输出仍被完整重新生成，成本与首次生成相当 (Fact)

Revision Prompting 的解法：不再重跑全量输入，而是把 **原始 Input + 原始 Output + 输入 diff** 一起给 LLM，让它产出**输出补丁（OutputPatch）**，应用补丁得到 `UpdatedOutput`。

```
Instruction: Input produced Output.
The input got updated as follows: diff(Input, UpdatedInput).
Please produce a patch to update the output.
```

## 工作机制（示例）

翻译场景：e-bike 产品页从"range 80 km"改为"100 km"，朴素做法是整页重译。Revision Prompting 只给 LLM：

- 原文 + 原译文（作为上下文）
- 输入 diff：`- The Vela 3 e-bike has a range of 80 km.` / `+ ... 100 km.`
- 指令：产出更新译文的 patch

LLM 返回仅两行 diff（`- Reichweite von 80 km` / `+ Reichweite von 100 km`），其余译文保持与原始输出逐字一致 (Fact)。

## 为什么有效

- **一致性**：OutputPatch 之外的内容与原始 Output 完全相同，`UpdatedOutput` 严格受限于输入变化 (Fact)
- **时间与成本**：把大部分 token 从输出端移到输入端。处理时间大致与输出长度成正比，因此消除了大部分处理时间；输出 token 成本（贵）转为输入 token 成本（便宜）。若重跑发生在首次运行后几分钟内，**prompt caching** 还能进一步削减输入成本 (Fact)
- **官方实测**：作者称在自己工业提示中，时间减少约 **80%**、成本减少约 **65%**（未披露场景规模与模型，样本量未知，视为作者自报数据）(Fact，但外部可复现性待验证)

## 格式选择

- 通用场景：POSIX diff（[opengroup 规范](https://pubs.opengroup.org/onlinepubs/9799919799/utilities/diff.html)）
- JSON 输出：JSON Patch（[jsonpatch.com](https://jsonpatch.com/)），结构化的增删改操作天然适配
- 效果取决于 diff 编码格式与指令类型的匹配度 (Inference)

## 与已有页面的关系与增量

- [Context-Window-Optimization](Context-Window-Optimization.md) — 同属成本优化主题，但 CWO 侧重上下文压缩/裁剪，本页面是**输出侧增量更新**，机制不同
- [Prompt-Caching-Pitfalls](Prompt-Caching-Pitfalls.md) — Revision Prompting 依赖 prompt caching 进一步降本，二者是互补关系而非替代
- [Headroom](../entities/Headroom.md) — Headroom 在输入进 LLM 前压缩（输入侧），Revision Prompting 在输出生成时只产 patch（输出侧），可组合使用

## 限制与反例

- **适用面窄**：仅适用于"同一指令 + 输入增量更新"的流水线场景；ad-hoc 提示（如让编码 agent 实现新功能）不适用
- **diff 质量依赖**：如果输入变化无法用结构化 diff 表达（如语义性重构），patch 生成效果会退化 (Inference)
- **依赖上下文窗口**：需要把原始 Input + Output 完整塞回 prompt，超长文档场景下输入 token 反而膨胀，节省主要来自输出端 (Inference)
- 数据来源单一：80%/65% 为作者自报，无独立基准测试，落地前应在自己的 pipeline 上验证 (Hypothesis)

## 可执行建议

1. 移动端/服务端批量翻译、批量格式转换等流水线，可引入 Revision Prompting 模式，预期显著降本
2. 输出为结构化数据（JSON）的管道优先用 JSON Patch，文本类用 POSIX diff
3. 与 prompt caching 配合：重跑间隔越短，输入侧成本越低
