
# SmartInspector Perfetto SQL 分析能力差距报告

> 生成时间: 2026-05-11
> 目的: 分析 SI 当前 Perfetto SQL 使用情况，对比 Perfetto stdlib 完整能力，找出可新增的分析维度

---

## 第一部分：SI 当前使用的 Perfetto 表和字段

### 1.1 已使用的核心表

| 表名 | 使用位置 | 查询字段 | 用途 |
|------|----------|----------|------|
| `slice` | frame.py, io.py, block.py, thread.py, perfetto.py, startup.py | id, name, ts, dur, depth, parent_id, track_id, cat | SI$ 自定义切片、doFrame、Choreographer、IO slices |
| `sched` | sched.py, cpu.py | ts, dur, utid, end_state, cpu | 调度切换、CPU 占用率、上下文切换统计 |
| `thread` | sched.py, cpu.py, thread.py, perfetto.py, startup.py | utid, tid, name, upid, start_ts | 线程名解析、主线程识别 |
| `process` | cpu.py, perfetto.py | upid, pid, uid, name | 进程名解析、目标进程识别 |
| `thread_state` | thread.py | ts, dur, utid, state | 线程状态分布 (Running/Sleeping/DiskSleep) |
| `__intrinsic_thread_state` | thread.py | ts, dur, utid, state, blocked_function, io_wait, waker_utid | 增强线程状态（含阻塞函数、唤醒者） |
| `sched_blocked_reason` | sched.py | utid, blocked_reason, io_wait | 线程阻塞原因 |
| `perf_sample` | cpu.py | ts, utid, callsite_id | CPU 采样热点分析 |
| `stack_profile_callsite` | cpu.py | id, frame_id, parent_id | 调用链重建 |
| `stack_profile_frame` | cpu.py | id, name | 函数名解析 |
| `counter` | sys.py | ts, value, track_id | CPU idle/freq/fork 计数器 |
| `cpu_counter_track` | sys.py | id, cpu, name | CPU 计数器轨道元数据 |
| `process_counter_track` | perfetto.py | id, upid, name | 进程内存计数器 (mem.rss, mem.rss.anon) |
| `actual_frame_timeline_slice` | frame.py | ts, dur, display_frame_token, surface_frame_token, jank_type, layer_name | 帧时间线和 jank 检测 |
| `expected_frame_timeline_slice` | frame.py | ts, dur, display_frame_token | 预期帧时间预算 |
| `heap_graph_object` | memory.py | id, upid, type_id, self_size, reachable | Java 堆对象分析 |
| `heap_graph_class` | memory.py | id, name | 类名 |
| `heap_graph_reference` | memory.py | owner_id, owned_id, field_name_id | 引用链 |
| `heap_graph_field` | memory.py | id, name | 字段名 |
| `android_logs` | block.py | ts, tag, msg | SIBlock logcat 堆栈关联 |
| `metadata` | perfetto.py | name, str_value | 设备/trace 元数据 |
| `trace_bounds` | cpu.py | start_ts, end_ts | trace 时间范围 |
| `package_list` | perfetto.py | package_name, uid | 包名到UID映射 |
| `thread_track` | frame.py, perfetto.py, startup.py | id, utid | slice到thread关联 |

### 1.2 已覆盖的分析维度

