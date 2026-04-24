# Context Window 优化：AI Coding Agent 的核心效率问题

> 源项目：[mksglu/context-mode](https://github.com/mksglu/context-mode) ⭐ 9,592
> 支持：12 个 AI 编码平台（Claude Code、Codex、Gemini CLI、Cursor 等）

## 核心问题

AI Coding Agent（如 Claude Code、Cline、Codex）在编码过程中会产生大量工具输出：
- 文件读取结果（可能数千行）
- 终端命令输出（编译日志、测试结果）
- 搜索结果（grep、find 的输出）
- 浏览器快照（DOM 树、accessibility tree）

这些输出会快速消耗 context window。以 Claude Code 为例，一次 `cat` 大文件就可能吃掉数万 token，导致：
1. **早期对话被截断**，Agent 丢失重要上下文
2. **成本飙升**，频繁触发 long context 定价
3. **质量下降**，关键指令被挤出窗口

## Context-Mode 的解决思路

Context-mode 通过**沙箱化（sandboxing）工具输出**，将冗长信息压缩或摘要化后注入 context，声称实现 **98% 的工具输出减少**。

### 核心机制（推断）

```
传统模式：
  tool_call("cat large_file.ts") → 5000行原始内容 → 全部塞入 context

Context-mode：
  tool_call("cat large_file.ts") → 5000行原始内容 
    → sandbox 处理（摘要/裁剪/结构化提取）
    → ~100行精简信息 → 塞入 context
```

### 智能裁剪策略（通用最佳实践）

1. **相关性过滤**：根据当前任务（如"修复 bug X"），只保留与 bug 相关的代码段
2. **结构化摘要**：对文件输出，提取 export 列表、函数签名、类型定义，丢弃实现细节
3. **滑动窗口**：对搜索结果，只保留匹配行及上下文 ±3 行
4. **Token 预算**：每个工具输出分配 token 预算，超预算自动截断并标注

### 对移动端 Agent 的借鉴

在移动端场景下，context 优化更加关键（移动端 API 调用成本更高、延迟更敏感）：

```python
# 移动端 Agent 的 context 管理策略
class ContextManager:
    def __init__(self, max_tokens: int = 8000):
        self.budget = max_tokens
        self.priority_queue = []  # 按优先级排序的上下文块
    
    def add_tool_output(self, output: str, priority: int, summarize: bool = True):
        tokens = estimate_tokens(output)
        if tokens > self.budget:
            if summarize:
                output = self.summarize(output, self.budget)
                tokens = estimate_tokens(output)
            else:
                output = self.truncate(output, self.budget)
                tokens = self.budget
        self.priority_queue.append((priority, output))
        self.budget -= tokens
    
    def get_context(self) -> list[str]:
        # 按 priority 排序，保留高优先级内容
        return [item[1] for item in sorted(self.priority_queue, reverse=True)]
```

## 与 Claude-context 的互补关系

| 维度 | Claude-context | Context-mode |
|------|---------------|--------------|
| **目标** | 让整个代码库可搜索 | 减少工具输出体积 |
| **方法** | 语义索引 + 向量检索 | 沙箱化 + 摘要化 |
| **时机** | 需要代码上下文时主动检索 | 每次工具调用自动压缩 |
| **定位** | "读什么" | "读多少" |

两者互补：Claude-context 决定 Agent 应该看哪些代码，Context-mode 决定看到的信息怎么精简。

## 可执行建议

1. **为 Agent 设计 token 预算系统**：每个工具调用分配最大 token 数，超预算自动摘要
2. **实现分层上下文**：核心指令（不可裁剪）> 当前任务上下文 > 工具输出（可裁剪）
3. **缓存工具输出**：同一文件多次读取时，使用摘要版本而非原始版本
4. **监控 context 使用率**：记录每次 turn 的 token 消耗，识别"吞 token"的工具

## 参见
- [[claude-context]] — 代码搜索 MCP，解决"找什么代码"的问题
- [[AI Agent Self-Improving]] — Agent 的自改进能力
- [[Memory Management]] — Agent 记忆与上下文管理
