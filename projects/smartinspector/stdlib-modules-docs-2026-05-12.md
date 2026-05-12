# SmartInspector Perfetto Stdlib 模块技术文档

> 生成日期：2026-05-12
> 分支：feat/stdlib-modules
> PR：https://github.com/mufans/AppSmartInspector/pull/12

本文档详细描述SmartInspector集成的13个Perfetto SQL Standard Library模块，包括SQL查询、输出字段、使用场景和注意事项。

---

## P0 核心模块

### P0-1: 锁竞争分析 (android.monitor_contention)

- **文件**: `collector/lock.py`
- **类名**: `LockMixin`
- **方法**: `collect_lock_contention() -> list[dict]`
- **Perfetto stdlib**: `INCLUDE PERFETTO MODULE android.monitor_contention;`
- **查询的表**:
  - `android_monitor_contention` — 锁竞争事件
  - `android_monitor_contention_chain_thread_state_by_txn` — 阻塞线程状态分解
- **解决的问题**: 检测Java `synchronized` 锁竞争，定位阻塞方法名和源码位置，分析阻塞线程在等待期间的状态分布
- **使用场景**: 主线程卡顿分析、ANR根因定位、多线程性能问题排查

#### SQL查询详解

**查询1: Top 20 锁竞争事件**
```sql
INCLUDE PERFETTO MODULE android.monitor_contention;

SELECT
  mc.id,                          -- 竞争事件ID
  mc.ts,                          -- 事件时间戳(ns)
  mc.dur / 1000000.0 AS dur_ms,   -- 等待时长(ms)
  mc.short_blocked_method,        -- 被阻塞的方法名
  mc.short_blocking_method,       -- 持有锁的方法名
  mc.blocked_src,                 -- 被阻塞方法源码位置
  mc.blocking_src,                -- 持锁方法源码位置
  mc.blocked_thread_name,         -- 被阻塞线程名
  mc.blocking_thread_name,        -- 持锁线程名
  mc.is_blocked_thread_main,      -- 被阻塞线程是否为主线程
  mc.is_blocking_thread_main,     -- 持锁线程是否为主线程
  mc.waiter_count,                -- 等待该锁的线程数
  mc.blocked_thread_tid,          -- 被阻塞线程TID
  mc.blocking_thread_tid,         -- 持锁线程TID
  mc.pid                          -- 进程PID
FROM android_monitor_contention mc
WHERE mc.dur > 1000000            -- 只关注>1ms的竞争
  AND mc.dur != -1                -- 排除未完成事件
  AND mc.upid = (SELECT upid FROM process WHERE name GLOB '{pkg}')
ORDER BY mc.dur DESC
LIMIT 20
```

**查询2: 重度竞争(>5ms)的线程状态分解**
```sql
SELECT
  mc.id,
  mc.short_blocked_method,
  mc.dur / 1000000.0 AS contention_dur_ms,
  mcts.thread_state,              -- 线程状态(Running/Sleeping等)
  mcts.thread_state_dur / 1000000.0 AS state_dur_ms,  -- 该状态持续时长
  mcts.thread_state_count         -- 该状态出现次数
FROM android_monitor_contention mc
JOIN android_monitor_contention_chain_thread_state_by_txn mcts
  ON mcts.id = mc.id
WHERE mc.id IN (...)              -- Top 20竞争事件ID
  AND mc.dur > 5000000            -- 只分析>5ms的
ORDER BY mc.dur DESC, mcts.thread_state_dur DESC
```

#### 输出字段

| 字段 | 类型 | 含义 |
|------|------|------|
| id | int | 竞争事件ID |
| ts_ns | int | 事件时间戳(纳秒) |
| dur_ms | float | 等待时长(毫秒) |
| short_blocked_method | str | 被阻塞的方法名 |
| short_blocking_method | str | 持有锁的方法名 |
| blocked_src | str | 被阻塞方法源码位置(类:行号) |
| blocking_src | str | 持锁方法源码位置 |
| blocked_thread | str | 被阻塞线程名 |
| blocking_thread | str | 持锁线程名 |
| is_blocked_main | bool | 被阻塞线程是否为主线程 |
| is_blocking_main | bool | 持锁线程是否为主线程 |
| waiter_count | int | 等待该锁的线程数 |
| blocking_thread_states | list | 可选，>5ms时的线程状态分解 |

