# Perfetto SQL Skill 深度分析报告

> 日期：2026-05-12
> 目标：分析 `/tmp/android-skills/profilers/perfetto-sql/` Skill，提炼可补充 SmartInspector (SI) 采集分析能力的内容

---

## 一、SKILL.md 查询规范与最佳实践提炼

### 1.1 幂等性规则
- Perfetto 对象使用 `CREATE OR REPLACE PERFETTO TABLE/VIEW/FUNCTION/MACRO`
- SQLite Virtual Table（如 `SPAN_JOIN`）不支持 `CREATE OR REPLACE`，必须先 `DROP TABLE IF EXISTS`
- SQLite 索引使用 `DROP INDEX IF EXISTS`

### 1.2 SPAN_JOIN 安全规则
- **同一输入表内区间不能重叠**，否则 crash。必须用 `PARTITIONED {column}` 隔离
- 中间表必须 `CREATE PERFETTO TABLE` 物化，不能用 `CREATE VIEW`

### 1.3 dur=-1 处理
- 未在 trace 结束前完成的 slice，`dur = -1`
- 计算边界/求和时：`IIF(dur = -1, trace_end() - ts, dur)`

### 1.4 状态转换安全
- 避免手动 `ts + dur = next.ts` 时间算术
- 使用 stdlib 模块（`sched.runnable`、`intervals.overlap`）安全处理

### 1.5 标识符规则
- 使用 `utid`/`upid` 而非 `tid`/`pid`（OS 回收 TID/PID，utid/upid 全 trace 唯一）

### 1.6 参数提取
- 使用 `EXTRACT_ARG(arg_set_id, 'key')` 而非字符串解析

### 1.7 字符串匹配
- **必须使用 `GLOB` 替代 `LIKE`**（LIKE 有性能问题且 `_` 被视为通配符）
- 精确匹配用 `=`，子串匹配用 `GLOB '*pattern*'`
- 大小写不敏感：`LOWER(name) GLOB '*pattern*'`

### 1.8 时间重叠计算
- 优先使用 `SPAN_JOIN` 或 stdlib 函数（`intervals.overlap`）
- 手动公式：`MIN(end1, end2) - MAX(start1, start2)`，需先处理 dur=-1

### 1.9 列名前缀
- **所有列名必须带表/视图别名**：`alias.column_name`

### 1.10 对 SI 的影响
| SI 现状 | 建议改进 |
|---------|---------|
| SQL 查询使用 `LIKE` | 改为 `GLOB`（frame.py, io.py, block.py 等） |
| 手动计算 thread_state overlap | 考虑使用 `SPAN_JOIN` + `PARTITIONED` |
| 直接查询原始表 | 大量场景可改用 stdlib 预计算视图 |
| 部分查询未处理 dur=-1 | 添加 `IIF(dur = -1, trace_end() - ts, dur)` |

---

## 二、Perfetto SQL Standard Library 完整模块目录

### 2.1 android 包模块清单（60+ 个子模块）

