# Hermes Agent 源码分析

> 基于 v0.11.0 源码的深度技术分析

## 1. Memory 系统

### 1.1 MemoryStore 实现

**文件**: `tools/memory_tool.py`

```python
class MemoryStore:
    def __init__(self, memory_char_limit: int = 2200, user_char_limit: int = 1375):
        self.memory_entries: List[str] = []
        self.user_entries: List[str] = []
        self.memory_char_limit = memory_char_limit
        self.user_char_limit = user_char_limit
        # 冻结快照 — session 启动时设置，会话中不变
        self._system_prompt_snapshot: Dict[str, str] = {"memory": "", "user": ""}
```

**关键设计**：
- 双状态机制：`_system_prompt_snapshot`（冻结）+ `entries`（实时）
- 字符限制而非 token 限制（模型无关）
- 条目分隔符：`\n§\n`（section sign）
- 文件锁：Unix 用 `fcntl.flock`，Windows 用 `msvcrt.locking`

**容量管理**：
- `add()`: 检查总字符数是否超限，超限返回错误并提示 replace/remove
- `replace()`: 子串匹配，多匹配时要求更精确的 old_text
- `remove()`: 同上，多匹配时报错
- 去重：`list(dict.fromkeys(entries))` 保持顺序去重

**原子写入**：
```python
fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp", prefix=".mem_")
with os.fdopen(fd, "w", encoding="utf-8") as f:
    f.write(content)
    f.flush()
    os.fsync(f.fileno())
os.replace(tmp_path, str(path))  # 同文件系统原子替换
```

### 1.2 安全扫描机制

**文件**: `tools/memory_tool.py` 第 45-78 行

```python
_MEMORY_THREAT_PATTERNS = [
    # Prompt 注入
    (r'ignore\s+(previous|all|above|prior)\s+instructions', "prompt_injection"),
    (r'you\s+are\s+now\s+', "role_hijack"),
    (r'do\s+not\s+tell\s+the\s+user', "deception_hide"),
    (r'system\s+prompt\s+override', "sys_prompt_override"),
    # 数据外泄
    (r'curl\s+[^\n]*\$\{?\w*(KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|API)', "exfil_curl"),
    (r'wget\s+[^\n]*\$\{?\w*(KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|API)', "exfil_wget"),
    (r'cat\s+[^\n]*(\.env|credentials|\.netrc|\.pgpass|\.npmrc|\.pypirc)', "read_secrets"),
    # 持久化后门
    (r'authorized_keys', "ssh_backdoor"),
    (r'\$HOME/\.ssh|\~/\.ssh', "ssh_access"),
    (r'\$HOME/\.hermes/\.env|\~/\.hermes/\.env', "hermes_env"),
]
```

还检查不可见 Unicode 字符（零宽字符等 10 种）：
```python
_INVISIBLE_CHARS = {
    '\u200b', '\u200c', '\u200d', '\u2060', '\ufeff',
    '\u202a', '\u202b', '\u202c', '\u202d', '\u202e',
}
```

### 1.3 MEMORY_SCHEMA（行为引导 Prompt）

**文件**: `tools/memory_tool.py` 第 515-575 行

Memory tool 的 schema description 本身就是行为引导：

```
WHEN TO SAVE (do this proactively, don't wait to be asked):
- User corrects you or says 'remember this' / 'don't do that again'
- User shares a preference, habit, or personal detail
- You discover something about the environment
- You learn a convention, API quirk, or workflow

PRIORITY: User preferences and corrections > environment facts > procedural knowledge

TWO TARGETS:
- 'user': who the user is
- 'memory': your notes

SKIP: trivial/obvious info, things easily re-discovered, raw data dumps, temporary TODO state
```

## 2. Skill 系统

### 2.1 skill_manage 工具 Schema

**文件**: `tools/skill_manager_tool.py` 第 725-810 行

```python
SKILL_MANAGE_SCHEMA = {
    "name": "skill_manage",
    "parameters": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["create", "patch", "edit", "delete", "write_file", "remove_file"]},
            "name": {"type": "string", "description": "Skill name (lowercase, hyphens/underscores, max 64 chars)"},
            "content": {"type": "string", "description": "Full SKILL.md content (YAML frontmatter + markdown body)"},
            "old_string": {"type": "string", "description": "Text to find in the file (required for 'patch')"},
            "new_string": {"type": "string", "description": "Replacement text (required for 'patch')"},
            "replace_all": {"type": "boolean"},
            "category": {"type": "string"},
            "file_path": {"type": "string"},
            "file_content": {"type": "string"},
        },
        "required": ["action", "name"],
    },
}
```

行为引导（description 中）：
- **Create when**: complex task succeeded (5+ calls), errors overcome, user-corrected approach worked
- **Update when**: instructions stale/wrong, OS-specific failures, missing steps found during use
- **Good skills**: trigger conditions, numbered steps with exact commands, pitfalls section, verification steps

### 2.2 _security_scan_skill

**文件**: `tools/skill_manager_tool.py` 第 72-110 行

