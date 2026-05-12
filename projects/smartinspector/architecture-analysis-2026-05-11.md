# SmartInspector (SI) 项目架构分析报告

> 分析日期：2026-05-11
> 对比对象：Google perfetto-sql Skill（/tmp/android-skills/profilers/perfetto-sql/SKILL.md）

---

## 一、SI 架构和模块分析

### 1.1 整体架构

SmartInspector 是一个 **AI 驱动的跨平台移动端性能分析 CLI 工具**，核心架构基于 LangGraph 编排的多 Agent 协作流水线。整体分为 5 层：

```
┌─────────────────────────────────────────────────────┐
│                   CLI / Headless                     │  用户交互层
│   (prompt_toolkit REPL / argparse CI / WebSocket)    │
├─────────────────────────────────────────────────────┤
│              LangGraph Orchestrator                   │  编排层
│   (LLM 意图路由 → 条件分支 → 11 个节点)              │
├─────────────────────────────────────────────────────┤
│                  Agent 层                             │  业务逻辑层
│   perf_analyzer / attributor / frame_analyzer /      │
│   android_expert / explorer / deterministic /         │
│   verifier / truncator                               │
├─────────────────────────────────────────────────────┤
│                Collector 层                           │  数据采集层
│   BaseCollector ABC → PerfettoCollector (Mixin)      │
│   sched|cpu|frame|io|block|thread|sys|memory|startup │
├─────────────────────────────────────────────────────┤
│              LLM / 基础设施层                         │  基础设施层
│   LLMFactory / TokenTracker / debug_log / config /   │
│   tools (grep|glob|read) / prompts loader             │
└─────────────────────────────────────────────────────┘
```

### 1.2 核心模块详解

#### 1.2.1 LangGraph 编排层（`graph/`）

**图的构建**（`builder.py`）：定义 11 个节点和条件路由：

| 节点 | 职责 |
|------|------|
| `orchestrator` | LLM 意图分类路由（few-shot prompt，max_tokens=5） |
| `collector` | 设备 trace 采集（PerfettoCollector.summarize()） |
| `analyzer` | 性能分析（LLM + 确定性预计算） |
| `attributor` | 源码归因（Glob→Grep→Read 三步搜索） |
| `reporter` | 报告生成（Markdown/JSON，流式输出） |
| `startup` | 冷启动分析（阶段切分+瓶颈识别） |
| `metric_qa` | 自然语言指标追问（6 大类 20 指标） |
| `perf_analyzer` | 独立性能解读 |
| `android_expert` | Android 平台专家 |
| `explorer` | 源码搜索 |
| `fallback` | 通用问答 |

**路由决策**（`RouteDecision`）：
```
full_analysis → collector → analyzer → attributor → reporter
startup      → collector → analyzer → startup → attributor → reporter
trace        → collector → analyzer → END
analyze      → perf_analyzer → END
explorer     → explorer → END
android      → android_expert → (条件: analyzer 或 END)
metric_qa    → metric_qa → END
end          → fallback → END
quick        → collector → analyzer → attributor → reporter（纯确定性）
```

**状态管理**（`AgentState` TypedDict）：
- `messages`：累积对话消息（`Annotated[list, operator.add]`）
- `perf_summary` / `perf_summary_raw`：性能数据（JSON 字符串 + dict）
- `perf_analysis` / `attribution_data` / `attribution_result`：分析中间产物
- `_route`：内部路由决策
- `_trace_path`：trace 文件路径

#### 1.2.2 Collector 层（`collector/`）

采用 **Mixin 组合模式**，`PerfettoCollector` 继承 7 个 Mixin + BaseCollector：

```
BaseCollector (ABC)
  ├── PerfSummary dataclass（平台无关输出）
  └── DeviceInfo dataclass

PerfettoCollector(BaseCollector, SchedMixin, CpuMixin, FrameMixin,
                  IoMixin, BlockMixin, ThreadMixin, SysMixin)
```

**14 个 collect_* 方法覆盖 7 个数据域**：