| 模块 | INCLUDE 语句 | 提供的表/视图/函数 | 解决的性能问题 |
|------|-------------|-------------------|---------------|
| android.anrs | `android.anrs` | `android_anrs` | ANR 检测与分析 |
| android.app_process_starts | `android.app_process_starts` | `android_app_process_starts` | 冷启动原因分类（broadcast/service/activity/provider） |
| android.battery | `android.battery` | `android_battery_charge` | 电池状态追踪 |
| android.battery.charging_states | `android.battery.charging_states` | `android_charging_states` | 充电状态追踪 |
| android.battery.doze | `android.battery.doze` | `android_light_idle_state`, `android_deep_idle_state` | Doze 模式分析 |
| android.battery_stats | `android.battery_stats` | `android_battery_stats_state`, `android_battery_stats_event_slices` | 电池统计状态 |
| android.binder | `android.binder` | `android_binder_txns`, `android_binder_metrics_by_process`, `android_sync_binder_thread_state_by_txn` 等 | Binder 事务分析、延迟分解 |
| android.binder_breakdown | `android.binder_breakdown` | `android_binder_server_breakdown`, `android_binder_client_breakdown`, `android_binder_client_server_breakdown` | Binder 延迟原因分解 |
| android.bitmaps | `android.bitmaps` | `android_bitmap_memory`, `android_bitmap_count`, `android_bitmap_counters_per_process` | Bitmap 内存追踪 |
| android.cpu.cluster_type | `android.cpu.cluster_type` | `android_cpu_cluster_mapping` | CPU 大小核映射 |
| android.cpu.cpu_per_uid | `android.cpu.cpu_per_uid` | `android_cpu_per_uid_track`, `android_cpu_per_uid_counter` | 按 UID 的 CPU 使用 |
| android.cujs.base | `android.cujs.base` | `android_jank_cuj` | CUJ（Critical User Journey）jank 追踪 |
| android.cujs.sysui_cujs | `android.cujs.sysui_cujs` | `android_sysui_jank_cujs`, `android_sysui_latency_cujs`, `android_jank_latency_cujs` | SystemUI CUJ 分析 |
| android.cujs.threads | `android.cujs.threads` | `android_jank_cuj_render_thread`, `android_jank_cuj_app_thread` | CUJ 线程关联 |
| android.desktop_mode | `android.desktop_mode` | `android_desktop_mode_windows` | 桌面模式窗口 |
| android.device | `android.device` | `android_device_name` | 设备名称提取 |
| android.dumpsys.show_map | `android.dumpsys.show_map` | `android_dumpsys_show_map` | /proc/pid/smaps 内存映射 |
| android.dvfs | `android.dvfs` | `android_dvfs_counters`, `android_dvfs_counter_stats`, `android_dvfs_counter_residency` | DVFS 频率调节分析 |
| android.entity_state_residency | `android.entity_state_residency` | `android_entity_state_residency` | 硬件实体状态驻留 |
| android.frames.jank_type | `android.frames.jank_type` | `android_is_sf_jank_type()`, `android_is_app_jank_type()`, `android_is_missed_frame_type()` | Jank 类型判断函数 |
| android.frames.per_frame_metrics | `android.frames.per_frame_metrics` | `android_frames_overrun`, `android_frames_ui_time`, `android_app_vsync_delay_per_frame`, `android_cpu_time_per_frame`, `android_frame_stats` | 逐帧指标（overrun/ui_time/vsync_delay/cpu_time） |
| android.frames.timeline | `android.frames.timeline` | `android_frames`, `android_frames_layers`, `android_frames_choreographer_do_frame`, `android_frames_draw_frame`, `android_first_frame_after()` | 帧时间线关联 |
| android.freezer | `android.freezer` | `android_freezer_events` | 进程冻结事件 |
| android.garbage_collection | `android.garbage_collection` | `android_garbage_collection_events` | GC 事件分析（类型/回收量/线程状态分解） |
| android.gpu.frequency | `android.gpu.frequency` | `android_gpu_frequency` | GPU 频率追踪 |
| android.gpu.memory | `android.gpu.memory` | `android_gpu_memory_per_process` | GPU 内存 per process |
| android.input | `android.input` | `android_input_events`, `android_key_events`, `android_motion_events` | 输入事件延迟分解（dispatch→receive→ACK） |
| android.job_scheduler | `android.job_scheduler` | `android_job_scheduler_events` | Job 调度事件 |
| android.kernel_wakelocks | `android.kernel_wakelocks` | `android_kernel_wakelocks` | 内核 wakelock 分析 |
| android.memory.dmabuf | `android.memory.dmabuf` | `android_dmabuf_allocs`, `android_memory_cumulative_dmabuf` | DMA buffer 追踪 |
| android.memory.heap_graph.class_summary_tree | `android.memory.heap_graph.class_summary_tree` | `android_heap_graph_class_summary_tree` | Java 堆火焰图式聚合 |
| android.memory.heap_graph.dominator_tree | `android.memory.heap_graph.dominator_tree` | `heap_graph_dominator_tree` | Java 堆 dominator 树 |
| android.memory.heap_graph.heap_graph_class_aggregation | `android.memory.heap_graph.heap_graph_class_aggregation` | `android_heap_graph_class_aggregation` | Java 堆按类聚合 |
| android.memory.heap_graph.heap_graph_stats | `android.memory.heap_graph.heap_graph_stats` | `android_heap_graph_stats` | Java 堆统计摘要 |
| android.memory.heap_profile.summary_tree | `android.memory.heap_profile.summary_tree` | `android_heap_profile_summary_tree` | Native 堆 profile 摘要树 |
| android.memory.lmk | `android.memory.lmk` | `android_lmk_events` | LMK kill 事件 |
| android.memory.process | `android.memory.process` | `memory_oom_score_with_rss_and_swap_per_process` | OOM 分数 + RSS/Swap 关联 |
| android.monitor_contention | `android.monitor_contention` | `android_monitor_contention`, `android_monitor_contention_chain`, `android_monitor_contention_chain_thread_state` | Java 锁竞争分析（阻塞方法/源码位置/线程状态） |
| android.network_packets | `android.network_packets` | `android_network_packets`, `android_network_uptime_spans` | 网络包分析 |
| android.oom_adjuster | `android.oom_adjuster` | `android_oom_adj_intervals`, `android_oom_adj_score_to_bucket_name()` | OOM adj 状态追踪 |
| android.power_rails | `android.power_rails` | `android_power_rails_counters`, `android_power_rails_metadata` | 功耗 rail 分析（Pixel only） |
| android.process_metadata | `android.process_metadata` | `android_process_metadata` | 进程包名/版本/debuggable 元数据 |
| android.screen_state | `android.screen_state` | `android_screen_state` | 屏幕状态（on/off/doze） |
| android.slices | `android.slices` | `android_standardize_slice_name()` | slice 名标准化（聚合用） |
| android.startup.startup_breakdowns | `android.startup.startup_breakdowns` | `android_startup_opinionated_breakdown` | 启动瓶颈分解 |
| android.startup.startups | `android.startup.startups` | `android_startups`, `android_startup_processes`, `android_startup_threads`, `android_thread_slices_for_all_startups`, `android_class_loading_for_startup` | 启动事件检测 |
| android.startup.time_to_display | `android.startup.time_to_display` | `android_startup_time_to_display` | TTID/TTFD 指标 |
| android.surfaceflinger | `android.surfaceflinger` | `android_app_to_sf_frame_timeline_match` | App-SF 帧时间线匹配 |
| android.suspend | `android.suspend` | `android_suspend_state` | 系统挂起/唤醒状态 |
| android.thread | `android.thread` | `android_standardize_thread_name()` | 线程名标准化 |
| android.wakeups | `android.wakeups` | `android_wakeups` | 唤醒事件分析 |

