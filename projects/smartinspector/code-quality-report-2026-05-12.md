# SmartInspector Collector Module Code Quality Report

**Date**: 2026-05-12
**Scope**: `src/smartinspector/collector/` (14 files)
**Focus**: SQL query efficiency, error handling, edge case coverage

---

## 1. Module Overview

| File | Lines | Role |
|------|-------|------|
| `base.py` | 139 | ABC + PerfSummary dataclass + DeviceInfo |
| `registry.py` | 151 | Platform factory with thread-safe registry |
| `perfetto.py` | 1022 | Core class, summarize(), pull_trace_from_device(), helpers |
| `_helpers.py` | 42 | Shared utility functions |
| `sched.py` | 66 | Scheduling data (hot threads, blocked reasons) |
| `cpu.py` | 177 | CPU hotspots (flame graph) + CPU usage |
| `frame.py` | 415 | Frame timeline + view slices + compose slices |
| `io.py` | 97 | IO slices + input events |
| `block.py` | 105 | Block events with logcat stack trace correlation |
| `thread.py` | 247 | Thread state (Running/Sleeping/DiskSleep) per slice |
| `sys.py` | 83 | System stats (CPU idle, freq, fork rate) |
| `memory.py` | 206 | Heap graph analysis + memory trend |
| `startup.py` | 480 | Cold start phase analysis |
| `__init__.py` | 13 | Package re-exports |

**Total**: ~2,843 lines of Python code.

---

## 2. SQL Query Efficiency Analysis

### 2.1 Critical Issues (P0)

#### 2.1.1 SQL Injection via f-string Interpolation

**Severity**: HIGH (Security + Correctness)
**Files**: `perfetto.py`, `thread.py`, `frame.py`, `startup.py`

Multiple queries use f-strings to embed user-provided or dynamically-computed values directly into SQL:

```python
# perfetto.py:113-118 — _resolve_target_process()
rows = tp.query(f"""
    SELECT upid, pid, uid
    FROM process
    WHERE name = '{package_name}'   -- <== f-string injection
    LIMIT 1
""")
```

```python
# thread.py:135
rows = tp.query(f"SELECT utid FROM thread WHERE name = '{self._target_package}' LIMIT 1")
```

```python
# thread.py:52-65 — collect_thread_state()
state_rows = tp.query(f"""
    SELECT state, SUM(dur) AS total_ns, ...
    FROM __intrinsic_thread_state
    WHERE utid = {main_utid}
      AND ts < {slice_end}
      AND ts + dur > {slice_ts}
    ...
""")
```

While Perfetto's `trace_processor_shell` is a local process (not a remote DB server), a malicious trace file could theoretically contain process names with SQL-breaking characters. More practically, a package name containing a single quote (e.g., `O'Brien's App`) would cause a syntax error or unexpected behavior.

**Instances**: 15+ f-string interpolated queries across the codebase.

**Recommendation**: Use parameterized queries if Perfetto's Python API supports them, or at minimum sanitize/escape inputs before interpolation.

#### 2.1.2 N+1 Query Pattern in `collect_thread_state()`

**Severity**: HIGH (Performance)
**File**: `thread.py:42-120`

For each of the top 20 SI$ slices, a **separate SQL query** is issued to `__intrinsic_thread_state`. If the intrinsic table is available, this means up to 20 individual queries, each with its own overhead:

```python
for sr in slice_rows:          # up to 20 iterations
    state_rows = tp.query(f"""  # 20 separate queries
        SELECT state, SUM(dur) AS total_ns, ...
        FROM __intrinsic_thread_state
        WHERE utid = {main_utid}
          AND ts < {slice_end}
          AND ts + dur > {slice_ts}
        GROUP BY state, blocked_function, io_wait, waker_utid
    """)
```

Additionally, each non-Running state triggers yet another query to resolve `waker_name` (thread.py:100-106), potentially adding 20 more queries.

**Impact**: Up to **40 sequential IPC calls** to trace_processor_shell for thread state alone.

**Recommendation**: Batch all slice time ranges into a single query using a CTE or UNION ALL, or pre-load all thread_state data for the main utid in one query and filter in Python.

#### 2.1.3 N+1 Query Pattern in `_walk_call_chain()`

**Severity**: MEDIUM (Performance)
**File**: `perfetto.py:992-1021`

Each call to `_walk_call_chain()` issues one SQL query per ancestor (up to 20 levels deep). For 10 slices, this could be up to **200 sequential queries**:

```python
for _ in range(20):
    rows = list(tp.query(f"""
        SELECT id, name, ts, dur, depth, parent_id
        FROM slice WHERE id = {current_id}
    """))
```