| Mixin | 方法 | SQL 表 | 返回数据 |
|-------|------|--------|----------|
| SchedMixin | `collect_sched()` | `sched`, `thread` | 调度统计、热线程、阻塞原因 |
| CpuMixin | `collect_cpu_hotspots()` | `perf_sample`, `stack_profile_*` | CPU 火焰图数据+调用链重建 |
| CpuMixin | `collect_cpu_usage()` | `counter`, `cpu` | 每核 CPU 使用率 |
| FrameMixin | `collect_frame_timeline()` | `actual_frame_timeline_slice` | 帧时间线+jank 检测 |
| FrameMixin | `collect_view_slices()` | `slice`, `args` | View 遍历切片（doFrame/measure/layout/draw/RV） |
| FrameMixin | `collect_compose_slices()` | `slice` | Compose 重组追踪 |
| IoMixin | `collect_io_slices()` | `slice` | IO 切片（网络/数据库/图片） |
| IoMixin | `collect_input_events()` | `slice` | 触摸/输入事件 |
| BlockMixin | `collect_block_events()` | `slice`, `android_logs` | 主线程阻塞事件+堆栈 |
| ThreadMixin | `collect_thread_state()` | `sched` | 线程状态（Running/Sleeping/DiskSleep） |
| SysMixin | `collect_sys_stats()` | `counter` | 系统统计（CPU idle/freq/fork rate） |
| SysMixin | `collect_threads()` | `thread`, `process` | 线程列表 |
| （核心） | `collect_memory()` | `heap_graph_*` | Java 堆内存分析 |
| （核心） | `collect_process_memory()` | `process_counter_track` | 进程内存（RSS/anon） |

**Trace 采集**（`pull_trace_from_device()`）：
- 三级降级策略：stdin pipe → SELinux fallback（cat pipe）→ 命令行模式
- 数据源：ftrace（sched_switch/power/cpu_freq）+ atrace（11 个类别）+ linux.perf（CPU callstack）+ android.java_hprof（堆 dump）+ linux.process_stats + android.log + android.surfaceflinger.frametimeline
- 缓冲区 65536 KB，支持 on_record_start 回调（冷启动场景）

**平台抽象**：
- `CollectorRegistry`：线程安全工厂，自动发现内置 collector
- `BaseCollector` ABC：定义 `summarize()` / `close()` / `get_device_info()` 接口
- 预留 HarmonyOS（HitraceCollector）和 iOS（XcodeCollector）扩展点

#### 1.2.3 Agent 层（`agents/`）

| Agent | 模型 | 功能 | LLM 交互方式 |
|-------|------|------|-------------|
| `perf_analyzer` | LLMFactory.get("perf_analyzer") | 性能深度解读 | 单次调用 + 验证重试 |
| `attributor` | LLMFactory.get("attributor") | 源码归因 | bind_tools + 手动 tool-call loop |
| `frame_analyzer` | LLMFactory.get("frame_analyzer") | 帧分析 | 单次调用 + 工具搜索 |
| `android_expert` | LLMFactory.get("default") | Android 领域问答 | bind_tools |
| `explorer` | LLMFactory.get("default") | 代码搜索 | bind_tools |
| `deterministic` | 无 LLM | 预计算结论 | 纯 Python 计算 |

**Attributor 归因策略**（核心亮点）：
1. **Fast Path**：纯确定性搜索（Glob→Grep→Read），无需 LLM
   - 适用于：Java 类型、方法名已知、匿名内部类
   - LRU 文件缓存避免重复读取（`_FileCache`，容量 32）
2. **LLM Fallback**：手动 tool-call loop，避免 O(n²) 消息增长
   - 消息窗口裁剪：system + human + 最近 6 轮
   - 连续 3 次搜索失败自动终止
3. **依赖上下文增强**：归因后解析 import + R.layout 引用，读取关联文件

**Deterministic 预计算**（`agents/deterministic.py`）：
- 9 个分析模块，纯 Python 计算，0 token 消耗
- `_classify_severity()`：基于设备帧预算的 P0/P1/P2 分级
- `_compute_call_chain_distribution()`：调用链时间分布（树形百分比）
- `_rank_rv_hotspots()`：RecyclerView 热点排名
- `_correlate_jank_frames()`：帧↔切片↔输入事件三方关联
- `_identify_cpu_hotspots()`：CPU 热点识别
- `_analyze_thread_state()`：线程状态分析（Running vs Blocked）
- `_analyze_io_slices()` / `_analyze_compose_slices()` / `_analyze_memory()`
- `summarize_sql_result()`：SQL 结果压缩（统计摘要+分布直方图+异常采样+去重聚合）
- `compress_perf_json()`：大列表字段自动压缩（降低 60-80% token）