### 2.2 非 android 包关键模块

| 模块 | INCLUDE 语句 | 提供的表/函数 | 解决的问题 |
|------|-------------|-------------|-----------|
| intervals.overlap | `intervals.overlap` | `intervals_overlap_count()`, `interval_merge_overlapping()` | 区间重叠计算 |
| counters.intervals | `counters.intervals` | `counter_leading_intervals()` | Counter 时序区间化 |
| linux.block_io | `linux.block_io` | `linux_active_block_io_operations_by_device` | 块设备 IO 追踪 |
| linux.cpu.frequency | `linux.cpu.frequency` | `cpu_frequency_counters` | CPU 频率 counter |
| linux.cpu.idle | `linux.cpu.idle` | `cpu_idle_counters` | CPU idle 状态 |
| linux.cpu.idle_stats | `linux.cpu.idle_stats` | `cpu_idle_stats` | CPU idle 统计聚合 |
| linux.cpu.utilization.process | `linux.cpu.utilization.process` | `cpu_cycles_per_process`, `cpu_process_utilization_per_second()` | 进程级 CPU 利用率（含频率/周期） |
| linux.cpu.utilization.slice | `linux.cpu.utilization.slice` | `cpu_cycles_per_thread_slice` | Slice 级 CPU 周期 |
| linux.cpu.utilization.thread | `linux.cpu.utilization.thread` | `cpu_cycles_per_thread`, `cpu_thread_utilization_per_second()` | 线程级 CPU 利用率 |
| linux.irqs | `linux.irqs` | `linux_hard_irqs`, `linux_soft_irqs`, `linux_irqs` | 硬/软中断分析 |
| linux.memory.process | `linux.memory.process` | `memory_rss_and_swap_per_process` | 进程 RSS/Swap 时间线 |
| linux.memory.high_watermark | `linux.memory.high_watermark` | `memory_rss_high_watermark_per_process` | RSS 高水位 |
| linux.perf.samples | `linux.perf.samples` | `linux_perf_samples_summary_tree` | CPU 采样火焰图 |
| sched.latency | `sched.latency` | `sched_latency_for_running_interval` | 调度延迟（runnable→running） |
| sched.runnable | `sched.runnable` | `sched_previous_runnable_on_thread` | Runnable 状态追踪 |
| sched.time_in_state | `sched.time_in_state` | `sched_time_in_state_for_thread`, `sched_percentage_of_time_in_state` | 线程状态时间分布 |
| sched.thread_level_parallelism | `sched.thread_level_parallelism` | `sched_runnable_thread_count`, `sched_active_cpu_count` | 线程级并行度 |
| sched.with_context | `sched.with_context` | `sched_with_thread_process` | sched + 线程/进程上下文 |
| slices.cpu_time | `slices.cpu_time` | `thread_slice_cpu_time`, `thread_slice_cpu_cycles` | Slice 级 CPU 时间和周期 |
| slices.self_dur | `slices.self_dur` | `slice_self_dur` | Slice 自身耗时（排除子 slice） |
| slices.time_in_state | `slices.time_in_state` | `thread_slice_time_in_state` | Slice 内线程状态分布 |
| slices.with_context | `slices.with_context` | `thread_slice`, `process_slice` | Slice + 线程/进程上下文 |

---

## 三、SI 当前覆盖范围

### 3.1 SI 已使用的 Perfetto 原始表

| 表名 | 使用模块 | 用途 |
|------|---------|------|
| `slice` | frame, io, block, thread, startup | 所有 SI$ 自定义 slice 查询 |
| `thread` | sched, cpu, frame, thread, sys, startup | 线程名、tid、utid 映射 |
| `process` | perfetto (resolve), cpu | 进程名、pid、upid 映射 |
| `sched` | sched, cpu | 调度切换、CPU 使用率 |
| `sched_blocked_reason` | sched | 阻塞原因（IO wait flag） |
| `perf_sample` | cpu | CPU 火焰图采样 |
| `stack_profile_callsite` | cpu | 调用栈层级 |
| `stack_profile_frame` | cpu | 函数名映射 |
| `actual_frame_timeline_slice` | frame | 实际帧时间 |
| `expected_frame_timeline_slice` | frame | 期望帧时间 |
| `heap_graph_object` | memory | Java 堆对象 |
| `heap_graph_class` | memory | Java 类定义 |
| `heap_graph_reference` | memory | 对象引用链 |
| `counter` | sys | 系统计数器 |
| `cpu_counter_track` | sys | CPU 计数器 track |
| `trace_bounds` | cpu | trace 时间范围 |
| `thread_track` | frame, thread, startup | track→thread 映射 |
| `thread_state` / `__intrinsic_thread_state` | thread | 线程状态 |
| `android_logs` | block | SIBlock logcat |
| `metadata` | perfetto | 设备信息 |
| `package_list` | perfetto | 包名→UID 映射 |

### 3.2 SI 未使用任何 stdlib 模块