#### 注意事项
- 需要 Android 10+ 的 trace（`android.monitor_contention` 模块依赖较新API）
- `blocked_src` 和 `blocking_src` 可能为空（取决于是否开启了源码关联）
- 仅返回>1ms的竞争事件，短竞争被过滤
- 线程状态分解仅在竞争>5ms时才查询

---

### P0-2: Binder 事务分析 (android.binder + android.binder_breakdown)

- **文件**: `collector/binder.py`
- **类名**: `BinderMixin`
- **方法**:
  - `collect_binder_txns() -> list[dict]` — Top Binder事务列表
  - `collect_binder_breakdown() -> list[dict]` — Binder延迟分解
- **Perfetto stdlib**:
  - `INCLUDE PERFETTO MODULE android.binder;`
  - `INCLUDE PERFETTO MODULE android.binder_breakdown;`
- **查询的表**:
  - `android_binder_txns` — Binder事务
  - `android_binder_client_server_breakdown` — 客户端/服务端延迟分解
- **解决的问题**: 识别耗时Binder IPC调用，分解客户端等待和服务端处理延迟
- **使用场景**: 跨进程调用卡顿分析、ContentProvider查询慢、SystemService调用延迟

#### SQL查询详解

**查询1: Top 30 同步Binder事务**
```sql
INCLUDE PERFETTO MODULE android.binder;

SELECT
  bt.binder_txn_id,               -- 事务ID
  bt.client_ts,                   -- 客户端发起时间
  bt.client_dur / 1000000.0,      -- 客户端总耗时(ms)
  bt.server_dur / 1000000.0,      -- 服务端处理耗时(ms)
  bt.aidl_name,                   -- AIDL接口名
  bt.method_name,                 -- 方法名
  bt.client_process/thread/tid/pid,  -- 客户端信息
  bt.server_process/thread/tid/pid,  -- 服务端信息
  bt.is_main_thread,              -- 是否在主线程发起
  bt.is_sync                      -- 是否同步调用
FROM android_binder_txns bt
WHERE bt.is_sync = TRUE            -- 只看同步调用
  AND bt.client_dur > 1000000      -- >1ms
  AND bt.client_dur != -1
ORDER BY bt.client_dur DESC
LIMIT 30
```

**查询2: Binder延迟分解**
```sql
INCLUDE PERFETTO MODULE android.binder;
INCLUDE PERFETTO MODULE android.binder_breakdown;

SELECT
  bb.binder_txn_id,               -- 关联的事务ID
  bb.binder_reply_id,             -- 关联的reply ID
  bb.ts,                          -- 延迟段开始时间
  bb.dur / 1000000.0,             -- 延迟段时长(ms)
  bb.server_reason,               -- 服务端延迟原因
  bb.client_reason,               -- 客户端延迟原因
  bb.reason,                      -- 通用原因描述
  bb.reason_type                  -- 原因类型
FROM android_binder_client_server_breakdown bb
JOIN android_binder_txns bt ON bt.binder_txn_id = bb.binder_txn_id
WHERE bb.dur > 1000000
ORDER BY bb.dur DESC
LIMIT 50
```

#### 输出字段

**collect_binder_txns:**

| 字段 | 类型 | 含义 |
|------|------|------|
| binder_txn_id | int | 事务唯一ID |
| client_ts_ns | int | 客户端发起时间(纳秒) |
| client_dur_ms | float | 客户端总耗时(毫秒) |
| server_dur_ms | float | 服务端处理耗时(毫秒) |
| aidl_name | str | AIDL接口名 |
| method_name | str | 方法名 |
| client_process/thread | str | 客户端进程/线程名 |
| server_process/thread | str | 服务端进程/线程名 |
| is_main_thread | bool | 是否主线程发起 |
| is_sync | bool | 是否同步调用 |

**collect_binder_breakdown:**

| 字段 | 类型 | 含义 |
|------|------|------|
| binder_txn_id | int | 关联事务ID |
| segment_dur_ms | float | 延迟段时长(毫秒) |
| server_reason | str | 服务端延迟原因 |
| client_reason | str | 客户端延迟原因 |
| reason | str | 通用原因描述 |
| reason_type | str | 原因类型 |