**验证系统**（`agents/verifier.py`）：
- L1 格式检查：数值存在性、方法名引用、长度合理性、P0/P1/P2 分级
- L2 一致性验证：P0 问题覆盖、关键数据点数值一致性（±20%）、热点方法覆盖
- L2 失败自动重试一次

#### 1.2.4 LLM 管理（`llm/factory.py`）

- `LLMFactory`：集中创建和缓存 LLM 实例
- 9 个角色：default / attributor / perf_analyzer / frame_analyzer / metric_qa / reporter / android_expert / explorer / router
- 支持角色级模型覆盖（`SI_ATTRIBUTOR_MODEL`）
- 线程安全单例

#### 1.2.5 工具系统（`tools/`）

| 工具 | 实现 | 用途 |
|------|------|------|
| `grep` | ripgrep 子进程 | 内容搜索（正则、上下文行、分页） |
| `glob` | glob 模式匹配 | 文件定位 |
| `read` | 文件读取 | 源码查看（限制行数/字节数/行长度） |
| `perfetto` | trace_processor SQL | Perfetto SQL 查询 |

#### 1.2.6 命令系统（`commands/`）

18 个 slash 命令，按职责分 5 个模块：
- `trace.py`：/trace, /record, /analyze, /frame, /open, /close
- `orchestrate.py`：/full, /startup, /report
- `hook.py`：/config, /hooks, /hook, /debug
- `device.py`：/devices, /connect, /status, /disconnect
- `session.py`：/help, /clear, /summary, /tokens
- `compare.py`：/compare
- `quick.py`：/quick

#### 1.2.7 通信层（`ws/`）

- **WebSocket Server**：CLI ↔ App 双向通信
  - Ping/Pong 心跳检测僵尸连接
  - Ready event 防止启动竞态
  - 配置下发带 msg_id + ACK 确认
  - 动态端口支持
- **Bridge Server**：Perfetto UI ↔ SI Agent
  - HTTP 静态文件服务（自托管 Perfetto UI）
  - WebSocket bridge 转发分析请求
  - 实时进度推送

#### 1.2.8 Android Hook 层（`platform/android/`）

- `TraceHook`：Pine AOP 方法 hook，`Trace.beginSection()` 注入 SI$ 标记
- `BlockMonitor`：BlockCanary-style 主线程卡顿检测，logcat 输出 SIBlock 堆栈
- `ComposeHook`：Compose Runtime TracerImpl hook，追踪重组
- `SIClient`：WebSocket 客户端
- Release 变体：纯 no-op stubs，编译器内联后零开销
- Hook 安全：嵌套深度保护、Tag 超 127 字节截断、系统 widget 过滤

---

## 二、SI 能力清单

### 2.1 数据采集能力

| # | 能力 | 描述 |
|---|------|------|
| 1 | Perfetto Trace 采集 | adb + Perfetto 配置化采集（ftrace+atrace+CPU callstack+Java heap+logcat+帧时间线） |
| 2 | 三级降级采集 | stdin pipe → SELinux cat pipe → cmdline 模式自动降级 |
| 3 | CPU 性能分析 | CPU 使用率（每核）、CPU 热点（火焰图+调用链重建） |
| 4 | 帧时间线分析 | FPS、jank 检测、慢帧排名、帧预算自适应（60Hz/120Hz/240Hz） |
| 5 | 线程状态分析 | Running/Sleeping/DiskSleep 分布、blocked_function 原因、IO 等待标识 |
| 6 | 调度分析 | 调度统计、热线程排名、阻塞原因分类 |
| 7 | 内存分析 | Java 堆分配分析、Activity/Fragment 泄漏检测、RSS/anon 趋势追踪 |
| 8 | IO 追踪 | 网络/数据库/图片 IO 独立收集、按类型聚合统计 |
| 9 | 输入事件采集 | 触摸事件时间线、与 jank 帧因果关联 |
| 10 | Compose 重组追踪 | Composable 首次组合/重组次数/耗时、重组率告警 |
| 11 | 主线程阻塞检测 | BlockMonitor 卡顿检测 + SIBlock 堆栈关联 |
| 12 | 冷启动分析 | 4 阶段切分（pre-main → App.onCreate → Activity.onCreate → 首帧渲染） |
| 13 | View 系统切片 | doFrame/measure/layout/draw/RV pipeline + 父子调用链 |