SI 当前所有 SQL 查询直接操作原始表，**未使用任何 `INCLUDE PERFETTO MODULE` 语句**。这意味着：
- 大量重复造轮子的 SQL（如帧分析、线程状态分析）
- 缺少 stdlib 中经过领域专家验证的正确性保证
- 无法利用 stdlib 中预计算的高阶抽象（如 binder 分解、锁竞争链分析）

---

## 四、差距分析与可落地方案

### 优先级说明
- **P0（必须做）**：对 SI 核心能力有重大提升，且实现成本可控
- **P1（应该做）**：显著增强特定场景分析能力
- **P2（可以做）**：锦上添花，适合后续迭代

---

### P0-1: android.monitor_contention — 锁竞争分析

**优先级理由**：锁竞争是 Android 性能问题的 Top 原因之一，SI 当前完全无覆盖。

**解决的问题**：检测主线程被其他线程持锁阻塞的场景，定位阻塞方法名和源码位置。

**SQL 查询模板**：
```sql
INCLUDE PERFETTO MODULE android.monitor_contention;

-- 查询目标进程的主线程锁竞争
SELECT
  mc.id,
  mc.ts,
  mc.dur / 1000000.0 AS dur_ms,
  mc.short_blocked_method,
  mc.short_blocking_method,
  mc.blocked_src,
  mc.blocking_src,
  mc.blocked_thread_name,
  mc.blocking_thread_name,
  mc.is_blocked_thread_main,
  mc.is_blocking_thread_main,
  mc.waiter_count
FROM android_monitor_contention mc
WHERE mc.upid = (SELECT upid FROM process WHERE name = '{process_name}')
  AND mc.dur > 1000000  -- > 1ms
ORDER BY mc.dur DESC
LIMIT 20;
```

**锁竞争链 + 线程状态分解**：
```sql
INCLUDE PERFETTO MODULE android.monitor_contention;

-- 查询锁竞争的阻塞线程状态分解
SELECT
  mc.id,
  mc.short_blocked_method,
  mc.dur / 1000000.0 AS contention_dur_ms,
  mcts.thread_state,
  mcts.thread_state_dur / 1000000.0 AS state_dur_ms,
  mcts.thread_state_count
FROM android_monitor_contention mc
JOIN android_monitor_contention_chain_thread_state_by_txn mcts
  ON mcts.id = mc.id
WHERE mc.upid = (SELECT upid FROM process WHERE name = '{process_name}')
  AND mc.dur > 5000000  -- > 5ms
ORDER BY mc.dur DESC, mcts.thread_state_dur DESC;
```

**Python collector 方法框架**：
```python
# collector/lock.py — LockMixin
class LockMixin:
    def collect_lock_contention(self) -> list[dict]:
        """收集 Java monitor contention 事件"""
        query = """
        INCLUDE PERFETTO MODULE android.monitor_contention;
        SELECT ...  -- 如上 SQL
        """
        rows = self._query_sql(query)
        return [
            {
                "blocked_method": r["short_blocked_method"],
                "blocking_method": r["short_blocking_method"],
                "blocked_src": r["blocked_src"],
                "blocking_src": r["blocking_src"],
                "dur_ms": r["dur_ms"],
                "blocking_thread": r["blocking_thread_name"],
                "is_main_blocked": bool(r["is_blocked_thread_main"]),
            }
            for r in rows
        ]
```

---

### P0-2: android.binder — Binder 事务分析

**优先级理由**：Binder 是 Android IPC 核心，跨进程调用延迟是性能瓶颈的主要来源。

**解决的问题**：识别耗时 Binder 事务，分解客户端/服务端延迟，关联 AIDL 方法名。

**SQL 查询模板**：
```sql
INCLUDE PERFETTO MODULE android.binder;

-- 目标进程的 Top Binder 事务
SELECT
  bt.client_ts,
  bt.client_dur / 1000000.0 AS client_dur_ms,
  bt.server_dur / 1000000.0 AS server_dur_ms,
  bt.aidl_name,
  bt.method_name,
  bt.client_process,
  bt.client_thread,
  bt.server_process,
  bt.server_thread,
  bt.is_main_thread,
  bt.is_sync
FROM android_binder_txns bt
WHERE bt.client_upid = (SELECT upid FROM process WHERE name = '{process_name}')
  AND bt.is_sync = TRUE
ORDER BY bt.client_dur DESC
LIMIT 30;
```

**Binder 延迟分解（client/server breakdown）**：
```sql
INCLUDE PERFETTO MODULE android.binder_breakdown;

-- 客户端+服务端延迟分解
SELECT
  bb.binder_txn_id,
  bb.ts,
  bb.dur / 1000000.0 AS segment_dur_ms,
  bb.server_reason,
  bb.client_reason,
  bb.reason,
  bb.reason_type
FROM android_binder_client_server_breakdown bb
WHERE bb.dur > 1000000  -- > 1ms segments only
ORDER BY bb.dur DESC
LIMIT 50;
```

**Python collector 方法框架**：
```python
# collector/binder.py — BinderMixin
class BinderMixin:
    def collect_binder_txns(self) -> list[dict]:
        """收集目标进程的 Binder 事务"""
        # 使用 android_binder_txns 表
        ...

    def collect_binder_breakdown(self, txn_id: int) -> list[dict]:
        """分解指定 Binder 事务的延迟原因"""
        # 使用 android_binder_client_server_breakdown 表
        ...
```

