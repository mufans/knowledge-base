---
title: "Agent MetaSKILLs"
category: "concepts"
tags: ["agent", "工作流", "skill系统", "starlark", "可重复任务"]
rating: 8.5
description: "Swival框架提出的MetaSKILL概念——用小型程序化工作流替代静态Markdown指令，解决Agent循环任务的脆弱性问题"
date: "2026-05-06"
---

# Agent MetaSKILLs

## 核心概念

MetaSKILLs 是 Swival Agent 框架中的一种**程序化技能扩展机制**。与传统的静态 SKILL.md（纯指令文本）不同，MetaSKILLs 用 Starlark 程序定义**可重复、有界、可检查**的工作流。

**解决的核心问题**：静态技能适合一次性指令（"运行部署命令，检查健康端点"），但 Agent 的很多任务是**循环**：
- 生成答案 → 检查是否包含必要内容 → 不满足则重试
- 运行测试 → 失败反馈给 Agent → 修复 → 直到通过
- 请求补丁 → 审查 → 要求修复 → 循环

用 Markdown 描述这些循环很脆弱——模型需要每次记住并正确执行循环逻辑。MetaSKILL 把循环变成**显式程序**。

## 设计原理

### 静态 Skill vs MetaSKILL 的 trade-off

| 维度 | 静态 SKILL | MetaSKILL |
|------|-----------|-----------|
| 适用场景 | 一次性指令、指导性建议 | 需要循环/重试的程序化工作流 |
| 执行保证 | 依赖模型记忆和遵循 | 代码强制执行循环逻辑 |
| 检查性 | 无内置追踪 | trace 记录每步执行 |
| 资源控制 | 无硬限制 | 指定最大尝试次数、嵌套调用计数 |
| 结果格式 | 自由文本 | 可预测的 JSON 结构 |
| 安全性 | 依赖 host 策略 | 无文件系统/网络/环境直接访问 |

**关键设计决策**：选择 Starlark（Python 子集）作为工作流语言——图灵不完备但有足够表达力，且天然受限，不会产生安全问题。

### 为什么不用 Python/JS？

Starlark 的限制是特性不是缺陷：
- **确定性**：无并发、无 I/O、无导入
- **安全**：host 提供 `ask`/`command`/`trace`，程序无法绕过策略
- **可审计**：代码小（<64KiB），逻辑清晰

## 关键实现

### 包结构

```
skills/
  require-heading/
    SKILL.md        # 元数据 + 使用说明
    SKILL.star      # Starlark 工作流程序
```

### SKILL.md frontmatter 规范

```yaml
---
name: require-heading          # 必填，小写+连字符，匹配目录名
description: 简短描述           # 必填，<1024字符
metaskill: SKILL.star          # 可选，默认查找 SKILL.star
metaskill_language: starlark   # 可选，默认 starlark
---
```

### 典型工作流示例（重试循环）

```python
def run(input):
    task = input["task"]
    heading = input["heading"]

    for i in range(3):  # 硬限制：最多3次
        result = ask(task, {
            "purpose": "draft",
            "max_turns": 4,
        })
        if heading in result["answer"]:
            return {
                "status": "accepted",
                "answer": result["answer"],
                "attempts": i + 1,
            }
        trace("missing-heading", {"attempt": i + 1})
        task = "Revise..." + result["answer"]

    return {"status": "exhausted", "answer": result["answer"]}
```

**核心 API**：
- `ask(prompt, opts)` → 调用嵌套模型
- `command(cmd, opts)` → 通过 host 策略执行命令
- `trace(tag, data)` → 记录执行追踪

### 执行隔离

- 激活（加载 SKILL.md）和执行（运行 SKILL.star）分离
- 程序无直接文件系统/进程/网络访问
- 所有操作通过 host 代理，遵循 host 安全策略

## 关联分析

### 与其他 Agent 框架的对比

- **OpenAI Assistants**：用 tools/function calling 定义能力，但没有内建的工作流循环机制
- **LangChain/LangGraph**：用 Python/JS 定义图结构工作流，更灵活但也更复杂，有图灵完备的安全风险
- **AutoGPT**：循环逻辑在 Agent 自身，无显式程序化控制
- **MetaSKILLs**：在灵活性和安全性之间取平衡——足够表达循环逻辑，但 Starlark 的限制天然防逃逸

### 对移动端 AI Agent 的启发

1. **Skill 系统设计**：移动端 Agent 同样需要可重复的工作流（如：拍照 → OCR → 校验 → 重试）
2. **安全沙箱**：Starlark 的受限执行模型适合移动端的安全需求
3. **资源控制**：硬限制尝试次数和嵌套调用，避免移动端资源耗尽

## 可执行建议

1. **借鉴 MetaSKILL 模式设计自己的 Skill 系统**：如果构建 AI Agent 应用，区分"指导性技能"和"程序化工作流"是好的架构分层
2. **评估 Starlark 作为嵌入式工作流语言**：对于需要用户自定义工作流的场景，Starlark 是安全且轻量的选择
3. **参考 trace 机制设计可观测性**：工作流执行的可追踪性对调试和优化至关重要

## 来源

- [Agent MetaSKILLs 官方文档](https://swival.dev/pages/metaskills.html)
- 来源：Lobste.rs RSS，采集于 2026-05-06