### 2.2 智能分析能力

| # | 能力 | 描述 |
|---|------|------|
| 14 | LLM 意图路由 | 自然语言 → 路由决策（full_analysis/startup/explorer/android/metric_qa 等） |
| 15 | 确定性预计算 | 9 个分析模块纯 Python 计算（严重度/调用链分布/RV 热点/jank 关联等），0 token |
| 16 | SQL 结果压缩 | 统计摘要+分布直方图+异常采样+去重聚合，降低 60-80% token |
| 17 | 源码归因 | SI$ slice → Glob→Grep→Read → 源码定位，Fast Path + LLM Fallback |
| 18 | 依赖上下文增强 | import 解析 + R.layout 引用 → 关联类/布局文件自动读取 |
| 19 | 分析质量验证 | L1 格式检查 + L2 一致性验证（数值一致性±20%、P0 覆盖率） |
| 20 | Token 预算截断 | SmartTruncator 基于优先级的段落截断（归因 > 预计算 > 线程状态 > 帧 > 分析） |
| 21 | 自然语言指标追问 | 6 大类 20 细粒度指标的即时查询（CPU/内存/UI/IO/系统/总览） |
| 22 | 帧级分析 | Perfetto UI 框选 → frame_analyzer agent → 实时进度 + 归因 |
| 23 | 快速确定性分析 | /quick 纯确定性分析（不调用 LLM），无 API Key 可用 |

### 2.3 输出和集成能力

| # | 能力 | 描述 |
|---|------|------|
| 24 | Markdown 报告 | P0/P1/P2 分级 + 源码位置 + 优化建议 |
| 25 | JSON 结构化报告 | CI/CD 友好的结构化输出（summary + issues + metrics） |
| 26 | 流式报告生成 | LLM 报告实时流式输出 |
| 27 | 报告持久化 | 自动保存到 reports/ 目录 |
| 28 | 历史对比 | /compare 两份报告对比，before/after 趋势 |
| 29 | Headless/CI 模式 | 非交互式全量流水线，JSON/Markdown 输出 |
| 30 | Token 使用追踪 | 线程安全的 token 消耗统计，按 stage 分组 |
| 31 | Perfetto UI 交互 | 自托管 Perfetto UI + SI Bridge 插件 |
| 32 | WebSocket 通信 | CLI ↔ App 双向通信，心跳检测 + 断线重连 |

### 2.4 平台扩展能力

| # | 能力 | 描述 |
|---|------|------|
| 33 | 平台抽象层 | BaseCollector ABC + CollectorRegistry 工厂 |
| 34 | Agent API 统一 | BaseAgent ABC（LLM 单例 + token 追踪 + 验证重试） |
| 35 | SI$ 统一 tag 解析 | `parse_si_tag()` 单次遍历解析所有 tag 模式 |
| 36 | 多 LLM 提供商 | DeepSeek / Claude / OpenAI，角色级模型覆盖 |
| 37 | 多 App Hook | Activity/Fragment/RV/View/Handler/Block/IO/Compose 12 类 Hook |

---

## 三、与 perfetto-sql Skill 的差距

### 3.1 perfetto-sql Skill 概要

Google 的 perfetto-sql Skill 是一个**自然语言转 Perfetto SQL 查询**的工具：
- 用户用自然语言描述数据需求
- Skill 自动翻译为合法的 Perfetto SQL
- 通过 `trace_processor` CLI 执行查询
- 返回 CSV 格式结果

核心特性：
- **严格的 SQL 编写规范**：`CREATE OR REPLACE`、`GLOB` 替代 `LIKE`、`SPAN_JOIN` 分区保护、`dur=-1` 安全处理
- **Perfetto Standard Library 集成**：自动搜索和引用标准库模块（`INCLUDE PERFETTO MODULE`）
- **Schema 驱动的查询生成**：强制查阅文档 schema 后才生成查询
- **验证循环**：最多 3 轮迭代验证（语法、幂等性、列准确性、模块引用等）
- **无状态执行**：每次查询独立，不可跨 turn 共享视图/表

### 3.2 差距对比