---

### P0-3: android.startup.* — 启动分析增强

**优先级理由**：SI 已有 `startup.py` 但使用原始 slice 查询，stdlib 提供了远更完整的启动分析能力。

**解决的问题**：
- 标准化的启动检测（`android_startups`）
- TTID/TTFD 指标（`android_startup_time_to_display`）
- 启动瓶颈自动分解（`android_startup_opinionated_breakdown`）
- 冷启动原因分类（`android_app_process_starts`）

**SQL 查询模板**：
```sql
INCLUDE PERFETTO MODULE android.startup.startups;
INCLUDE PERFETTO MODULE android.startup.time_to_display;

-- 启动检测 + TTID/TTFD
SELECT
  s.startup_id,
  s.ts,
  s.dur / 1000000.0 AS startup_dur_ms,
  s.package,
  s.startup_type,
  ttd.time_to_initial_display / 1000000.0 AS ttid_ms,
  ttd.time_to_full_display / 1000000.0 AS ttfid_ms
FROM android_startups s
LEFT JOIN android_startup_time_to_display ttd
  ON ttd.startup_id = s.startup_id
WHERE s.package = '{package_name}'
ORDER BY s.ts;
```

**启动瓶颈分解**：
```sql
INCLUDE PERFETTO MODULE android.startup.startup_breakdowns;

-- 自动分解启动瓶颈（slice + thread_state 融合）
SELECT
  sb.startup_id,
  sb.ts,
  sb.dur / 1000000.0 AS segment_dur_ms,
  sb.reason
FROM android_startup_opinionated_breakdown sb
WHERE sb.startup_id = {startup_id}
ORDER BY sb.dur DESC
LIMIT 30;
```

**冷启动原因**：
```sql
INCLUDE PERFETTO MODULE android.app_process_starts;

SELECT
  aps.process_name,
  aps.reason,
  aps.intent,
  aps.proc_start_ts,
  aps.total_dur / 1000000.0 AS total_dur_ms,
  aps.bind_app_dur / 1000000.0 AS bind_app_ms,
  aps.intent_dur / 1000000.0 AS intent_ms
FROM android_app_process_starts aps
WHERE aps.process_name = '{process_name}';
```

**对 SI 的影响**：重构 `startup.py`，用 stdlib 模块替代手动 slice 查询。将 `StartupAnalyzer` 升级为使用 `android_startups` + `android_startup_opinionated_breakdown`。

---

### P0-4: android.garbage_collection — GC 事件分析

**优先级理由**：GC pause 是帧卡顿和启动慢的直接原因，SI 当前无任何 GC 分析能力。

**解决的问题**：检测 GC 事件、GC 耗时、GC 类型、GC 期间线程状态分解。

**SQL 查询模板**：
```sql
INCLUDE PERFETTO MODULE android.garbage_collection;

SELECT
  gc.gc_ts,
  gc.gc_dur / 1000000.0 AS gc_dur_ms,
  gc.gc_running_dur / 1000000.0 AS running_ms,
  gc.gc_runnable_dur / 1000000.0 AS runnable_ms,
  gc.gc_unint_io_dur / 1000000.0 AS io_wait_ms,
  gc.gc_unint_non_io_dur / 1000000.0 AS non_io_wait_ms,
  gc.gc_type,
  gc.reclaimed_mb,
  gc.thread_name,
  gc.process_name
FROM android_garbage_collection_events gc
WHERE gc.upid = (SELECT upid FROM process WHERE name = '{process_name}')
ORDER BY gc.gc_dur DESC
LIMIT 20;
```

**Python collector 方法框架**：
```python
# collector/gc.py — GcMixin
class GcMixin:
    def collect_gc_events(self) -> list[dict]:
        """收集 GC 事件"""
        ...
```

---

### P0-5: android.anrs — ANR 检测

**优先级理由**：ANR 是最严重的用户体验问题，SI 应该能检测并报告 trace 中发生的 ANR。

**SQL 查询模板**：
```sql
INCLUDE PERFETTO MODULE android.anrs;

SELECT
  a.ts,
  a.process_name,
  a.subject,
  a.anr_type,
  a.anr_dur_ms,
  a.default_anr_dur_ms,
  a.timer_delay,
  a.component,
  a.intent
FROM android_anrs a
WHERE a.process_name = '{process_name}'
  OR a.pid = {pid};
```

---

### P0-6: slices.cpu_time / slices.time_in_state — Slice 级 CPU 时间

**优先级理由**：SI 当前有 `thread_state` 分析，但无法将 CPU 时间精确归属到每个 SI$ slice。stdlib 提供了精确的 slice 级 CPU 时间和线程状态分解。

**SQL 查询模板**：
```sql
INCLUDE PERFETTO MODULE slices.cpu_time;
INCLUDE PERFETTO MODULE slices.time_in_state;

-- SI$ slice 的 CPU 时间
SELECT
  tsct.name AS slice_name,
  tsct.cpu_time / 1000000.0 AS cpu_time_ms,
  tsct.thread_name,
  tsct.process_name
FROM thread_slice_cpu_time tsct
WHERE tsct.name GLOB 'SI$*'
  AND tsct.upid = (SELECT upid FROM process WHERE name = '{process_name}')
ORDER BY tsct.cpu_time DESC
LIMIT 20;

-- SI$ slice 的线程状态分布
SELECT
  tsts.name AS slice_name,
  tsts.state,
  tsts.io_wait,
  tsts.blocked_function,
  tsts.dur / 1000000.0 AS state_dur_ms,
  tsts.thread_name
FROM thread_slice_time_in_state tsts
WHERE tsts.name GLOB 'SI$*'
  AND tsts.upid = (SELECT upid FROM process WHERE name = '{process_name}')
ORDER BY tsts.dur DESC
LIMIT 50;
```

