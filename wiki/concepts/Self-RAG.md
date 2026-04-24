# Self-RAG: 自反思检索增强生成

> 论文：*Learning to Retrieve, Generate, and Critique through Self-Reflection* (arXiv:2310.11511, 2023)
> 作者：Akari Asai, Zeqiu Wu, Yizhong Wang, Chen Henry Wu, Patrick Ng, Nayeon Lee, Sewon Min, Hannaneh Hajishirzi, Luke Zettlemoyer, Sida I. Wang

## 核心问题

传统 RAG 有两个致命缺陷：
1. **盲目检索**：无论是否需要，都固定检索固定数量的文档
2. **无差别注入**：检索到的文档无论相关性高低都塞给 LLM

这导致两个后果——不需要检索时降低了 LLM 的通用能力（浪费 token），检索到的内容不相关时反而引入噪声（降低质量）。

## 设计原理

Self-RAG 的核心思路：**让 LLM 自己决定何时检索、检索什么、检索结果是否有用**。

### Reflection Tokens 机制

Self-RAG 在训练时引入了四种特殊的 reflection token，让模型在生成过程中"自我检查"：

| Token | 作用 | 时机 |
|-------|------|------|
| `Retrieve` | 判断是否需要检索外部知识 | 生成前 |
| `IsRel` | 判断检索到的文档是否相关 | 检索后 |
| `IsSup` | 判断生成内容是否有文档支撑 | 生成中 |
| `IsUse` | 判断生成内容是否有用 | 生成后 |

这些 token 不是额外的"分类器"，而是直接融入模型的生成序列中。推理时，模型通过输出这些 token 来控制自己的行为。

### 训练策略

1. **检索注释阶段**：对训练数据中的每个问题，自动标注是否需要检索
2. **反思标注阶段**：对检索到的文档和生成结果，标注相关性和有用性
3. **统一训练**：将 retrieval tokens 和 reflection tokens 一起训练到同一个 LM 中

关键在于：这不是一个外挂系统，而是**单一模型的端到端训练**。

## 与传统 RAG 的架构对比

```
传统 RAG:
Query → Retriever(固定top-k) → LLM(强制拼接) → Response

Self-RAG:
Query → LLM(输出Retrieve?) 
       ├─ No → 直接生成
       └─ Yes → Retriever → LLM(输出IsRel?)
                            ├─ 相关 → 生成(输出IsSup/IsUse自检)
                            └─ 不相关 → 跳过，继续生成
```

## 关键结果

- **7B/13B 模型**在多项任务上**超越 ChatGPT** 和 retrieval-augmented Llama2-chat
- 在长文本生成中，**事实准确率和引用准确率显著提升**
- 不需要检索时，模型退化为普通 LLM，不损失通用能力

## 对 Agent 开发的启发

### 1. 自适应工具调用
Self-RAG 的"按需检索"思想可以直接迁移到 Agent 的工具调用设计：
- 不是每个 step 都调用工具，让模型判断"这个 step 是否需要外部信息"
- 工具返回结果后，让模型评估"这个结果是否有用"，无用则跳过

### 2. 自我反思机制
在 Agent 的 action loop 中嵌入反思步骤：
```python
# 伪代码：Self-RAG 思想的 Agent 实现
def agent_step(query, history):
    # 1. 判断是否需要工具
    need_tool = llm.generate(f"是否需要工具？{query}", tokens=["NEED_TOOL", "NO_NEED"])
    
    if need_tool == "NEED_TOOL":
        result = tool_call(query)
        # 2. 判断工具结果是否相关
        is_relevant = llm.generate(f"结果相关？{result}", tokens=["RELEVANT", "IRRELEVANT"])
        if is_relevant == "IRRELEVANT":
            result = None  # 跳过，不注入上下文
    
    # 3. 生成 + 自检
    response = llm.generate(query, context=result)
    return response
```

### 3. 降低 Token 成本
对移动端 Agent 应用特别重要：按需检索意味着不需要时完全不消耗检索 token，大幅降低运行成本。

## 参见
- [[AI Agent Self-Improving]] — Agent 的自改进能力
- [[claude-context]] — 代码场景的上下文检索工具
- [[Memory Management]] — Agent 记忆管理策略