**Recommendation**: Pre-load the slice table's parent-chain columns in a single query, or use a recursive CTE:
```sql
WITH RECURSIVE chain AS (
    SELECT id, name, dur, depth, parent_id FROM slice WHERE id = ?
    UNION ALL
    SELECT s.id, s.name, s.dur, s.depth, s.parent_id
    FROM slice s JOIN chain c ON s.id = c.parent_id
)
SELECT * FROM chain LIMIT 20;
```

#### 2.1.4 Full Table Scans in `collect_view_slices()`

**Severity**: MEDIUM (Performance)
**File**: `frame.py:98-120`

The main view slices query uses 8 `LIKE` patterns with no index exploitation:

```sql
WHERE (name LIKE 'SI$%'
       AND name NOT LIKE 'SI$net#%'
       AND name NOT LIKE 'SI$db#%'
       AND name NOT LIKE 'SI$img#%'
       AND name NOT LIKE 'SI$touch#%')
   OR name LIKE '%doFrame%'
   OR name LIKE '%Choreographer%'
   OR name LIKE '%Traversal%'
   OR name LIKE '%performDraw%'
   OR name LIKE '%performMeasure%'
   OR name LIKE '%performLayout%'
```

Leading `%` wildcards (`%doFrame%`) force full table scans. On large traces with millions of slices, this is expensive.

**Recommendation**: Perfetto's trace processor does not support traditional SQL indexes, but consider:
- Using `GLOB` instead of `LIKE` where applicable (Perfetto supports it)
- Reducing the OR conditions by collecting SI$ slices and system slices separately
- Adding a `LIMIT` to cap results

### 2.2 Moderate Issues (P1)

#### 2.2.1 Unbounded `collect_sys_stats()` Queries

**File**: `sys.py:17-70`

All three queries in `collect_sys_stats()` have no `LIMIT` clause:

```python
# CPU idle samples — could return millions of rows
cpu_rows = tp.query("""
    SELECT c.ts, c.value AS cpu_util
    FROM counter c
    JOIN cpu_counter_track cct ON c.track_id = cct.id
    WHERE cct.name = 'cpuidle_time'
    ORDER BY c.ts ASC
""")
```

Counter tables can have millions of rows for long traces. Each sample is returned as a dict and held in memory.

**Impact**: Memory pressure on long traces (10s+ trace with 1000Hz sampling = 10,000+ rows per core).

**Recommendation**: Downsample in SQL (`WHERE ROW_NUMBER() % 100 = 0`) or add a `LIMIT`.

#### 2.2.2 Unbounded `collect_threads()` Query

**File**: `sys.py:77`

```python
rows = tp.query("SELECT tid, name FROM thread ORDER BY tid")
```

No `LIMIT`, no `WHERE` clause. Returns all threads from all processes in the trace. On Android, this can be 500+ threads.

**Recommendation**: Filter by target process, or at least add a `LIMIT`.

#### 2.2.3 Redundant TraceProcessor Instantiation in `startup.py`

**File**: `startup.py:143-147, 188-189, 371-373`

`StartupAnalyzer` creates new `PerfettoCollector` instances in three methods just to call `_resolve_target_process()`:

```python
def _find_startup_timestamps(self, tp):
    collector = PerfettoCollector(self.trace_path, target_process=self.target_process)
    target_info = collector._resolve_target_process(self.target_process)
```

Each `PerfettoCollector()` instantiation creates a separate `TraceProcessor` connection (since `_open()` is lazy but not shared).

**Impact**: 3 extra trace_processor_shell processes spawned for startup analysis.

**Recommendation**: Pass the existing `PerfettoCollector` instance or reuse the `tp` object.

#### 2.2.4 Two-Phase Query for CPU Hotspots

**File**: `cpu.py:13-48`

`collect_cpu_hotspots()` first queries top 20 hotspots, then queries the **entire** `stack_profile_callsite` table to build a callsite map:

```python
# Query 1: top 20 hotspots
rows = tp.query("... GROUP BY spf.name, t.name, ps.callsite_id ORDER BY sample_count DESC LIMIT 20")

# Query 2: ALL callsites (no limit)
cs_rows = tp.query("""
    SELECT spc.id, spf.name, spc.parent_id
    FROM stack_profile_callsite spc
    JOIN stack_profile_frame spf ON spc.frame_id = spf.id
""")
```

The second query loads the entire callsite graph into Python memory. For traces with deep call stacks, this can be thousands of rows.

**Recommendation**: Only load callsites reachable from the top 20 hotspots by walking up the parent chain.

### 2.3 Minor Issues (P2)