**对 SI 的影响**：增强 `thread.py` 中的 `collect_thread_state()`，使用 `thread_slice_time_in_state` 为每个 SI$ slice 提供精确的线程状态分解，替代当前的手动 sched overlap 计算。

---

### P1-1: android.frames.per_frame_metrics — 逐帧指标

**优先级理由**：SI 当前有 `collect_frame_timeline()`，但只有 wall duration。stdlib 提供 per-frame 的 CPU time、UI time、vsync delay、overrun。

**SQL 查询模板**：
```sql
INCLUDE PERFETTO MODULE android.frames.per_frame_metrics;

SELECT
  fs.frame_id,
  fs.overrun / 1000000.0 AS overrun_ms,
  fs.cpu_time / 1000000.0 AS cpu_time_ms,
  fs.ui_time / 1000000.0 AS ui_time_ms,
  fs.was_jank,
  fs.was_slow_frame,
  fs.was_big_jank,
  fs.was_huge_jank
FROM android_frame_stats fs
ORDER BY fs.overrun DESC
LIMIT 30;
```

**对 SI 的影响**：增强 `frame.py` 中的 `collect_frame_timeline()`，额外查询 `android_frame_stats` 获取 per-frame CPU time 和 jank 分级。

---

### P1-2: android.input — 输入延迟分解

**优先级理由**：SI 有 `collect_input_events()` 但只收集 SI$touch# slice。stdlib 提供完整的输入事件延迟分解（dispatch→receive→ACK→frame present）。

**SQL 查询模板**：
```sql
INCLUDE PERFETTO MODULE android.input;

SELECT
  ie.dispatch_latency_dur / 1000000.0 AS dispatch_ms,
  ie.handling_latency_dur / 1000000.0 AS handling_ms,
  ie.ack_latency_dur / 1000000.0 AS ack_ms,
  ie.total_latency_dur / 1000000.0 AS total_ms,
  ie.end_to_end_latency_dur / 1000000.0 AS e2e_ms,
  ie.event_type,
  ie.event_action,
  ie.thread_name,
  ie.process_name,
  ie.frame_id
FROM android_input_events ie
WHERE ie.process_name = '{process_name}'
ORDER BY ie.total_latency_dur DESC
LIMIT 20;
```

---

### P1-3: sched.latency — 调度延迟分析

**优先级理由**：补充 SI 的 sched 分析，量化 runnable→running 的调度延迟。

**SQL 查询模板**：
```sql
INCLUDE PERFETTO MODULE sched.latency;

SELECT
  sl.utid,
  t.name AS thread_name,
  sl.latency_dur / 1000000.0 AS latency_ms,
  COUNT(*) AS wakeup_count,
  AVG(sl.latency_dur) / 1000000.0 AS avg_latency_ms,
  MAX(sl.latency_dur) / 1000000.0 AS max_latency_ms
FROM sched_latency_for_running_interval sl
JOIN thread t ON t.utid = sl.utid
WHERE t.upid = (SELECT upid FROM process WHERE name = '{process_name}')
GROUP BY sl.utid, t.name
ORDER BY avg_latency_ms DESC
LIMIT 10;
```

---

### P1-4: android.memory.process — OOM + RSS/Swap 关联

**优先级理由**：SI 有 `collect_process_memory()` 但无 OOM 分数关联。这个 stdlib 表将 OOM adj 变化与内存变化关联在一起。

**SQL 查询模板**：
```sql
INCLUDE PERFETTO MODULE android.memory.process;

SELECT
  m.ts,
  m.dur / 1000000.0 AS dur_ms,
  m.score AS oom_score,
  m.bucket AS oom_bucket,
  m.anon_rss / 1024 / 1024 AS anon_rss_mb,
  m.swap / 1024 / 1024 AS swap_mb,
  m.anon_rss_and_swap / 1024 / 1024 AS total_mb,
  m.oom_adj_reason,
  m.oom_adj_trigger,
  m.process_name
FROM memory_oom_score_with_rss_and_swap_per_process m
WHERE m.process_name = '{process_name}'
ORDER BY m.ts;
```

---

### P1-5: linux.cpu.utilization.process/thread — 精确 CPU 利用率

**优先级理由**：SI 的 `collect_cpu_usage()` 使用手动 sched 查询计算 CPU%。stdlib 提供含频率加权的 CPU 周期计算，更精确。