#### 注意事项
- 只关注同步Binder调用（`is_sync=TRUE`），异步调用被过滤
- `server_dur` 可能为 `None`（服务端可能不在同一trace中）
- `aidl_name` 需要trace中包含AIDL元数据
- 延迟分解中 `reason_type` 值包括：`notified`、`scheduled`、`running` 等

---

### P0-3: 启动分析增强 (android.startup.*)

- **文件**: `collector/startup.py`（新增方法）
- **方法**:
  - `collect_startup_metrics() -> list[dict]` — TTID/TTFD指标
  - `collect_startup_breakdown() -> list[dict]` — 启动瓶颈自动分解
- **Perfetto stdlib**:
  - `INCLUDE PERFETTO MODULE android.startup.time_to_display;`
  - `INCLUDE PERFETTO MODULE android.startup.startup_breakdowns;`
- **查询的表**:
  - `android_startup_time_to_display` — TTID/TTFD指标
  - `android_startup_opinionated_breakdown` — 启动瓶颈分解
- **解决的问题**: 标准化启动时间测量（TTID/TTFD），自动识别启动各阶段瓶颈
- **使用场景**: 冷启动优化、启动速度回归测试、启动阶段耗时对比

#### SQL查询详解

**查询1: TTID/TTFD 指标**
```sql
INCLUDE PERFETTO MODULE android.startup.time_to_display;

SELECT
  ttid.startup_id,                -- 启动事件ID
  ttid.ts,                        -- 启动开始时间
  ttid.ttid / 1000000.0,          -- Time To Initial Display(ms)
  ttid.ttfd / 1000000.0,          -- Time To Full Display(ms)
  ttid.package,                   -- 包名
  ttid.process_name               -- 进程名
FROM android_startup_time_to_display ttid
ORDER BY ttid.ts
```

**查询2: 启动瓶颈分解**
```sql
INCLUDE PERFETTO MODULE android.startup.startup_breakdowns;

SELECT
  sb.startup_id,                  -- 启动事件ID
  sb.ts,                          -- 时间戳
  sb.dur / 1000000.0,             -- 阶段耗时(ms)
  sb.subsystem,                   -- 子系统分类(binder/io/cpu/lock等)
  sb.name                         -- 阶段名称
FROM android_startup_opinionated_breakdown sb
ORDER BY sb.ts
```

#### 输出字段

**collect_startup_metrics:**

| 字段 | 类型 | 含义 |
|------|------|------|
| startup_id | int | 启动事件ID |
| ts | int | 启动开始时间 |
| ttid_ms | float | Time To Initial Display(首帧渲染时间) |
| ttfd_ms | float | Time To Full Display(完整内容显示时间) |
| package | str | 应用包名 |
| process_name | str | 进程名 |

**collect_startup_breakdown:**

| 字段 | 类型 | 含义 |
|------|------|------|
| startup_id | int | 关联启动事件ID |
| ts | int | 阶段开始时间 |
| dur_ms | float | 阶段耗时(毫秒) |
| subsystem | str | 子系统分类 |
| name | str | 阶段名称 |

#### 注意事项
- TTID/TTFD需要trace包含`android.startup`数据源（Android 12+自动采集）
- 瓶颈分解是"opinionated"的（有倾向性的），可能不完全准确
- 如果trace中没有启动事件，返回空列表

---

### P0-4: GC 分析 (android.garbage_collection)

- **文件**: `collector/gc.py`
- **类名**: `GcMixin`
- **方法**: `collect_garbage_collection() -> list[dict]`
- **Perfetto stdlib**: `INCLUDE PERFETTO MODULE android.garbage_collection;`
- **查询的表**: `android_garbage_collection_events`
- **解决的问题**: GC pause检测，分析GC期间的CPU时间分布（Running/Runnable/IO Wait），统计回收量
- **使用场景**: 帧率抖动排查、GC导致的卡顿定位、内存回收效率分析

#### SQL查询详解