| 维度 | Collector 方法 | 数据来源 |
|------|---------------|----------|
| **调度分析** | `collect_sched()` | sched + thread + sched_blocked_reason |
| **CPU 热点** | `collect_cpu_hotspots()` | perf_sample + stack_profile_callsite/frame |
| **CPU 占用率** | `collect_cpu_usage()` | sched + thread + process + trace_bounds |
| **帧时间线/Jank** | `collect_frame_timeline()` | actual/expected_frame_timeline_slice |
| **View 切片** | `collect_view_slices()` | slice (SI$RV#, SI$inflate#, SI$view#, doFrame) |
| **Compose 重组** | `collect_compose_slices()` | slice (SI$compose#) |
| **IO 切片** | `collect_io_slices()` | slice (SI$net#, SI$db#, SI$img#) |
| **触摸事件** | `collect_input_events()` | slice (SI$touch#) |
| **主线程阻塞** | `collect_block_events()` | slice (SI$block#) + android_logs (SIBlock) |
| **线程状态** | `collect_thread_state()` | thread_state / __intrinsic_thread_state |
| **系统统计** | `collect_sys_stats()` | counter + cpu_counter_track (cpuidle_time, cpufreq, num_forks) |
| **进程内存** | `collect_process_memory()` | process_counter_track + counter (mem.rss, mem.rss.anon) |
| **堆内存** | `collect_memory()` | heap_graph_object + heap_graph_class + heap_graph_reference |
| **线程信息** | `collect_threads()` | thread |
| **冷启动** | `StartupAnalyzer.analyze()` | slice + thread_track + thread (SI$Activity, doFrame) |

---

## 第二部分：Perfetto stdlib 可用但 SI 未使用的模块和表

### 2.1 完全未覆盖的新分析维度

#### 2.1.1 ANR 深度分析

**stdlib 模块**: `INCLUDE PERFETTO MODULE android.anrs;`

**表**: `android_anrs`

| 字段 | 类型 | 说明 |
|------|------|------|
| process_name | STRING | ANR 进程名 |
| pid | LONG | 进程 PID |
| upid | JOINID(process.id) | 进程 UPID |
| error_id | STRING | ANR UUID |
| ts | TIMESTAMP | ANR 发生时间 |
| dur | DURATION | ANR 持续时间 |
| reason | STRING | ANR 原因 |
| thread_name | STRING | 被阻塞的线程名 |
| thread_utid | JOINID(thread.id) | 被阻塞的线程 utid |

**解决的性能问题**: ANR 是 Android 最严重的性能问题之一，SI 目前完全没有 ANR 检测能力

**示例 SQL**:
```sql
INCLUDE PERFETTO MODULE android.anrs;

SELECT a.process_name, a.reason, a.dur / 1e6 AS anr_dur_ms, a.thread_name, a.ts
FROM android_anrs a
ORDER BY a.ts;

-- ANR 期间主线程 slices
SELECT s.name, s.dur / 1e6 AS dur_ms, s.depth
FROM android_anrs a
JOIN slice s ON s.track_id IN (
  SELECT tt.id FROM thread_track tt
  JOIN thread t ON tt.utid = t.utid
  WHERE t.utid = a.thread_utid
)
WHERE s.ts >= a.ts AND s.ts <= a.ts + a.dur
ORDER BY s.dur DESC;
```

---

#### 2.1.2 Binder 分析

**stdlib 模块**: `INCLUDE PERFETTO MODULE android.binder;` / `android.binder_breakdown;`

**表**:
- `android_binder_metrics_by_process` — Binder 事务计数 (process_name, pid, slice_name, event_count, dur)
- `android_binder_server_breakdown` — 服务端分解 (binder_txn_id, binder_reply_id, ts, dur, client_process, server_process, client_thread, server_thread)

**解决的性能问题**: Binder IPC 延迟直接影响性能，主线程 Binder 调用是常见卡顿来源

**示例 SQL**:
```sql
INCLUDE PERFETTO MODULE android.binder;

SELECT process_name, slice_name, event_count, dur / 1e6 AS total_dur_ms
FROM android_binder_metrics_by_process
ORDER BY dur DESC LIMIT 20;

INCLUDE PERFETTO MODULE android.binder_breakdown;

SELECT client_process, server_process, client_thread, server_thread, dur / 1e6 AS dur_ms
FROM android_binder_server_breakdown
ORDER BY dur DESC LIMIT 20;
```

---

#### 2.1.3 DVFS 分析

**stdlib 模块**: `INCLUDE PERFETTO MODULE android.dvfs;`

**表**:
- `android_dvfs_counters` — DVFS 计数器 (name, ts, value, dur)
- `android_dvfs_counter_stats` — 统计汇总 (name, avg_value, min_value, max_value, pct_25, pct_50, pct_75, pct_90)

**解决的性能问题**: CPU/GPU/DDR 频率调节影响功耗和性能

**示例 SQL**:
```sql
INCLUDE PERFETTO MODULE android.dvfs;
SELECT name, avg_value, min_value, max_value, pct_50, pct_90
FROM android_dvfs_counter_stats ORDER BY name;
```

---

#### 2.1.4 WakeLock / 内核唤醒锁分析

**stdlib 模块**: `INCLUDE PERFETTO MODULE android.kernel_wakelocks;`

**表**: `android_kernel_wakelocks` (ts, dur, awake_dur, name, held_pct)

**解决的性能问题**: WakeLock 阻止系统进入低功耗状态，导致电池消耗

**示例 SQL**:
```sql
INCLUDE PERFETTO MODULE android.kernel_wakelocks;
SELECT name, held_pct, dur / 1e6 AS dur_ms, awake_dur / 1e6 AS awake_ms
FROM android_kernel_wakelocks ORDER BY held_pct DESC LIMIT 20;
```

---

#### 2.1.5 电池/功耗分析

**stdlib 模块**: `android.battery`, `android.battery.doze`, `android.battery.charging_states`, `android.power_rails`

**表**:
- `android_battery_charge` (ts, current_avg_ua, capacity_percent, charge_uah, voltage_uv)
- `android_power_rails_counters` (仅 Pixel 设备)

---

#### 2.1.6 GC (垃圾回收) 分析

**stdlib 模块**: `INCLUDE PERFETTO MODULE android.garbage_collection;`

**表**: `android_garbage_collection_events`
- tid, pid, utid, upid, ts, dur, gc_reason (ALLOC, CONCURRENT, EXTERNAL)
- reclaimed_objects, reclaimed_size, total_objects_freed, total_size_freed

**解决的性能问题**: GC 暂停直接影响帧率

**示例 SQL**:
```sql
INCLUDE PERFETTO MODULE android.garbage_collection;

SELECT ts, dur / 1e6 AS gc_dur_ms, gc_reason, reclaimed_objects, reclaimed_size / 1024 AS reclaimed_kb
FROM android_garbage_collection_events
WHERE upid = (SELECT upid FROM process WHERE name = 'com.example.app' LIMIT 1)
ORDER BY dur DESC LIMIT 20;
```

---

#### 2.1.7 Monitor Contention (Java 锁竞争) 分析

**stdlib 模块**: `INCLUDE PERFETTO MODULE android.monitor_contention;`

**表**: `android_monitor_contention`
- blocking_method, blocked_method, short_blocking_method, short_blocked_method
- blocked_utid, blocking_utid, blocked_upid, blocking_upid, ts, dur

**解决的性能问题**: Java synchronized 锁竞争是主线程卡顿的重要原因，与 SI$block# 互补

**示例 SQL**:
```sql
INCLUDE PERFETTO MODULE android.monitor_contention;

SELECT blocked_method, blocking_method, dur / 1e6 AS wait_ms, blocked_utid, blocking_utid
FROM android_monitor_contention ORDER BY dur DESC LIMIT 20;
```

---

#### 2.1.8 输入事件延迟分析

**stdlib 模块**: `INCLUDE PERFETTO MODULE android.input;`

**表**: `android_input_events`
- dispatch_ts, delivery_ts, ack_ts, ack_receive_ts
- round_trip_latency, app_latency, system_latency

**解决的性能问题**: 比当前 SI$touch# 更精确的输入延迟分解

---

#### 2.1.9 调度延迟分析

**stdlib 模块**: `INCLUDE PERFETTO MODULE sched.latency;`

**表**: `sched_latency_for_running_interval`
- thread_state_id, sched_id, utid, ts, dur (runnable duration before running)

**解决的性能问题**: 线程从 Runnable 到 Running 的调度延迟，补充 thread_state 分析

**示例 SQL**:
```sql
INCLUDE PERFETTO MODULE sched.latency;

SELECT t.name AS thread_name, COUNT(*) AS waits, SUM(sl.dur) / 1e6 AS total_wait_ms, MAX(sl.dur) / 1e6 AS max_wait_ms
FROM sched_latency_for_running_interval sl
JOIN thread t ON sl.utid = t.utid
GROUP BY t.name ORDER BY total_wait_ms DESC LIMIT 20;
```

---

#### 2.1.10 其他新维度

| 维度 | stdlib 模块 | 核心表 | 解决的性能问题 |
|------|-----------|--------|--------------|
| 系统挂起/唤醒 | android.suspend, android.wakeups | android_suspend_state, android_wakeups | 功耗分析 |
| Block IO | linux.block_io | linux_active_block_io_operations_by_device | IO 瓶颈 |
| CPU 频率 | linux.cpu.frequency | cpu_frequency_counters | 频率区间统计 |
| CPU 利用率 | linux.cpu.utilization.* | cpu_cycles_per_thread, cpu_utilization_per_second | CPU 周期/频率加权分析 |
| OOM Adjuster | android.oom_adjuster | android_oom_adj_intervals | 进程优先级变化 |
| 屏幕状态 | android.screen_state | android_screen_state | 屏幕开/关时间线 |
| LMK 事件 | android.memory.lmk | android_lmk_events | 内存压力杀进程 |
| DMA-Buf | android.memory.dmabuf | android_dmabuf_allocs | GPU 内存泄漏 |
| 进程冻结 | android.freezer | android_freezer_events | 进程冻结时长 |
| JobScheduler | android.job_scheduler | android_job_scheduler_events | 后台任务调度 |

---

### 2.2 现有分析能力的增强方向

#### 2.2.1 增强启动分析

**当前**: `StartupAnalyzer` 自定义 SQL 查找 SI$ 标签切片

**stdllib 提供**:
- `android.startup.startups` → `android_startups` 表: 自动检测所有启动事件（不依赖 SI$ 标签），含 startup_type (cold/warm/hot)
- `android.startup.startup_breakdowns` → `android_startup_opinionated_breakdown`: 混合 thread_state + slice 的启动分解，自动归类 binder/io/cpu/lock
- `android.startup.time_to_display` → `android_startup_time_to_display`: TTID/TTFD 标准指标

**建议**: 使用 stdlib 替代自定义启动检测，添加 TTID/TTFD

---

#### 2.2.2 增强帧分析

**stdllib 提供**:
- `android.frames.timeline` → `android_frames_choreographer_do_frame`: Choreographer 切片 + frame_id + ui/render thread
- `android.frames.per_frame_metrics` → `android_frames_overrun`: 每帧 overrun（错过 deadline 的量）

**建议**: 使用 `android_frames_overrun` 替代手动 jank 计算

---

#### 2.2.3 增强 Slice 分析

**stdllib 提供**:
- `slices.cpu_time` → `thread_slice_cpu_time`: 每个 slice 的实际 CPU 时间（排除子 slice 和非 CPU 时间）
- `slices.self_dur` → `slice_self_dur`: 每个 slice 的"自身时间"（排除子 slice 时间）
- `slices.with_context` → `thread_slice`: 自动关联 thread + process + track 信息的 slice 视图

**建议**: `thread_slice_cpu_time` 可区分 wall time vs CPU time，精确识别 IO vs CPU 耗时

---

#### 2.2.4 增强堆内存分析

**stdllib 提供**:
- `android.memory.heap_graph.dominator_tree` → `heap_graph_dominator_tree`: 支配树分析
- `android.memory.heap_graph.heap_graph_stats` → `android_heap_graph_stats`: 堆图统计汇总
- `android.memory.heap_graph.class_summary_tree`: 按类聚合的内存摘要树

---

### 2.3 未使用的 Perfetto 核心表字段

| 表 | 未用字段 | 潜在价值 |
|------|----------|----------|
| `slice` | `category`, `arg_set_id`, `thread_ts`, `thread_dur` | 分类过滤、参数提取、线程时间 vs 墙钟时间 |
| `sched` | `priority`, `ucpu` | 线程优先级变化、CPU 亲和性 |
| `thread_state` | `waker_utid`, `waker_id`, `irq_context`, `ucpu` | 唤醒者分析、中断上下文 |
| `process` | `start_ts`, `end_ts`, `parent_upid`, `cmdline`, `android_appid` | 进程生命周期 |
| `thread` | `is_main_thread`, `end_ts`, `is_idle` | 主线程标识（比 name='main' 更可靠） |
| `cpu` | `cluster_id`, `capacity` | CPU 大小核簇映射 |
| `perf_sample` | `cpu`, `cpu_mode`, `unwind_error` | 用户态/内核态分布 |
| `flow` | `slice_out`, `slice_in`, `trace_id` | 跨线程/进程操作追踪 |
| `args` | `flat_key`, `key`, `int_value`, `string_value` | Slice 参数提取 |

---

## 第三部分：新增能力优先级评估

### P0 (高价值，实现难度低)

| 新增能力 | 依赖模块 | 实现复杂度 | 用户价值 |
|----------|----------|-----------|----------|
| **ANR 深度分析** | android.anrs | 低 | 极高 |
| **GC 暂停分析** | android.garbage_collection | 低 | 高 |
| **Monitor Contention (锁竞争)** | android.monitor_contention | 低 | 高 |
| **调度延迟分析** | sched.latency | 低 | 高 |
| **Slice CPU Time** | slices.cpu_time | 低 | 高 |
| **Slice Self Duration** | slices.self_dur | 低 | 中 |

### P1 (高价值，实现难度中等)

| 新增能力 | 依赖模块 | 实现复杂度 | 用户价值 |
|----------|----------|-----------|----------|
| **Binder 分析** | android.binder, android.binder_breakdown | 中 | 高 |
| **启动分析增强** | android.startup.* | 中 | 高 |
| **帧分析增强** | android.frames.* | 中 | 中 |
| **CPU 频率/簇分析** | android.cpu.cluster_type, linux.cpu.frequency | 中 | 中 |
| **输入延迟分析** | android.input | 中 | 高 |
| **CPU 利用率增强** | linux.cpu.utilization.* | 中 | 中 |

### P2 (中等价值，或需要特定硬件/配置)

| 新增能力 | 依赖模块 | 用户价值 |
|----------|----------|----------|
| **WakeLock 分析** | android.kernel_wakelocks | 中 |
| **电池分析** | android.battery.* | 中 |
| **DVFS 分析** | android.dvfs | 中 |
| **Block IO 分析** | linux.block_io | 中 |
| **OOM Adjuster** | android.oom_adjuster | 中 |
| **LMK 事件** | android.memory.lmk | 中 |
| **堆图增强** | android.memory.heap_graph.* | 中 |
| **网络包分析** | android.network_packets | 中 |
| **进程冻结** | android.freezer | 低 |
| **屏幕状态** | android.screen_state | 低 |
| **JobScheduler** | android.job_scheduler | 低 |
| **电源轨** | android.power_rails (仅 Pixel) | 低 |

---

## 第四部分：推荐新增的 Collector Mixin 设计

### 4.1 AnrMixin (`collector/anr.py`)
- `collect_anr_events()` → 使用 `android_anrs` 检测 ANR，关联主线程 slices 和 thread_state
- 需要 atrace category: `am` (已有)

### 4.2 GcMixin (`collector/gc.py`)
- `collect_gc_events()` → 使用 `android_garbage_collection_events` 分析 GC
- 需要 atrace category: `art` (需新增)

### 4.3 LockMixin (`collector/lock.py`)
- `collect_lock_contention()` → 使用 `android_monitor_contention` 分析锁竞争
- 需要 atrace category: `art` (需新增)

### 4.4 BinderMixin (`collector/binder.py`)
- `collect_binder_analysis()` → 使用 `android_binder_metrics_by_process` + `android_binder_server_breakdown`
- 需要 atrace category: `binder_driver` (需新增)

### 4.5 SchedLatencyMixin (`collector/sched_latency.py`)
- `collect_sched_latency()` → 使用 `sched_latency_for_running_interval`
- 需要 ftrace: `sched/sched_switch`, `sched/sched_wakeup*` (已有)

### 4.6 增强现有 Mixin
- `frame.py`: 集成 `android_frames_overrun` (per_frame_metrics)
- `cpu.py`: 集成 `cpu_cycles_per_thread` (linux.cpu.utilization.thread)
- `startup.py`: 使用 `android_startups` + `startup_breakdowns` + `time_to_display`
- `memory.py`: 使用 `heap_graph_dominator_tree` 替代简单 dominator 查询

---

## 第五部分：Perfetto stdlib 完整模块清单 (Android/Linux 相关)

### android.* 模块 (38个)

| 模块 | 核心表/视图 | 分析维度 |
|------|-----------|----------|
| `android.anrs` | android_anrs | ANR 检测 |
| `android.app_process_starts` | - | 进程启动 |
| `android.battery` | android_battery_charge | 电池状态 |
| `android.battery.charging_states` | - | 充电状态 |
| `android.battery.doze` | - | Doze 模式 |
| `android.battery_stats` | - | 电池统计 |
| `android.binder` | android_binder_metrics_by_process | Binder 计数 |
| `android.binder_breakdown` | android_binder_server_breakdown | Binder 延迟分解 |
| `android.bitmaps` | - | Bitmap 分析 |
| `android.cpu.cluster_type` | android_cpu_cluster_mapping | CPU 大小核 |
| `android.cpu.cpu_per_uid` | - | 每UID CPU时间 |
| `android.dvfs` | android_dvfs_counters, android_dvfs_counter_stats | DVFS 分析 |
| `android.entity_state_residency` | - | 电源实体状态 |
| `android.frames.jank_type` | - | Jank 类型 |
| `android.frames.per_frame_metrics` | android_frames_overrun | 帧超时量 |
| `android.frames.timeline` | android_frames_choreographer_do_frame | 帧时间线 |
| `android.freezer` | android_freezer_events | 进程冻结 |
| `android.garbage_collection` | android_garbage_collection_events | GC 分析 |
| `android.input` | android_input_events | 输入延迟 |
| `android.job_scheduler` | android_job_scheduler_events | Job 调度 |
| `android.kernel_wakelocks` | android_kernel_wakelocks | 内核锁 |
| `android.memory.dmabuf` | android_dmabuf_allocs | DMA-Buf 内存 |
| `android.memory.heap_graph.*` | heap_graph_dominator_tree, heap_graph_stats, class_summary_tree | 堆图分析 |
| `android.memory.heap_profile.summary_tree` | - | 堆 profile 汇总 |
| `android.memory.lmk` | android_lmk_events | LMK 杀进程 |
| `android.memory.process` | - | 进程内存 |
| `android.monitor_contention` | android_monitor_contention | Java 锁竞争 |
| `android.network_packets` | - | 网络包 |
| `android.oom_adjuster` | android_oom_adj_intervals | OOM 分数 |
| `android.power_rails` | android_power_rails_counters | 电源轨 (仅 Pixel) |
| `android.screen_state` | android_screen_state | 屏幕状态 |
| `android.startup.startups` | android_startups | 启动检测 |
| `android.startup.startup_breakdowns` | android_startup_opinionated_breakdown | 启动分解 |
| `android.startup.time_to_display` | android_startup_time_to_display | TTID/TTFD |
| `android.surfaceflinger` | - | SurfaceFlinger |
| `android.suspend` | android_suspend_state | 系统挂起 |
| `android.thread` | - | 线程信息 |
| `android.wakeups` | android_wakeups | 唤醒事件 |

### linux.* 模块 (14个)

| 模块 | 核心表/视图 | 分析维度 |
|------|-----------|----------|
| `linux.block_io` | linux_active_block_io_operations_by_device | 块 IO |
| `linux.cpu.frequency` | cpu_frequency_counters | CPU 频率 |
| `linux.cpu.idle` | - | CPU idle |
| `linux.cpu.idle_stats` | - | CPU idle 统计 |
| `linux.cpu.idle_time_in_state` | - | CPU idle 各状态时间 |
| `linux.cpu.utilization.system` | cpu_utilization_per_second | 系统利用率 |
| `linux.cpu.utilization.thread` | cpu_cycles_per_thread | 线程 CPU 周期 |
| `linux.cpu.utilization.thread_cpu` | thread_cpu_usage | 线程 CPU 使用率 |
| `linux.cpu.utilization.process` | - | 进程 CPU 利用率 |
| `linux.cpu.utilization.slice` | - | Slice CPU 利用率 |
| `linux.devfreq` | - | 设备频率 |
| `linux.irqs` | - | 中断分析 |
| `linux.memory.high_watermark` | - | 内存高水位 |
| `linux.memory.process` | - | Linux 进程内存 |

### sched.* 模块 (6个)

| 模块 | 分析维度 |
|------|----------|
| `sched.latency` | 调度延迟 |
| `sched.runnable` | Runnable 状态分析 |
| `sched.states` | 状态转换函数 |
| `sched.thread_level_parallelism` | 线程并行度 |
| `sched.time_in_state` | CPU 频率分布 |
| `sched.with_context` | 调度上下文 |

### slices.* 模块 (5个)

| 模块 | 分析维度 |
|------|----------|
| `slices.cpu_time` | Slice CPU 时间 |
| `slices.self_dur` | Slice 自身时间 |
| `slices.stack` | Slice 调用栈 hash |
| `slices.with_context` | Slice + 线程/进程上下文 |
| `slices.time_in_state` | Slice CPU 频率分布 |

### intervals.* 模块 (2个)

| 模块 | 分析维度 |
|------|----------|
| `intervals.overlap` | 区间重叠计数 |
| `intervals.intersect` | 区间交集 |

---

## 第六部分：重要 SQL 函数和最佳实践

| 函数 | 用途 |
|------|------|
| `trace_end()` | trace 结束时间戳，处理 dur=-1 |
| `trace_start()` | trace 开始时间戳 |
| `EXTRACT_ARG(arg_set_id, 'key')` | 从 slice/track 参数集提取值 |
| `IIF(dur = -1, trace_end() - ts, dur)` | 安全计算有效 duration |
| `SPAN_JOIN` | 时间区间连接（需 PARTITIONED） |

**最佳实践**:
1. 幂等性: 使用 `CREATE OR REPLACE PERFETTO TABLE/VIEW/FUNCTION`
2. SPAN_JOIN: 中间表必须 `CREATE PERFETTO TABLE`，用 `PARTITIONED`
3. 唯一标识: 用 `utid`/`upid` 而非 `tid`/`pid`
4. 字符串匹配: 用 `GLOB` 而非 `LIKE`
5. 列名前缀: 所有列名加表别名

---

## 第七部分：需要新增的 atrace category

当前默认: `sched, freq, idle, power, memreclaim, gfx, view, input, dalvik, am, wm`

建议新增:

| Category | 用途 | 启用的分析 |
|----------|------|-----------|
| `art` | ART 虚拟机事件 | GC 分析、Monitor Contentions |
| `binder_driver` | Binder 驱动事件 | Binder 事务追踪 |
| `ss` | System Server | JobScheduler、OOM Adjuster |

---

## 第八部分：实施建议

### Phase 1 (立即收益，低风险)
1. 新增 `AnrMixin` — ANR 检测
2. 新增 `GcMixin` — GC 分析
3. 新增 `LockMixin` — Java 锁竞争分析
4. 新增 `SchedLatencyMixin` — 调度延迟
5. 集成 `thread_slice_cpu_time` — 区分 IO vs CPU 耗时

### Phase 2 (中等投入，显著增强)
1. 新增 `BinderMixin` — Binder 分析
2. 增强 `StartupAnalyzer` 使用 stdlib
3. 增强帧分析使用 `android_frames_overrun`
4. 新增 CPU 大小核分析

### Phase 3 (扩展能力)
1. WakeLock / 功耗分析
2. Block IO 分析
3. OOM Adjuster / LMK 分析
4. 输入延迟增强
5. 堆图支配树增强