**SQL 查询模板**：
```sql
INCLUDE PERFETTO MODULE linux.cpu.utilization.process;
INCLUDE PERFETTO MODULE linux.cpu.utilization.thread;

-- 进程级 CPU 周期
SELECT
  cp.upid,
  p.name AS process_name,
  cp.millicycles,
  cp.megacycles,
  cp.runtime / 1000000.0 AS runtime_ms,
  cp.min_freq,
  cp.max_freq,
  cp.avg_freq
FROM cpu_cycles_per_process cp
JOIN process p ON p.upid = cp.upid
WHERE p.name = '{process_name}';

-- 线程级 CPU 周期
SELECT
  ct.utid,
  t.name AS thread_name,
  ct.millicycles,
  ct.megacycles,
  ct.runtime / 1000000.0 AS runtime_ms,
  ct.avg_freq
FROM cpu_cycles_per_thread ct
JOIN thread t ON t.utid = ct.utid
WHERE t.upid = (SELECT upid FROM process WHERE name = '{process_name}')
ORDER BY ct.megacycles DESC
LIMIT 15;
```

---

### P1-6: android.memory.heap_graph.* — 增强堆分析

**优先级理由**：SI 有基础 heap_graph 查询，但 stdlib 提供 dominator tree 和 class aggregation 等高级分析。

**SQL 查询模板**：
```sql
INCLUDE PERFETTO MODULE android.memory.heap_graph.heap_graph_stats;
INCLUDE PERFETTO MODULE android.memory.heap_graph.heap_graph_class_aggregation;

-- 堆统计摘要
SELECT
  hs.upid,
  hs.graph_sample_ts,
  hs.total_heap_size / 1024 / 1024 AS total_heap_mb,
  hs.reachable_heap_size / 1024 / 1024 AS reachable_heap_mb,
  hs.total_obj_count,
  hs.reachable_obj_count,
  hs.oom_score_adj,
  hs.anon_rss_and_swap_size / 1024 / 1024 AS rss_swap_mb
FROM android_heap_graph_stats hs
WHERE hs.upid = (SELECT upid FROM process WHERE name = '{process_name}');

-- 按类聚合（Top 内存占用类）
SELECT
  ca.type_name,
  ca.obj_count,
  ca.size_bytes / 1024 / 1024 AS size_mb,
  ca.dominated_obj_count,
  ca.dominated_size_bytes / 1024 / 1024 AS dominated_mb,
  ca.is_libcore_or_array
FROM android_heap_graph_class_aggregation ca
WHERE ca.upid = (SELECT upid FROM process WHERE name = '{process_name}')
  AND ca.is_libcore_or_array = FALSE
ORDER BY ca.dominated_size_bytes DESC
LIMIT 20;
```

---

### P1-7: android.surfaceflinger — App-SF 帧时间线匹配

**优先级理由**：帧卡可能来自 app 也可能来自 SF，需要关联两端。

**SQL 查询模板**：
```sql
INCLUDE PERFETTO MODULE android.surfaceflinger;

SELECT
  m.app_upid,
  m.app_vsync,
  m.sf_upid,
  m.sf_vsync
FROM android_app_to_sf_frame_timeline_match m
WHERE m.app_upid = (SELECT upid FROM process WHERE name = '{process_name}');
```

---

### P2-1: android.bitmaps — Bitmap 内存追踪

**SQL 查询模板**：
```sql
INCLUDE PERFETTO MODULE android.bitmaps;

SELECT
  bc.upid,
  bc.process_name,
  bc.ts,
  bc.bitmap_memory / 1024 / 1024 AS bitmap_mb,
  bc.bitmap_count
FROM android_bitmap_counters_per_process bc
WHERE bc.process_name = '{process_name}'
ORDER BY bc.ts;
```

---

### P2-2: android.gpu.memory — GPU 内存

**SQL 查询模板**：
```sql
INCLUDE PERFETTO MODULE android.gpu.memory;

SELECT
  gm.ts,
  gm.dur / 1000000.0 AS dur_ms,
  gm.upid,
  gm.gpu_memory / 1024 / 1024 AS gpu_mem_mb
FROM android_gpu_memory_per_process gm
WHERE gm.upid = (SELECT upid FROM process WHERE name = '{process_name}')
ORDER BY gm.ts;
```

---

### P2-3: linux.irqs — 中断分析

**SQL 查询模板**：
```sql
INCLUDE PERFETTO MODULE linux.irqs;

SELECT
  irq.ts,
  irq.dur / 1000000.0 AS dur_ms,
  irq.name,
  irq.is_soft_irq
FROM linux_irqs irq
WHERE irq.dur > 100000  -- > 0.1ms
ORDER BY irq.dur DESC
LIMIT 30;
```

---

### P2-4: sched.thread_level_parallelism — 线程并行度

**SQL 查询模板**：
```sql
INCLUDE PERFETTO MODULE sched.thread_level_parallelism;

SELECT
  r.tc.ts,
  r.tc.runnable_thread_count,
  ac.active_cpu_count
FROM sched_runnable_thread_count r.tc
JOIN sched_active_cpu_count ac ON ac.ts = r.tc.ts;
```

---

### P2-5: android.kernel_wakelocks — Wakelock 分析

**SQL 查询模板**：
```sql
INCLUDE PERFETTO MODULE android.kernel_wakelocks;

SELECT
  wk.ts,
  wk.name,
  wk.type,
  wk.held_dur / 1000000.0 AS held_ms,
  wk.awake_dur / 1000000.0 AS awake_ms,
  wk.held_ratio
FROM android_kernel_wakelocks wk
WHERE wk.held_dur > 10000000  -- > 10ms
ORDER BY wk.held_dur DESC
LIMIT 20;
```