```python
def _security_scan_skill(skill_dir: Path) -> Optional[str]:
    if not _GUARD_AVAILABLE:
        return None
    if not _guard_agent_created_enabled():
        return None  # 默认关闭！
    result = scan_skill(skill_dir, source="agent-created")
    allowed, reason = should_allow_install(result)
    if allowed is False:
        return f"Security scan blocked this skill ({reason}):\n{report}"
```

**注意**：默认关闭（`guard_agent_created` 默认 False），因为 Agent 已经可以通过 terminal() 执行任意代码，扫描只是增加摩擦。

### 2.3 fuzzy_find_and_replace

**文件**: `tools/fuzzy_match.py` 第 50-120 行

9 级模糊匹配策略链：

```python
strategies = [
    ("exact", _strategy_exact),
    ("line_trimmed", _strategy_line_trimmed),
    ("whitespace_normalized", _strategy_whitespace_normalized),
    ("indentation_flexible", _strategy_indentation_flexible),
    ("escape_normalized", _strategy_escape_normalized),
    ("trimmed_boundary", _strategy_trimmed_boundary),
    ("unicode_normalized", _strategy_unicode_normalized),
    ("block_anchor", _strategy_block_anchor),
    ("context_aware", _strategy_context_aware),
]
```

还有 **escape-drift 防护**：当使用非 exact 策略匹配时，检测 `\'` 或 `\"` 是否是工具调用序列化引入的假象，防止写入损坏的代码。

## 3. Nudge Engine

### 3.1 计数器机制

**文件**: `run_agent.py`

```python
# 初始化 (第 1429-1538 行)
self._memory_nudge_interval = 10       # 每 10 个 user turns
self._memory_flush_min_turns = 6
self._turns_since_memory = 0
self._iters_since_skill = 0            # 每 10 次工具迭代
self._skill_nudge_interval = 10
```

**Memory Nudge 触发**（第 8771-8779 行）：
```python
if (self._memory_nudge_interval > 0
        and "memory" in self.valid_tool_names
        and self._memory_store):
    self._turns_since_memory += 1
    if self._turns_since_memory >= self._memory_nudge_interval:
        _should_review_memory = True
        self._turns_since_memory = 0
```

**Skill Nudge 触发**（第 11891-11892 行）：
```python
if (self._skill_nudge_interval > 0
        and self._iters_since_skill >= self._skill_nudge_interval
        and "skill_manage" in self.valid_tool_names):
    _should_review_skills = True
    self._iters_since_skill = 0
```

### 3.2 _spawn_background_review

**文件**: `run_agent.py` 第 2879-2960 行

```python
def _spawn_background_review(self, messages_snapshot, review_memory=False, review_skills=False):
    import threading
    # 选择 prompt
    if review_memory and review_skills:
        prompt = self._COMBINED_REVIEW_PROMPT
    elif review_memory:
        prompt = self._MEMORY_REVIEW_PROMPT
    else:
        prompt = self._SKILL_REVIEW_PROMPT

    def _run_review():
        # Fork 一个完整的 AIAgent
        review_agent = AIAgent(model=self.model, max_iterations=8, quiet_mode=True, ...)
        # 共享 MemoryStore
        review_agent._memory_store = self._memory_store
        # 禁用嵌套 nudge
        review_agent._memory_nudge_interval = 0
        review_agent._skill_nudge_interval = 0
        # 重定向 stdout/stderr 到 /dev/null
        review_agent.run_conversation(user_message=prompt, conversation_history=messages_snapshot)
        # 扫描 review agent 的 tool 调用结果，生成摘要
        ...

    t = threading.Thread(target=_run_review, daemon=True, name="bg-review")
    t.start()
```

**关键点**：
- 在后台线程运行，不阻塞用户对话
- Fork 完整 AIAgent，有独立模型调用
- 共享 MemoryStore（可直接写入记忆/技能）
- 禁用嵌套 nudge（防止无限递归）
- max_iterations=8（限制审查开销）
- 完成后输出简洁摘要

### 3.3 Review Prompts

**文件**: `run_agent.py` 第 2844-2878 行

**Memory Review Prompt**：
```
Review the conversation above and consider saving to memory if appropriate.
Focus on:
1. Has the user revealed things about themselves — their persona, desires,
   preferences, or personal details worth remembering?
2. Has the user expressed expectations about how you should behave, their work
   style, or ways they want you to operate?
If something stands out, save it using the memory tool.
If nothing is worth saving, just say 'Nothing to save.' and stop.
```

**Skill Review Prompt**：
```
Review the conversation above and consider saving or updating a skill if appropriate.
Focus on: was a non-trivial approach used to complete a task that required trial
and error, or changing course due to experiential findings along the way?
If a relevant skill already exists, update it with what you learned.
Otherwise, create a new skill if the approach is reusable.
```

## 4. 整体数据流

```
用户消息 → Gateway (platform adapter)
    → AIAgent.run_conversation()
        → System Prompt (冻结快照 + skills + tools schema)
        → LLM API 调用
        → 工具执行循环
            → memory/skill_manage → MemoryStore/Skill 文件
            → terminal/browser/... → 外部系统
        → 返回响应
        → Nudge 检查 → _spawn_background_review()
            → Fork AIAgent (后台线程)
                → 独立 LLM 调用
                → 写入 Memory/Skill
            → 输出 💾 摘要
    → 平台适配器发送响应
```
