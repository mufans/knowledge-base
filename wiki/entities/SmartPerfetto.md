# SmartPerfetto

> tags: #Perfetto #AI-Performance #MCP #Agent #Android
> source: [SmartPerfetto GitHub](https://github.com/Gracker/SmartPerfetto)
> project: [Gracker/SmartPerfetto](https://github.com/Gracker/SmartPerfetto)
> score: 技术深度9/10 | 实用价值9/10 | 时效性9/10 | 领域匹配10/10 | 综合 9.3/10

## 核心概念

AI 驱动的 Android 性能分析平台，基于 Claude Agent SDK + MCP 协议 + Perfetto trace_processor。通过 146 个 YAML 声明式 Skill 和 20 个 MCP Tool，将 trace 数据查询、数值计算交给工具，LLM 只负责推理归因和自然语言表达，解决了 LLM 无法直接分析二进制 trace 的根本问题。

## 架构设计

### 技术栈
- **后端**: TypeScript + Express + Claude Agent SDK (Anthropic)
- **前端**: Fork Perfetto UI + 自定义 AI Assistant 插件
- **数据引擎**: trace_processor_shell (HTTP RPC, 端口池 9100-9900)
- **Agent 编排**: Claude Agent SDK + MCP Protocol (20 tools)
- **Skill 定义**: YAML 声明式 pipeline (164 个 skill)
- **部署**: Docker Compose 一键启动

### 核心架构分层

```
Frontend (Perfetto UI + AI Plugin) @ :10000
  ↓ SSE/HTTP
Backend (Express) @ :3000
  ├── agentv3 Runtime
  │   ├── ClaudeRuntime (主编排器)
  │   ├── Scene Classifier (关键词分类, <1ms)
  │   ├── System Prompt Builder (动态场景 prompt, 4500 token 预算)
  │   ├── Claude Agent SDK (MCP 协议)
  │   ├── SSE Bridge (SDK stream → 前端事件)
  │   └── Verifier (4 层验证 + 反思纠错)
  ├── MCP Server (20 tools: 9 always-on + 8 full-analysis + 3 comparison)
  ├── Skill Engine (146 YAML Skills)
  └── trace_processor_shell (HTTP RPC)
```

### 分析流程

1. **Scene Classifier**: 关键词匹配路由到 12 种场景策略 (scrolling/startup/ANR/interaction/memory/game 等)
2. **System Prompt Builder**: 动态组装 角色 + 方法论 + 场景策略 + 架构指南 + 输出格式
3. **Claude Agent SDK**: LLM 自主调用 MCP 工具，最多 30 轮
4. **Verifier**: 4 层验证 (heuristic → plan → hypothesis → LLM)，不通过则反思纠错最多 2 轮
5. **SSE 流式输出**: 实时推送分析结果到前端

## MCP 工具体系 (20 个)

### Always-on 工具 (9)
| 工具 | 用途 |
|------|------|
| execute_sql | 执行 Perfetto SQL，支持 summary=true 压缩 |
| invoke_skill | 执行 Skill pipeline |
| list_skills | 列出可用 Skills |
| detect_architecture | 检测渲染架构 (Standard/Flutter/Compose/WebView) |
| lookup_sql_schema | 查询 761 个 Perfetto stdlib 表/视图/函数 |
| query_perfetto_source | 查询 stdlib 源码 |
| list_stdlib_modules | 列出 stdlib 模块 |
| lookup_knowledge | 加载 6 个领域背景知识 |
| recall_patterns | 跨会话分析模式记忆 (加权 Jaccard 匹配) |

### 全分析模式工具 (8)
submit_plan, update_plan_phase, revise_plan, submit_hypothesis, resolve_hypothesis, write_analysis_note, fetch_artifact, flag_uncertainty

### 对比模式工具 (3)
execute_sql_on, compare_skill, get_comparison_context

## Skill 系统 (146 个)

### 分层结构
- **atomic/** (87): 单步检测，如帧耗时统计、CPU 频率查询
- **composite/** (29): 多步分析，如滚动卡顿根因分类
- **pipelines/** (28): 渲染管线检测 (23 种 Android 渲染管线)
- **deep/** (2): 深度因果分析 (blocking chain, binder tracing)
- **modules/**: 模块配置 (app/framework/hardware/kernel)
- **vendors/**: 厂商定制 (Pixel/Samsung/Xiaomi/OPPO/vivo/Honor/Qualcomm/MediaTek)

### 输出分层 (L1-L4)
- L1: 概览统计
- L2: 异常检测
- L3: 根因分类
- L4: 深度根因链 (含 Mermaid 因果图)

## Context Engineering

核心设计：LLM context 极其宝贵，必须精打细算。

- **SQL Summarizer**: SQL 结果压缩 ~85% token (统计值 + 采样)
- **Artifact Store**: Skill 结果缓存，分级获取 (summary/rows/full)，每次调用节省 ~3000 tokens
- **System Prompt**: 4500 token 预算，按场景动态组装
- **Complexity Classifier**: 简单查询走 Lightweight Mode (5 轮, 3 个工具)
- **Analysis Notes**: 抗 context compression 的持久笔记

## 安全边界

- 并发守卫 (同一 session 不允许并行)
- 超时控制 (40s/轮 × 30 轮 = 20min 上限)
- Watchdog (连续 3 次同工具失败 → 策略切换)
- Circuit Breaker (>60% 工具调用失败 → 简化分析)
- Safety Timer (Promise.race 强制超时)

## 多 LLM 支持

通过 ANTHROPIC_BASE_URL + API Proxy 支持：GLM、DeepSeek、Qwen、Kimi、豆包、OpenAI、Gemini、Ollama 本地模型等。Function calling 质量好的模型效果最佳。

## 关联分析

- 与 [SmartInspector](../syntheses/SmartPerfetto-vs-SmartInspector对比分析.md) 的详细对比见综合分析页面
- 基于 Perfetto SQL 引擎，与 Google [Perfetto](https://perfetto.dev/) 深度集成
- 使用 Claude Agent SDK 的 MCP 协议，与 [Claude](https://www.anthropic.com/claude) 生态紧密绑定

## 可执行建议

1. **关注 Skill YAML DSL 设计**: 声明式定义分析 pipeline 的模式值得 SI 项目借鉴，可将 perf_analyzer 中的 SQL 查询逻辑抽取为 YAML skill
2. **Context Engineering 实践**: SQL Summarizer 和 Artifact Store 的 token 节省策略可直接参考
3. **Verifier 4 层验证**: 反思纠错机制是提升 AI 分析质量的关键，SI 可引入类似验证循环
4. **厂商定制层**: vendors/ 目录的设备特定分析策略，对国内 Android 性能分析非常实用