#### 2.3.1 `GROUP_CONCAT` Parsing Fragility

**File**: `frame.py:35, 56`

```python
"GROUP_CONCAT(DISTINCT jank_type) AS jank_types"
# ...
all_jank = [j.strip() for j in (r.jank_types or "").split(",")
            if j.strip() and j.strip() != "None"]
```

`GROUP_CONCAT` output is fragile: if a jank_type itself contains a comma (unlikely but possible in future Android versions), the parsing would break.

#### 2.3.2 Window Function Overhead in `collect_cpu_hotspots()`

**File**: `cpu.py:19`

```sql
SUM(COUNT(*)) OVER () AS total_samples
```

The window function `SUM(COUNT(*)) OVER ()` is computed for every group, even though it's the same value. A separate scalar subquery or CTE would be cleaner and potentially faster:

```sql
WITH stats AS (SELECT COUNT(*) AS total_samples FROM perf_sample WHERE callsite_id IS NOT NULL)
SELECT ..., stats.total_samples FROM stats, ...
```

---

## 3. Error Handling Analysis

### 3.1 Strengths

1. **Systematic try/except in `summarize()`** (`perfetto.py:306-440`): Each `collect_*` call is wrapped individually, so one failure does not prevent other collections. Errors are stored in the result as `{"error": str(e)}`, allowing downstream analysis to continue.

2. **Three-tier trace collection fallback** (`perfetto.py:596-738`): `pull_trace_from_device()` tries three strategies:
   - Strategy 1: Config via stdin pipe
   - Strategy 2: SELinux fallback (push config file + cat pipe)
   - Strategy 3: Auto-degradation to command-line mode

3. **Intrinsic thread state fallback** (`thread.py:35-39`): Falls back to legacy `thread_state` table if `__intrinsic_thread_state` is unavailable.

4. **Per-query error handling in `collect_sys_stats()`**: Each of the three sub-queries (CPU idle, freq, fork rate) has independent error handling, so one table missing doesn't block the others.

5. **`_diagnose_tables()` helper** (`perfetto.py:200-222`): Proactively checks table availability and adds diagnostic notes to metadata, helping users understand missing data.

### 3.2 Issues

#### 3.2.1 Bare `except Exception` Suppresses All Errors Silently

**Severity**: MEDIUM
**Files**: Nearly all mixin modules

Every query is wrapped in `except Exception as e:` with only `debug_log()`. While this prevents crashes, it makes debugging difficult:

- `sched.py:12`: `collect_sched()` has **no try/except** on the main query — any SQL error propagates uncaught
- `frame.py:98-163`: `collect_view_slices()` returns `{}` on error, losing context about what went wrong
- `cpu.py:87-97`: `collect_cpu_usage()` returns `{}` silently if trace_bounds fails

**Recommendation**: Use `info_log()` for unexpected errors (not just `debug_log()`), so failures are visible without SI_DEBUG=1.

#### 3.2.2 `collect_sched()` Has No Error Handling on Main Query

**Severity**: HIGH
**File**: `sched.py:12-24`

```python
def collect_sched(self) -> dict:
    tp = self._open()
    rows = tp.query("""...""")  # <== no try/except!
    hot_threads = []
    for r in rows:
        ...
```