| 维度 | SI 当前状态 | perfetto-sql Skill | 差距评估 |
|------|------------|-------------------|----------|
| **SQL 查询灵活度** | 14 个预定义 collect_* 方法，SQL 硬编码在各 Mixin 中 | 自然语言→任意 SQL，覆盖所有 Perfetto 表 | **大差距**：SI 只能查预定义的 SQL，无法自由探索 |
| **Perfetto Standard Library** | 未使用 `INCLUDE PERFETTO MODULE` | 强制搜索标准库模块后再写查询 | **大差距**：SI 未利用 Perfetto 标准库的高级抽象 |
| **查询安全性** | `dur=-1` 未统一处理，直接用 f-string 拼 SQL | 统一 `IIF(dur=-1, trace_end()-ts, dur)` 处理 | **中差距**：SI 部分查询可能产生错误结果 |
| **SPAN_JOIN 使用** | 未使用 SPAN_JOIN | 强制分区保护 + 中间表物化 | **中差距**：SI 缺少跨表时间关联能力 |
| **查询幂等性** | 无此概念 | `CREATE OR REPLACE` + `DROP TABLE IF EXISTS` | **小差距**：SI 只执行 SELECT，不创建对象 |
| **SQL 字符串安全** | f-string 直接拼接（SQL 注入风险低但存在） | 模板化生成 | **小差距**：SI 使用内部数据但应参数化 |
| **实时查询能力** | 仅在分析流水线中批量执行 | 随时自然语言提问 | **大差距**：SI 不支持 ad-hoc 查询 |
| **GLOB vs LIKE** | 使用 Python 端过滤 | 强制使用 GLOB 替代 LIKE | **小差距**：SI 在 Python 端过滤，不涉及此问题 |
| **唯一标识符** | 部分查询使用 pid/tid | 强制使用 utid/upid | **中差距**：SI 可能受 PID 回收影响 |
| **EXTRACT_ARG** | 通过 `args` 表 JOIN 获取 | 推荐使用 `EXTRACT_ARG()` 函数 | **小差距**：功能等效但 EXTRACT_ARG 更简洁 |
| **Schema 文档化** | SQL 散布在各 Mixin 中，无统一文档 | 统一的标准库文档引用流程 | **中差距**：SI 缺少 SQL 查询的知识库 |
| **trace boundaries** | 部分处理（summarize 中有诊断） | 统一 `trace_end()` 处理 | **小差距** |

### 3.3 核心差距总结

1. **查询自由度**：SI 是"预定义模板"模式，perfetto-sql 是"自然语言→SQL"模式。SI 无法响应用户的临时查询需求。
2. **Perfetto 标准库**：SI 未利用 Perfetto Standard Library（如 `sched.runnable`、`linux.perf.counters`、`intervals.overlap`），全部手写 SQL。
3. **SQL 质量保障**：perfetto-sql 有严格的验证清单（语法、幂等性、列准确性、模块引用、SPAN_JOIN 安全等），SI 的 SQL 缺少类似的质量检查。
4. **Ad-hoc 分析能力**：perfetto-sql 支持任何维度的自由探索，SI 只能通过 `metric_qa` 回答 20 个预定义指标。

---

## 四、可借鉴技术点

### 4.1 Perfetto Standard Library 集成（`INCLUDE PERFETTO MODULE`）

**借鉴价值：高**

perfetto-sql Skill 强制在写任何 SQL 前先查阅标准库文档，确保使用最佳实践。SI 当前的所有 collect_* 方法都是手写 SQL，可以利用标准库模块来简化和增强：

- `sched.runnable`：替代手动 sched 表查询，安全处理 trace gaps
- `linux.perf.counters`：标准化的 CPU 计数器查询
- `intervals.overlap`：替代手动时间重叠计算（用于 jank 关联）
- `android.startup.startups`：替代手写的冷启动阶段检测

**实施建议**：在 Collector Mixin 中引入 `INCLUDE PERFETTO MODULE` 语句，逐步替换手写 SQL 为标准库视图。

### 4.2 SQL 查询安全规范

**借鉴价值：高**

perfetto-sql Skill 的以下规范可以直接应用到 SI 的 SQL 查询中：

- **`dur=-1` 统一处理**：所有时间计算使用 `IIF(dur=-1, trace_end() - ts, dur)`
- **utid/upid 替代 tid/pid**：避免操作系统 PID 回收导致的错误 JOIN
- **`EXTRACT_ARG()` 替代 args 表 JOIN**：更简洁的参数提取
- **`GLOB` 替代 `LIKE`**：避免下划线通配符问题和性能问题