```sql
INCLUDE PERFETTO MODULE android.garbage_collection;

SELECT
  gc.gc_ts,                       -- GC开始时间
  gc.gc_dur / 1000000.0,          -- GC总耗时(ms)
  gc.gc_running_dur / 1000000.0,  -- Running状态时长(ms)
  gc.gc_runnable_dur / 1000000.0, -- Runnable状态时长(ms)
  gc.gc_unint_io_dur / 1000000.0,-- IO Wait时长(ms)
  gc.gc_unint_non_io_dur / 1000000.0, -- 非IO Wait时长(ms)
  gc.gc_int_dur / 1000000.0,      -- 中断等待时长(ms)
  gc.gc_type,                     -- GC类型
  gc.is_mark_compact,             -- 是否为Mark-Compact
  gc.reclaimed_mb,                -- 回收内存(MB)
  gc.min_heap_mb,                 -- GC前最小堆(MB)
  gc.max_heap_mb,                 -- GC后最大堆(MB)
  gc.gc_id,                       -- GC事件ID
  gc.tid/pid/utid/upid,           -- 线程/进程信息
  gc.thread_name, gc.process_name
FROM android_garbage_collection_events gc
WHERE gc.gc_dur != -1
  AND gc.upid = (SELECT upid FROM process WHERE name GLOB '{pkg}')
ORDER BY gc.gc_dur DESC
LIMIT 20
```

#### 输出字段

| 字段 | 类型 | 含义 |
|------|------|------|
| gc_ts | int | GC开始时间 |
| gc_dur_ms | float | GC总耗时(毫秒) |
| running_ms | float | 实际Running时长(真正执行GC的时间) |
| runnable_ms | float | Runnable等待时长(准备运行但未获得CPU) |
| io_wait_ms | float | IO Wait时长(等待磁盘IO) |
| non_io_wait_ms | float | 非IO Wait时长(其他阻塞) |
| int_wait_ms | float | 中断等待时长 |
| gc_type | str | GC类型(如Alloc/Concurrent/External) |
| is_mark_compact | bool | 是否为Mark-Compact GC |
| reclaimed_mb | float | 回收的内存大小(MB) |
| min_heap_mb | float | GC前最小堆大小 |
| max_heap_mb | float | GC后最大堆大小 |

#### 注意事项
- GC类型 `Alloc` 表示因分配失败触发的同步GC，通常影响最大
- `running_ms` 低但 `runnable_ms` 高说明CPU调度压力大
- `reclaimed_mb` 为 `None` 表示trace中未采集回收量数据
- 需要 ART GC trace 数据源

---

### P0-5: ANR 分析 (android.anrs)

- **文件**: `collector/anr.py`
- **类名**: `AnrMixin`
- **方法**: `collect_anrs() -> list[dict]`
- **Perfetto stdlib**: `INCLUDE PERFETTO MODULE android.anrs;`
- **查询的表**: `android_anrs` + `slice` + `thread_track` + `thread`
- **解决的问题**: ANR事件检测，分析ANR期间主线程上最耗时的操作
- **使用场景**: ANR根因定位、ANR发生时的主线程行为分析

#### SQL查询详解

**查询1: ANR事件列表**
```sql
INCLUDE PERFETTO MODULE android.anrs;

SELECT
  a.process_name,                 -- 发生ANR的进程名
  a.pid, a.upid,                  -- 进程标识
  a.error_id,                     -- ANR唯一ID
  a.ts,                           -- ANR发生时间
  a.subject,                      -- ANR主题(Broadcast/Service/Input等)
  a.intent,                       -- 关联的Intent
  a.component,                    -- 关联的Component
  a.timer_delay,                  -- 定时器延迟
  a.anr_type,                     -- ANR类型
  a.anr_dur_ms,                   -- ANR持续时间(ms)
  a.default_anr_dur_ms            -- 默认ANR超时阈值(ms)
FROM android_anrs a
WHERE a.upid = (SELECT upid FROM process WHERE name GLOB '{pkg}')
ORDER BY a.ts
```