If this query fails (e.g., `sched` table doesn't exist), the exception propagates up to `summarize()` which catches it, but the `blocked_reasons` sub-query within the same method **is** wrapped in try/except. This inconsistency means a missing `sched` table breaks the entire method, while a missing `sched_blocked_reason` table is silently handled.

**Recommendation**: Wrap the main query in try/except, consistent with the blocked_reasons sub-query.

#### 3.2.3 `collect_threads()` Has No Error Handling

**Severity**: LOW
**File**: `sys.py:77-82`

```python
def collect_threads(self) -> list[dict]:
    tp = self._open()
    rows = tp.query("SELECT tid, name FROM thread ORDER BY tid")  # no try/except
    threads = []
    ...
```

**Recommendation**: Add try/except consistent with other methods.

#### 3.2.4 `_resolve_main_utid()` Strategy 2 Uses f-string Without Sanitization

**Severity**: MEDIUM
**File**: `thread.py:133-138`

```python
rows = tp.query(f"SELECT utid FROM thread WHERE name = '{self._target_package}' LIMIT 1")
```

If `_target_package` contains a single quote, this query will fail. Strategy 1 and 3 are safer (hardcoded 'main' or upid-based).

#### 3.2.5 Resource Leak in `StartupAnalyzer._open_tp()`

**Severity**: MEDIUM
**File**: `startup.py:143-147`

```python
def _open_tp(self):
    collector = PerfettoCollector(self.trace_path, target_process=self.target_process)
    return collector._open()
```

The `PerfettoCollector` instance is created but never `close()`d. The `tp` returned from `_open()` references the collector's `_tp` field, but since the collector itself is not stored, it's never cleaned up. This leaves the trace_processor_shell process orphaned.

#### 3.2.6 `pull_trace_from_device` Doesn't Clean Up on `adb pull` Failure

**Severity**: LOW
**File**: `perfetto.py:743-754`

```python
# Pull trace from device
subprocess.run(
    ["adb", "pull", device_path, output_path],
    check=True, capture_output=True, text=True,
)
# Cleanup device
subprocess.run(["adb", "shell", "rm", device_path], ...)
```

If `adb pull` fails, the `rm` cleanup never runs, leaving the trace file on the device. A `finally` block would be safer.

---

## 4. Edge Case Coverage Analysis

### 4.1 Well-Handled Edge Cases

| Edge Case | Location | Handling |
|-----------|----------|----------|
| Empty trace / missing tables | `summarize()`, `_diagnose_tables()` | Returns empty results with diagnostic notes |
| No target process specified | `_resolve_target_process()` | Returns `{}`, most collectors degrade gracefully |
| Missing `__intrinsic_thread_state` | `thread.py:161-167` | Falls back to legacy `thread_state` table |
| `dur = 0` or `dur = -1` | `frame.py:38`, `thread.py:196` | `WHERE dur > 0` filters, `MIN()` handles negative dur |
| Empty frame data | `frame.py:68-69` | Returns `{"total_frames": 0}` |
| No SI$ slices in trace | `block.py:53`, `frame.py:183` | Returns `[]` or `{}` early |
| Trace file doesn't exist | `_open()` | Perfetto library raises descriptive error |
| No main thread found | `thread.py:158` | Returns `None`, caller returns `[]` |
| SELinux blocking perfetto | `perfetto.py:686-713` | Three-tier fallback |

### 4.2 Unhandled Edge Cases

#### 4.2.1 Division by Zero

**Severity**: MEDIUM
**Files**: `cpu.py:51`, `frame.py:79`, `thread.py:92`, `startup.py:316`

```python
# cpu.py:51 — total_samples could be 0 if all callsite_id are NULL
pct = round(r.sample_count / r.total_samples * 100, 1) if r.total_samples else 0
# ^ This IS guarded, but other places aren't:
```

```python
# startup.py:316
"pct": dur_ms / total_ms * 100 if total_ms > 0 else 0,
# ^ total_ms is checked, but dur_ms is not checked for being negative
```

```python
# thread.py:92 — total_ns could be 0 if all state rows have dur=0
pct = round(r.total_ns / total_ns * 100, 1)
# ^ NOT guarded if total_ns is 0
```

**Specific Risk in `thread.py:84`**: `total_ns` is computed as `sum(r.total_ns for r in state_entries)`. If all rows have `total_ns = 0` or `None`, `total_ns = 0` and the division on line 92 raises `ZeroDivisionError`.

#### 4.2.2 Negative `dur` Values

**Severity**: LOW
**Files**: Multiple

Perfetto uses `dur = -1` for "still running" slices. While `thread.py:196` handles this with `CASE WHEN dur < 0`, other locations don't:

```python
# cpu.py:145 — total_dur_ns could be -1
dur_ns = r.total_dur_ns or 0  # "or 0" doesn't catch -1
```

```python
# frame.py:55, 168 — assumes dur > 0
dur_ms = round(r.frame_dur_ns / 1e6, 2)  # negative dur → negative ms
```

#### 4.2.3 Very Large Traces (OOM Risk)

**Severity**: MEDIUM
**Files**: `sys.py`, `frame.py`, `io.py`

No protection against loading millions of rows into memory:
- `collect_sys_stats()`: All CPU counter samples loaded into Python lists
- `collect_view_slices()`: All matching slices loaded (could be 100K+ on long traces)
- `collect_io_slices()`: No LIMIT on IO slice query

#### 4.2.4 Timestamp Overflow/Underflow

**Severity**: LOW
**Files**: `frame.py:78`, `startup.py:283`

```python
# frame.py:78 — ts_ns could overflow Python int? No, Python has arbitrary precision.
# But float conversion could lose precision:
total_s = (frames[-1]["ts_ns"] - frames[0]["ts_ns"]) / 1e9
```

Perfetto timestamps are nanoseconds (int64). Python's `float` has ~15 digits of precision, but nanosecond timestamps can be 18+ digits. Division by 1e9 loses some precision in float conversion.

#### 4.2.5 `collect_thread_state()` With No SI$ Slices

**Severity**: LOW
**File**: `thread.py:10-30`

If no SI$ slices match the filter (`dur > 1000000`), `slice_rows` is empty and the method returns `[]`. This is correct, but there's no diagnostic logging to explain *why* it's empty (unlike the empty `thread_state` table diagnosis in `summarize()`).

#### 4.2.6 `block.py` Timestamp Correlation: Only Checks 2 Candidates

**Severity**: LOW
**File**: `block.py:89-94`

```python
for candidate_idx in (idx - 1, idx):
```

Only checks the two closest log entries by bisect position. If the closest match is at `idx + 1` (the log entry is slightly after the block), it will be missed. This is a correctness edge case when log timestamps are not perfectly ordered.

#### 4.2.7 `startup.py` Creates Multiple `PerfettoCollector` Instances

**Severity**: MEDIUM
**File**: `startup.py:145-147, 189, 372`

`_find_startup_timestamps()` and `_extract_critical_path()` each create a new `PerfettoCollector`, which in turn creates new `TraceProcessor` connections. These are never closed, leaking trace_processor_shell processes.

---

## 5. Code Quality Summary

### 5.1 Strengths

1. **Clean architecture**: Mixin-based separation of concerns is well-executed. Each domain (sched, cpu, frame, io, block, thread, sys) has its own file.
2. **Graceful degradation**: The collector rarely crashes — most failures return empty results and log diagnostics.
3. **Diagnostic tooling**: `_diagnose_tables()` and the table_stats metadata help users understand missing data.
4. **Consistent patterns**: All mixin methods follow the same `tp = self._open()` → query → process → return pattern.
5. **Good documentation**: CLAUDE.md is comprehensive and well-maintained.

### 5.2 Top 10 Issues (Priority Order)

| # | Severity | File:Line | Issue |
|---|----------|-----------|-------|
| 1 | P0 | `perfetto.py`, `thread.py`, `frame.py`, `startup.py` | SQL injection via f-string interpolation (15+ instances) |
| 2 | P0 | `thread.py:42-120` | N+1 query pattern: up to 40 sequential queries per thread_state collection |
| 3 | P0 | `perfetto.py:992-1021` | N+1 query pattern: up to 200 queries in `_walk_call_chain()` |
| 4 | P1 | `sys.py:17-70` | Unbounded counter queries — OOM risk on long traces |
| 5 | P1 | `startup.py:143-147` | Resource leak: PerfettoCollector/TraceProcessor never closed |
| 6 | P1 | `sched.py:12` | Main query has no try/except — inconsistent with sub-queries |
| 7 | P1 | `thread.py:92` | Potential ZeroDivisionError when total_ns = 0 |
| 8 | P1 | `frame.py:98-120` | Full table scan with 8 LIKE patterns, no LIMIT |
| 9 | P2 | `perfetto.py:743-754` | Device trace cleanup skipped if `adb pull` fails |
| 10 | P2 | `cpu.py:145` | `total_dur_ns` could be -1, `or 0` doesn't catch negative values |

### 5.3 Metrics

| Metric | Value |
|--------|-------|
| Total f-string SQL queries | 25+ |
| Queries with LIMIT | 14 / 25+ |
| Queries with try/except | 18 / 25+ |
| Unbounded queries (no LIMIT) | 6 |
| Resource leak risk points | 3 |
| ZeroDivisionError risk points | 3 |
| Files with consistent error handling | 9 / 10 |
| Average cyclomatic complexity per method | Low-Medium (well-structured) |
| Test coverage (estimated from structure) | Partial — summarize() integration tests exist |

---

## 6. Recommendations

### Short-term (P0 fixes)

1. **Parameterize SQL queries** or add input sanitization for `package_name` and other user-provided values
2. **Batch thread_state queries** — load all thread_state data for main_utid in one query, filter by slice time ranges in Python
3. **Replace `_walk_call_chain()` N+1 pattern** with a single recursive CTE or pre-loaded parent map

### Medium-term (P1 fixes)

4. Add `LIMIT` clauses to all counter/slice queries, or downsample in SQL
5. Fix resource leaks in `StartupAnalyzer` — reuse a single `PerfettoCollector` instance
6. Add try/except to `collect_sched()` main query
7. Guard against `ZeroDivisionError` in `thread.py:92`

### Long-term (P2 improvements)

8. Add `finally` block for device trace cleanup in `pull_trace_from_device()`
9. Handle negative `dur` values consistently across all collectors
10. Add memory budget checks — reject processing traces that would exceed reasonable memory limits
11. Consider adding query-level timeouts to prevent hangs on pathological traces