**实施建议**：创建 `collector/sql_utils.py`，封装安全的 SQL 构建工具函数。

### 4.3 自然语言→SQL 查询层

**借鉴价值：高**

借鉴 perfetto-sql 的"自然语言→SQL"模式，在 SI 中增加 ad-hoc 查询能力：

- 用户可以用自然语言追问任何 Perfetto 维度的数据
- 不限于预定义的 20 个 metric_qa 指标
- 结合 SI 已有的 trace_processor 基础设施，成本较低

**实施建议**：新增一个 `sql_agent` 节点，接收自然语言查询意图，结合 Perfetto Standard Library 文档生成 SQL，执行后返回结果。

### 4.4 Schema 驱动的查询生成 + 验证循环

**借鉴价值：中**

perfetto-sql 的"先查文档再写查询"流程可以应用于 SI 的 metric_qa 和 ad-hoc 查询：

- 维护一份 SI 常用查询的 Schema 文档（类似 `references/perfetto-stdlib-docs.md`）
- 查询生成前强制查阅 schema，确保列名、类型准确
- 执行后验证结果（行数、列数、数值范围），失败自动重试

**实施建议**：将各 Mixin 的 SQL 查询模式提取为文档化的"查询模板"，配合 LLM 做动态查询生成。

### 4.5 SPAN_JOIN 跨表时间关联

**借鉴价值：中**

perfetto-sql 强调使用 `SPAN_JOIN` 做跨表时间关联。SI 当前的 jank 关联是 Python 端手动计算时间重叠，可以利用 `SPAN_JOIN` 在 SQL 层完成：

- 帧时间线 ↔ View 切片的时间重叠 → 直接 SQL JOIN
- 线程状态 ↔ SI$ 切片的 Running/Blocked 分布 → `SPAN_JOIN(thread_state, slice)`

**注意**：`SPAN_JOIN` 需要中间表物化（`CREATE PERFETTO TABLE`）和分区保护（`PARTITIONED upid`），需要正确使用。

### 4.6 Trace Boundaries 安全处理

**借鉴价值：中**

SI 当前的 `_diagnose_tables()` 已经有基本的 trace 边界诊断，但缺少统一的 `dur=-1` 安全处理。可以在 `PerfettoCollector` 基类中添加：

```python
# 安全的时间范围计算 SQL 模板
SAFE_DUR = "IIF(dur = -1, trace_end() - ts, dur)"
SAFE_END = "ts + IIF(dur = -1, trace_end() - ts, dur)"
```

所有 Mixin 的 SQL 查询统一使用这些模板。

### 4.7 查询无状态执行 + 幂等性

**借鉴价值：低**

perfetto-sql 强调每次查询独立、无状态。SI 的 Collector 当前是一次性 `summarize()` 调用，不存在跨查询状态问题。但如果未来引入 ad-hoc 查询能力，需要注意：
- 不依赖上一次查询创建的视图/表
- 使用 `CREATE OR REPLACE` 确保幂等性

---

## 五、优化路线图

### Phase 1：SQL 质量提升（基础加固）

**目标**：提升现有 SQL 查询的健壮性和正确性

| # | 任务 | 影响 |
|---|------|------|
| 1.1 | 统一 `dur=-1` 安全处理：所有 Mixin 的时间计算使用 `IIF(dur=-1, trace_end()-ts, dur)` | 修复潜在的数据错误 |
| 1.2 | 全面使用 `utid`/`upid` 替代 `tid`/`pid`：审查所有 Mixin SQL | 避免进程 ID 回收导致的错误 JOIN |
| 1.3 | 创建 `collector/sql_utils.py`：封装安全 SQL 构建工具 | 统一 SQL 编写规范 |
| 1.4 | 使用 `EXTRACT_ARG()` 简化 args 查询：替代 `_args` 表 JOIN | 简化代码 |
| 1.5 | 添加 SQL 查询文档化：为每个 collect_* 方法记录 SQL 表、列、逻辑 | 维护性提升 |

### Phase 2：Perfetto Standard Library 集成

**目标**：利用标准库模块替代手写 SQL，提升查询质量和可维护性