**查询2: ANR期间主线程Top 10切片**
```sql
WITH anr_windows(error_ts, anr_end_ts, error_id) AS (
  VALUES (ts1, ts1+dur1, 'id1'), (ts2, ts2+dur2, 'id2'), ...
),
main_thread AS (
  SELECT utid FROM thread WHERE upid = {upid} AND name = 'main' LIMIT 1
)
SELECT
  aw.error_id,
  s.name AS slice_name,           -- slice名称
  IIF(s.dur = -1, 0, s.dur) / 1000000.0 AS slice_dur_ms,
  s.ts AS slice_ts
FROM anr_windows aw
JOIN main_thread mt
JOIN thread_track tt ON tt.utid = mt.utid
JOIN slice s ON s.track_id = tt.id
WHERE s.ts >= aw.error_ts
  AND (s.ts + IIF(s.dur = -1, aw.anr_end_ts - s.ts, s.dur)) <= aw.anr_end_ts
ORDER BY aw.error_id, s.dur DESC
```

#### 输出字段

| 字段 | 类型 | 含义 |
|------|------|------|
| error_id | str | ANR唯一ID |
| process_name | str | 进程名 |
| ts_ns | int | ANR发生时间 |
| subject | str | ANR触发原因(如Broadcast/Service) |
| anr_type | str | ANR类型 |
| anr_dur_ms | float | ANR持续时间(毫秒) |
| default_anr_dur_ms | float | 系统默认ANR超时(通常5000ms) |
| main_thread_slices | list | 可选，ANR期间主线程Top 10切片 |

#### 注意事项
- ANR检测依赖 `android.anrs` 模块，需要Android系统提供ANR trace数据
- `anr_dur_ms` 可能比 `default_anr_dur_ms` 小（应用可能在超时前恢复）
- 主线程slice分析依赖ANR时间窗口定义，可能有边界误差

---

### P0-6: Slice CPU 时间增强 (slices.cpu_time + slices.time_in_state)

- **文件**: `collector/slice_enhanced.py`
- **类名**: `SliceEnhancedMixin`
- **方法**:
  - `collect_slice_cpu_time() -> list[dict]` — Slice实际CPU时间
  - `collect_slice_time_in_state() -> list[dict]` — Slice内线程状态分布
- **Perfetto stdlib**:
  - `INCLUDE PERFETTO MODULE slices.cpu_time;`
  - `INCLUDE PERFETTO MODULE slices.time_in_state;`
  - `INCLUDE PERFETTO MODULE sched.states;`
- **查询的表**:
  - `thread_slice_cpu_time` — Slice级CPU时间
  - `thread_slice_time_in_state` — Slice内线程状态
- **解决的问题**: 区分SI$ slice的wall time和实际CPU时间，分析slice等待CPU的时间分布
- **使用场景**: 准确评估方法实际执行成本，区分CPU密集和IO密集操作

#### SQL查询详解

**查询1: SI$ slice的实际CPU时间**
```sql
INCLUDE PERFETTO MODULE slices.cpu_time;

SELECT
  tsct.id,                        -- slice ID
  tsct.name,                      -- slice名称
  tsct.cpu_time / 1000000.0,      -- 实际CPU时间(ms)
  tsct.thread_name,               -- 线程名
  tsct.process_name,              -- 进程名
  s.dur / 1000000.0,              -- 总耗时(ms)
  ROUND(tsct.cpu_time * 100.0 / s.dur, 1) AS cpu_ratio  -- CPU占比(%)
FROM thread_slice_cpu_time tsct
JOIN slice s ON s.id = tsct.id
WHERE tsct.name GLOB 'SI$*'        -- 只看SI标记的slice
  AND tsct.cpu_time > 0
ORDER BY tsct.cpu_time DESC
LIMIT 20
```

**查询2: SI$ slice内的线程状态分布**
```sql
INCLUDE PERFETTO MODULE slices.time_in_state;
INCLUDE PERFETTO MODULE sched.states;

SELECT
  tsts.id,                        -- slice ID
  tsts.name,                      -- slice名称
  tsts.thread_name,
  tsts.process_name,
  sched_state_to_human_readable_string(tsts.state) AS state_name,  -- 可读状态名
  tsts.state,                     -- 原始状态值
  tsts.dur / 1000000.0,           -- 该状态持续时长(ms)
  tsts.io_wait,                   -- 是否为IO等待
  tsts.blocked_function           -- 阻塞函数名
FROM thread_slice_time_in_state tsts
WHERE tsts.name GLOB 'SI$*'
ORDER BY tsts.dur DESC
LIMIT 50
```