---

### P2-6: android.memory.lmk — LMK Kill 事件

**SQL 查询模板**：
```sql
INCLUDE PERFETTO MODULE android.memory.lmk;

SELECT
  lmk.ts,
  lmk.process_name,
  lmk.oom_score_adj,
  lmk.kill_reason,
  lmk.pid
FROM android_lmk_events lmk
ORDER BY lmk.ts;
```

---

### P2-7: intervals.overlap — 通用区间重叠工具

**用途**：替代 SI 中所有手动时间重叠计算。

**示例**：
```sql
INCLUDE PERFETTO MODULE intervals.overlap;

-- 计算 SI$ slice 在时间轴上的重叠密度
SELECT *
FROM intervals_overlap_count!(
  (SELECT ts, dur FROM slice WHERE name GLOB 'SI$*' AND dur > 0),
  'ts', 'dur'
);
```

---

## 五、对 SI 代码的改进建议汇总

### 5.1 SQL 查询改进（低风险，立即可做）

| 现有文件 | 改进点 |
|---------|-------|
| `collector/frame.py` | `LIKE` → `GLOB`；添加 `android_frame_stats` 查询 |
| `collector/io.py` | `LIKE` → `GLOB` |
| `collector/block.py` | `LIKE` → `GLOB` |
| `collector/thread.py` | 用 `thread_slice_time_in_state` 替代手动 sched overlap |
| `collector/sched.py` | 添加 `sched_latency_for_running_interval` 查询 |
| `collector/cpu.py` | 用 `cpu_cycles_per_thread` 替代手动 CPU% 计算 |
| `collector/startup.py` | 用 `android_startups` + `android_startup_opinionated_breakdown` 重构 |

### 5.2 新增 Collector Mixin（中等风险，按优先级分批）

| 优先级 | 新模块 | 方法 | 依赖的 stdlib |
|--------|-------|------|-------------|
| P0 | `collector/lock.py` | `collect_lock_contention()` | `android.monitor_contention` |
| P0 | `collector/binder.py` | `collect_binder_txns()`, `collect_binder_breakdown()` | `android.binder`, `android.binder_breakdown` |
| P0 | `collector/gc.py` | `collect_gc_events()` | `android.garbage_collection` |
| P0 | `collector/anr.py` | `collect_anrs()` | `android.anrs` |
| P1 | `collector/input_latency.py` | `collect_input_latency()` | `android.input` |

### 5.3 PerfSummary 扩展字段

```python
@dataclass
class PerfSummary:
    # ... 现有字段 ...
    # 新增字段
    lock_contention: list[dict] | None = None      # 锁竞争事件
    binder_txns: list[dict] | None = None           # Binder 事务
    gc_events: list[dict] | None = None             # GC 事件
    anr_events: list[dict] | None = None            # ANR 事件
    input_latency: list[dict] | None = None         # 输入延迟分解
    startup_metrics: dict | None = None             # TTID/TTFD
```

### 5.4 LIKE → GLOB 迁移

需要检查和替换的文件和模式：

| 文件 | 现有 LIKE 用法 | 替换为 |
|------|--------------|-------|
| `frame.py` | `LIKE '%Choreographer%'` 等 | `GLOB '*Choreographer*'` |
| `io.py` | `LIKE 'SI$net%'` 等 | `GLOB 'SI$net*'` |
| `block.py` | `LIKE 'SI$block%'` | `GLOB 'SI$block*'` |
| `thread.py` | 各种 slice 名匹配 | `GLOB` 模式 |
| `startup.py` | slice 名匹配 | `GLOB` 模式 |

---

## 六、总结

### 核心发现

1. **SI 未使用任何 stdlib 模块**，所有查询直接操作原始表。这是最大的改进机会。
2. **60+ 个 stdlib 模块中**，SI 可直接受益的有 **25+ 个**。
3. **最高价值的 6 个模块**（P0）：
   - `android.monitor_contention` — 锁竞争（SI 完全空白）
   - `android.binder` + `android.binder_breakdown` — Binder 分析（SI 完全空白）
   - `android.startup.*` — 启动分析增强（替代 SI 现有手动实现）
   - `android.garbage_collection` — GC 事件（SI 完全空白）
   - `android.anrs` — ANR 检测（SI 完全空白）
   - `slices.cpu_time` + `slices.time_in_state` — Slice 级精确分析

### 预期收益

| 能力 | 现状 | 增强后 |
|------|------|--------|
| 锁竞争 | 无 | 自动检测主线程锁阻塞，定位阻塞方法+源码 |
| Binder | 无 | 检测耗时 IPC，分解 client/server 延迟 |
| GC | 无 | 检测 GC pause，分析对帧/启动的影响 |
| ANR | 无 | 自动检测 trace 中的 ANR |
| 启动 | 手动 slice 查询 | stdlib 标准化启动检测 + TTID/TTFD + 自动瓶颈分解 |
| 帧分析 | wall duration only | per-frame CPU time + jank 分级 + vsync delay |
| 线程状态 | 手动 sched overlap | stdlib 精确的 slice 级线程状态分解 |
| SQL 安全 | LIKE + 手动算术 | GLOB + stdlib 预计算（SPAN_JOIN safety） |