| # | 任务 | 影响 |
|---|------|------|
| 2.1 | 引入 `android.startup.startups` 替代手写冷启动检测 | 提升冷启动分析准确性 |
| 2.2 | 引入 `sched.runnable` 替代手动 sched 表查询 | 安全处理 trace gaps |
| 2.3 | 引入 `intervals.overlap` 替代手动 jank 关联计算 | 标准化时间重叠计算 |
| 2.4 | 引入 `linux.perf.counters` 替代手动 CPU 计数器查询 | 利用标准抽象 |
| 2.5 | 创建 Perfetto 标准库文档索引：`references/perfetto-modules.md` | 开发参考 |

### Phase 3：Ad-hoc 查询能力

**目标**：支持用户自然语言→SQL 的自由查询，突破预定义指标限制

| # | 任务 | 影响 |
|---|------|------|
| 3.1 | 新增 `sql_agent` 节点：自然语言→Perfetto SQL 生成 + 执行 | 用户可查询任意维度 |
| 3.2 | 构建 Perfetto Schema 知识库：表/列/模块文档化 | 支持准确的 SQL 生成 |
| 3.3 | 实现查询验证循环：语法检查→执行→结果验证→重试 | 查询质量保障 |
| 3.4 | 扩展 metric_qa：支持任意自然语言追问（不限于 20 个预定义指标） | 更灵活的指标查询 |
| 3.5 | 集成到 Orchestrator 路由：新增 `sql_query` 路由决策 | 自然语言入口 |

### Phase 4：高级分析能力

**目标**：利用 `SPAN_JOIN` 和标准库增强跨维度关联分析

| # | 任务 | 影响 |
|---|------|------|
| 4.1 | SPAN_JOIN 帧时间线↔View 切片关联：SQL 层替代 Python 端计算 | 更准确的时间关联 |
| 4.2 | SPAN_JOIN 线程状态↔SI$ 切片关联：SQL 层计算 Running/Blocked 分布 | 统一分析逻辑 |
| 4.3 | Power/Battery 分析：利用 `android.power_rails` 等标准库模块 | 新分析维度 |
| 4.4 | Network 流量分析：利用标准库网络模块 | 新分析维度 |
| 4.5 | ANR 分析增强：结合 `atrace` + `ftrace` 的 ANR 信号 | 更完整的卡顿分析 |

### Phase 5：工程化和生态

**目标**：提升工具的可用性、可扩展性和生态集成

| # | 任务 | 影响 |
|---|------|------|
| 5.1 | SQL 查询测试框架：为每个 collect_* 方法建立 SQL 正确性测试 | 回归保护 |
| 5.2 | Perfetto UI 插件增强：支持 ad-hoc SQL 查询面板 | UI 层自由查询 |
| 5.3 | 查询结果可视化：帧时间线图、CPU 火焰图、内存趋势图 | 更直观的分析结果 |
| 5.4 | 多 trace 对比分析：支持同时加载多个 trace 做对比 | 版本回归检测 |
| 5.5 | HarmonyOS / iOS Collector 实现 | 多平台支持 |

### 优先级排序

```
Phase 1 (SQL 质量)    → 立即执行，基础加固
Phase 2 (标准库集成)  → 短期执行，提升查询质量
Phase 3 (Ad-hoc 查询) → 中期执行，核心竞争力提升
Phase 4 (高级分析)    → 中长期执行，差异化能力
Phase 5 (工程化)      → 持续推进，生态建设
```

---

## 附录：SI 与 perfetto-sql Skill 的定位差异

| 维度 | SmartInspector | perfetto-sql Skill |
|------|---------------|-------------------|
| **定位** | 端到端性能分析平台 | Perfetto SQL 查询生成器 |
| **范围** | 采集→分析→归因→报告 | 自然语言→SQL→执行 |
| **LLM 用途** | 意图路由+分析+归因+报告 | SQL 查询生成+验证 |
| **输出** | Markdown/JSON 报告 + 源码归因 | CSV 查询结果 |
| **目标用户** | 移动端开发者（不需要懂 SQL） | 需要 SQL 查询能力的开发者 |
| **独特价值** | SI$ 源码归因 + 自动优化建议 | 灵活的 SQL 查询能力 |

两者并非竞争关系，而是互补：perfetto-sql 的 SQL 生成和验证能力可以增强 SI 的查询层，而 SI 的端到端流水线和源码归因是 perfetto-sql 不具备的。