#### 输出字段

**collect_slice_cpu_time:**

| 字段 | 类型 | 含义 |
|------|------|------|
| slice_name | str | Slice名称(如SI$RV#1) |
| cpu_time_ms | float | 实际CPU时间(毫秒) |
| total_dur_ms | float | 总耗时(毫秒) |
| cpu_ratio | float | CPU时间占比(%) |
| thread_name | str | 线程名 |

**collect_slice_time_in_state:**

| 字段 | 类型 | 含义 |
|------|------|------|
| slice_name | str | Slice名称 |
| states | list | 线程状态列表，每项包含：state(状态名), dur_ms(时长), io_wait(是否IO), blocked_function(阻塞函数) |

#### 注意事项
- CPU占比可能超过100%（多核场景下）
- `blocked_function` 可能为空
- 只分析SI$标记的slice，其他slice不包含

---

## P1 场景增强模块

### P1-1: 逐帧指标 (android.frames.per_frame_metrics)

- **文件**: `collector/frame.py`（新增方法）
- **方法**: `collect_frame_metrics() -> list[dict]`
- **Perfetto stdlib**: `INCLUDE PERFETTO MODULE android.frames.per_frame_metrics;`
- **查询的表**: `android_frame_stats`
- **解决的问题**: 获取每帧的精确指标——overrun、CPU time、UI time、vsync delay、jank分级
- **使用场景**: 帧率问题精细分析、jank严重程度分级

#### 输出字段

| 字段 | 类型 | 含义 |
|------|------|------|
| frame_id | int | 帧ID |
| overrun_ms | float | 超出预算的时间(>16.6ms的部分) |
| cpu_time_ms | float | 帧渲染CPU时间 |
| ui_time_ms | float | UI线程时间 |
| was_jank | bool | 是否为jank帧 |
| was_slow_frame | bool | 是否为慢帧 |
| was_big_jank | bool | 是否为大jank帧 |
| was_huge_jank | bool | 是否为巨大jank帧 |
| app_vsync_delay_ms | float | App侧vsync延迟 |

#### 注意事项
- 需要 Android 12+ 的帧指标数据源
- `was_jank/was_slow_frame/was_big_jank/was_huge_jank` 是互斥的分级

---

### P1-2: 输入延迟分解 (android.input)

- **文件**: `collector/input.py`
- **类名**: `InputMixin`
- **方法**: `collect_input_latency() -> list[dict]`
- **Perfetto stdlib**: `INCLUDE PERFETTO MODULE android.input;`
- **查询的表**: `android_input_events`
- **解决的问题**: 将输入事件延迟分解为dispatch、handling、ACK三个阶段
- **使用场景**: 触摸响应慢的排查、输入事件流水线分析

#### 输出字段

| 字段 | 类型 | 含义 |
|------|------|------|
| dispatch_ms | float | InputDispatcher分发耗时 |
| handling_ms | float | 应用处理耗时 |
| ack_ms | float | ACK确认耗时 |
| total_ms | float | 总延迟(dispatch+handling+ack) |
| e2e_ms | float | 端到端延迟 |
| event_type | str | 事件类型(如KEY/MOTION) |
| event_action | str | 事件动作(如ACTION_DOWN) |
| thread_name | str | 处理线程名 |
| event_seq | int | 事件序列号 |

#### 注意事项
- `total_ms = dispatch_ms + handling_ms + ack_ms`
- `e2e_ms` 可能比 `total_ms` 更大（包含额外的系统层延迟）
- 需要开启input trace数据源

---

### P1-3: 调度延迟 (sched.latency)

- **文件**: `collector/sched_latency.py`
- **类名**: `SchedLatencyMixin`
- **方法**: `collect_sched_latency() -> list[dict]`
- **Perfetto stdlib**: `INCLUDE PERFETTO MODULE sched.latency;`
- **查询的表**: `sched_latency_for_running_interval`
- **解决的问题**: 分析线程从Runnable到Running的调度等待时间
- **使用场景**: CPU调度压力大、线程饥饿、优先级反转分析

#### 输出字段

| 字段 | 类型 | 含义 |
|------|------|------|
| thread_name | str | 线程名 |
| wait_count | int | 调度等待次数 |
| total_wait_ms | float | 总等待时间(毫秒) |
| avg_wait_ms | float | 平均等待时间(毫秒) |
| max_wait_ms | float | 最大单次等待时间(毫秒) |
| min_wait_ms | float | 最小单次等待时间(毫秒) |

#### 注意事项
- 按 `total_wait_ms` 排序，返回Top 20线程
- 高 `max_wait_ms` 值表示存在单次长时间调度饥饿

---

### P1-4: OOM + RSS/Swap (android.memory.process + android.memory.lmk)

- **文件**: `collector/oom.py`
- **类名**: `OomMixin`
- **方法**: `collect_oom_rss_swap() -> dict`
- **Perfetto stdlib**:
  - `INCLUDE PERFETTO MODULE android.memory.process;`
  - `INCLUDE PERFETTO MODULE android.memory.lmk;`
- **查询的表**:
  - `memory_oom_score_with_rss_and_swap_per_process`
  - `android_lmk_events`
- **解决的问题**: 追踪OOM adj分数变化与内存使用关联，检测LMK杀进程事件
- **使用场景**: 内存压力分析、后台进程被杀排查、OOM adj变化原因

#### 输出字段

**oom_transitions (OOM分数时间线):**

| 字段 | 类型 | 含义 |
|------|------|------|
| ts | int | 时间戳 |
| oom_score | int | OOM adj分数 |
| oom_bucket | str | OOM桶分类 |
| rss_mb | float | 总RSS(MB) |
| anon_rss_mb | float | 匿名RSS(MB) |
| swap_mb | float | Swap使用(MB) |
| oom_adj_reason | str | 调整原因 |
| oom_adj_trigger | str | 触发来源 |

**lmk_events (LMK杀进程事件):**

| 字段 | 类型 | 含义 |
|------|------|------|
| ts | int | 杀进程时间 |
| process_name | str | 被杀进程名 |
| oom_score_adj | int | 被杀时的adj分数 |
| kill_reason | str | 杀进程原因 |

#### 注意事项
- 返回dict包含两个key：`oom_transitions` 和 `lmk_events`
- LMK事件不区分进程，返回trace中所有LMK事件

---

### P1-5: 精确CPU利用率 (linux.cpu.utilization)

- **文件**: `collector/cpu_utilization.py`
- **类名**: `CpuUtilizationMixin`
- **方法**:
  - `collect_process_cpu_utilization() -> list[dict]` — 进程级CPU利用率
  - `collect_thread_cpu_utilization() -> list[dict]` — 线程级CPU利用率
- **Perfetto stdlib**:
  - `INCLUDE PERFETTO MODULE linux.cpu.utilization.process;`
  - `INCLUDE PERFETTO MODULE linux.cpu.utilization.thread;`
- **查询的表**:
  - `cpu_cycles_per_process` / `cpu_process_utilization_per_second()`
  - `cpu_cycles_per_thread` / `cpu_thread_utilization_per_second()`
- **解决的问题**: 频率加权的精确CPU利用率（非简单wall time占比）
- **使用场景**: 准确的CPU使用分析、大小核利用率、功耗评估

#### 输出字段

**collect_process_cpu_utilization:**

| 字段 | 类型 | 含义 |
|------|------|------|
| ts | int | 时间戳 |
| utilization | float | 频率加权CPU利用率(0.0~1.0) |
| megacycles | float | 总CPU周期数(百万) |
| runtime_ms | float | 总运行时间(毫秒) |
| min/max/avg_freq_khz | float | 频率范围(kHz) |

**collect_thread_cpu_utilization:**

| 字段 | 类型 | 含义 |
|------|------|------|
| thread_name | str | 线程名 |
| megacycles | float | CPU周期数 |
| runtime_ms | float | 运行时间 |
| per_second | list | 可选，每秒利用率序列 |

#### 注意事项
- `utilization` 是频率加权的，考虑了大小核差异
- 线程级分析返回Top 15线程（按megacycles排序）
- 需要 `linux.cpu.freq` trace数据源

---

### P1-6: 堆分析增强 (android.memory.heap_graph.*)

- **文件**: `collector/memory.py`（新增方法）
- **方法**:
  - `collect_heap_graph_stats() -> list[dict]` — 堆统计摘要
  - `collect_heap_class_aggregation() -> list[dict]` — 按类聚合
  - `collect_heap_dominator_tree() -> list[dict]` — 支配树
- **Perfetto stdlib**:
  - `INCLUDE PERFETTO MODULE android.memory.heap_graph.heap_graph_stats;`
  - `INCLUDE PERFETTO MODULE android.memory.heap_graph.heap_graph_class_aggregation;`
  - `INCLUDE PERFETTO MODULE android.memory.heap_graph.dominator_tree;`
- **查询的表**:
  - `android_heap_graph_stats`
  - `android_heap_graph_class_aggregation`
  - `heap_graph_dominator_tree`
- **解决的问题**: Java堆高级分析——统计摘要、按类聚合的内存占用、支配树找retained size最大的对象
- **使用场景**: 内存泄漏分析、大对象定位、内存占用热点类排查

#### 输出字段

**collect_heap_graph_stats:** 堆统计摘要（对象总数、总大小等）

**collect_heap_class_aggregation:**

| 字段 | 类型 | 含义 |
|------|------|------|
| class_name | str | Java类名 |
| object_count | int | 对象数量 |
| self_size | int | 自身大小(bytes) |
| total_size | int | 含引用的总大小(bytes) |

**collect_heap_dominator_tree:**

| 字段 | 类型 | 含义 |
|------|------|------|
| class_name | str | 类名 |
| retained_size | int | Retained大小(bytes) |
| shallow_size | int | Shallow大小(bytes) |
| depth | int | 支配树深度 |

#### 注意事项
- 需要在trace中采集Java heap dump
- 支配树查询可能很慢（大堆上）
- `retained_size` 表示该对象被GC后能释放的最大内存

---

### P1-7: SurfaceFlinger 帧匹配 (android.surfaceflinger)

- **文件**: `collector/surfaceflinger.py`
- **类名**: `SurfaceFlingerMixin`
- **方法**: `collect_surfaceflinger_timeline() -> list[dict]`
- **Perfetto stdlib**: `INCLUDE PERFETTO MODULE android.surfaceflinger;`
- **查询的表**: `android_app_to_sf_frame_timeline_match` + `actual/expected_frame_timeline_slice`
- **解决的问题**: 关联App帧和SurfaceFlinger帧的时间线，检测渲染管线延迟
- **使用场景**: 显示延迟分析、App-SF帧对应关系、渲染流水线瓶颈

#### 输出字段

| 字段 | 类型 | 含义 |
|------|------|------|
| app_vsync_id | int | App侧vsync ID |
| sf_vsync_id | int | SF侧vsync ID |
| app_dur_ms | float | App帧渲染耗时 |
| sf_dur_ms | float | SF合成耗时 |
| app_expected_dur_ms | float | App帧预算(vsync间隔) |
| sf_expected_dur_ms | float | SF帧预算 |
| match_type | str | 帧类型(on_time/late/unknown) |

#### 注意事项
- 需要 SurfaceFlinger trace 数据
- `match_type` 通过比较实际耗时和预期预算自动判断
- 返回Top 200帧匹配记录
- `app_vsync_id` 和 `sf_vsync_id` 用于关联App和SF的帧

---

## 附录：Perfetto SQL 最佳实践

基于 SKILL.md 提炼的查询规范，所有模块已遵循：

1. **GLOB替代LIKE** — 所有字符串匹配使用 `GLOB`，避免 `LIKE` 的性能问题和 `_` 通配符bug
2. **dur=-1处理** — 使用 `!= -1` 过滤或 `IIF(dur=-1, ...)` 处理未完成事件
3. **utid/upid** — 使用唯一标识符而非tid/pid进行表关联
4. **列名前缀** — 所有列名带表别名（如 `mc.id`, `bt.client_dur`）
5. **GLOB匹配包名** — 使用 `name GLOB '{pkg}'` 精确匹配进程名
6. **错误处理** — 每个查询都有 try/except，失败返回空列表/dict并记录日志