# Hermes × OpenClaw 个人成长控制台设计

> 日期：2026-07-19
>
> 状态：用户已确认设计
>
> 目标：一次性完成可自动运行、可从任意浏览器安全访问、可通过钉钉查询与告警、可受控修改任务的个人机会发现系统。

## 1. 背景与目标

现有系统已经具备以下基础：

- OpenClaw 负责知识采集、知识库任务、钉钉入口和系统 Cron。
- Hermes `0.18.2` 使用 `opportunity-discovery` Profile，主模型为 OpenCode Go，DeepSeek API 为 fallback。
- Opportunity OS 已有机会、方向组合、技术新鲜度、Review、快照和审计事件模型。
- 知识库通过唯一同步脚本发布到 GitHub Pages。

本次不是再增加一个独立 Agent，而是建设统一控制面：

1. 实时查看 OpenClaw、Hermes、Opportunity OS、知识库和外网隧道状态。
2. 从网页与钉钉查询系统、与 OpenClaw/Hermes 会话、查看完整报告。
3. 受控创建、修改、启停和立即执行任务。
4. 自动完成每日轻扫描、每周完整分析、知识库脱敏输出和推送。
5. 为 Hermes 补齐监控、失败告警、自恢复和可审计的自我提升入口。
6. 保持广域技术信息采集，避免因个人方向形成信息茧房。

## 2. 设计原则

- **OpenClaw 是唯一生产调度器和钉钉出口**：Hermes 不启用自己的 Cron 或 messaging。
- **Hermes 是深度分析器**：按需运行会话，维护私有 Opportunity OS，不成为常驻网关。
- **浏览器不直接连接 Gateway**：所有访问经本机 Dashboard Broker，浏览器永不接触 Gateway Token 或 API Key。
- **私有与公开分层**：完整机会、实验、个人偏好和会话只保留在本机；知识库与 GitHub Pages 只接收脱敏报告。
- **默认拒绝写入**：任务、Memory、Skill 和策略变更先生成结构化 Diff，再审批、应用、验证；失败自动回滚。
- **新鲜但不躁动**：持续发现新技术，同时用多源验证、反证和 Stable gates 控制不可靠信号。
- **不制造信息茧房**：广域采集不少于 80%，定向补充不超过 20%，每次分析保留反证和 surprise bucket。
- **可观测性不得伪精确**：没有可靠公式时显示最近时间、延迟和状态，不展示虚构的“新鲜度 92 分”或“费用为 0”。

## 3. 当前基线与必须修复的问题

只读审计确认以下状态：

- OpenClaw Gateway 已由 LaunchAgent 以 `RunAtLoad + KeepAlive` 管理，只监听 loopback；普通 Shell 的 Node PATH 可能命中 Node 18，而 OpenClaw 需要 Node 22.12 以上，所有 Wrapper 必须固定 PATH。
- OpenClaw 有 42 个 Cron，25 个启用、17 个停用；启用任务最近为 19 个成功、6 个失败。
- 当前没有真正的 Hermes daily/weekly 生产任务。
- 钉钉插件已经启用，但 `dmPolicy=open`、缺少 owner allowlist，群聊策略也过宽。
- 钉钉投递队列存在 7 条 pending、245 条 failed；多数为 HTTP 400，不能把“任务成功”当作“消息送达”。
- 现有健康脚本没有可靠的时间窗、锁、滞回、去重和重启冷却，并尝试调用不存在的独立 `dingtalk` CLI。
- Gateway 主日志约 351 MB、错误日志约 9 MB；需要轮转与保留策略，不能删除故障证据。
- 每日提炼任务内部同步与 22:30 独立同步形成双同步；周日 Lint 与每日提炼同刻运行。
- `sync_kb.sh` 缺少严格失败传播，可能在 build、push 或 deploy 失败后仍显示成功，也可能暂存无关改动。
- Opportunity OS 的现有 `system_status()` 会嵌入完整方向数据，不可直接作为仪表盘公开 DTO。
- Hermes 的 `state.db` 中存在未终结记录，但不能据此判断真实运行进程；必须使用心跳和进程探针。
- Hermes 当前 `memory_enabled=true`、`user_profile_enabled=false`，Memory/Skill 写审批开启；默认 nudge 仍可能触发后台 Review，费用与写入需显式控制。

这些问题属于本次交付范围，因为它们直接影响仪表盘状态真实性、自动化可靠性和远程控制安全性。

## 4. 总体架构

```text
任意浏览器
   │ HTTPS + GitHub OAuth allowlist
   ▼
ngrok Edge（固定免费开发域名）
   │ OAuth 后注入 origin credential
   ▼
Dashboard Broker（仅 127.0.0.1）
   ├── Read Model / SSE Event Hub
   ├── OpenClaw Adapter
   ├── Hermes Session Adapter
   ├── Opportunity OS Read Repository
   ├── Task + Approval Controller
   ├── Runtime Probes + Incident Sentinel
   ├── Sanitizer + Report Exporter
   └── Append-only Audit
         │
         ├── OpenClaw Gateway / Cron / 钉钉
         ├── 固定 Hermes Wrapper / Profile
         ├── Opportunity OS 私有状态
         └── Knowledge Base / GitHub Pages
```

### 4.1 进程与自动启动

- 复用现有 OpenClaw Gateway LaunchAgent。
- 新增 Dashboard Broker LaunchAgent，使用 `RunAtLoad + KeepAlive`。
- 新增 ngrok Agent LaunchAgent，仅把固定外网端点转发至 Dashboard loopback 端口。
- Hermes 不常驻；由 OpenClaw Cron 或 Dashboard 按需调用固定 Wrapper。
- Dashboard 进程由 `launchd` 拉起，OpenClaw 另设低频健康任务监控 Dashboard；OpenClaw 完全退出时由其 LaunchAgent 拉起。

### 4.2 组件边界

| 组件 | 职责 | 依赖 | 禁止事项 |
|---|---|---|---|
| `PrivateStateReadRepository` | 纯只读机会、实验、TechState、Review、事件查询 | Opportunity OS 文件 | 初始化/touch 文件、返回秘密或完整路径 |
| `DashboardReadModel` | 聚合稳定 DTO、状态和新鲜度 | 只读 Repository、Probes | 透传 `system_status()` |
| `RuntimeProbe` | 探测 OpenClaw、Hermes、Dashboard、ngrok、任务心跳 | 固定命令、短超时 | 触发模型调用或修改状态 |
| `ConversationRouter` | 路由 OpenClaw 与 Hermes 会话、流式输出 | 两个 Adapter | 向浏览器暴露 Token |
| `TaskController` | 任务预览、审批、应用、验证、回滚 | OpenClaw CLI/Gateway Adapter | 直接写 `jobs.json`、任意 Shell |
| `ApprovalService` | Digest、ETag、TTL、nonce、状态机 | 私有审批存储 | 批准后替换 Payload |
| `IncidentSentinel` | 告警去重、冷却、恢复通知、重启上限 | Probes、OpenClaw 钉钉 | 删除日志、无限重启 |
| `Sanitizer` | 私有数据分级、内容扫描、脱敏导出 | 明确 allowlist | 仅按字段名判断 Secret |
| `AuditLog` | 记录 actor、request-id、字段 Diff、结果 | Append-only 文件 | 记录 Token、收件人、完整会话正文 |

## 5. 外网访问与认证

首阶段采用 ngrok 免费方案：

- 使用账户自动分配的固定 `*.ngrok-free.app` 开发域名。
- ngrok Edge 强制 GitHub OAuth，并显式 allowlist 唯一 owner 账号。
- Dashboard 只监听 `127.0.0.1`/`::1`，不开放局域网或公网端口。
- ngrok 在 OAuth 成功后注入高熵 origin credential；Broker 校验 credential、Host、Origin 和 GitHub 身份，再签发短期 HttpOnly Session Cookie。
- Mutation 仅接受 JSON，关闭 CORS，禁止 GET 修改，使用 CSRF Token、`SameSite=Strict` Cookie 和 5 分钟确认 nonce。
- 私有响应使用 `Cache-Control: no-store`，错误只返回固定错误码和 trace ID。
- 免费额度不可用或无法可靠读取时显示 `unknown` 和 ngrok 控制台链接，不伪造剩余额度。
- 采用 SSE 长连接传输状态和任务事件，避免高频浏览器轮询消耗 20,000 请求/月额度。

ngrok 免费方案的已知约束：1 GB/月、20,000 HTTP 请求/月、最多 3 个 OAuth/OIDC 月活身份、访问提示页和无生产 SLA。超出阈值或稳定性不足时，再迁移到自有域名 + Cloudflare Tunnel + Access；Dashboard 内部接口不因隧道供应商改变。

本机应急访问不绕过安全控制。CLI `dashboard open` 生成 60 秒一次性 loopback bootstrap token，换取本机 HttpOnly Session；远程和本机会话共享相同的写操作审批规则。

实施到 ngrok Authtoken 时必须暂停，由用户在可见终端输入。任何 Token 不进入命令输出、Git、日志或对话。

## 6. 仪表盘信息架构

### 6.1 总览

- OpenClaw、Hermes、Opportunity OS、Dashboard、ngrok、知识库发布六张状态卡。
- 状态只允许 `healthy / degraded / down / unknown`，同时显示最近探测和最近成功时间。
- 机会/实验/Review 数量、observe/validate/active 容量、最近新信号和到期复核数。
- 最新机会变化、待审批变更、最近事故、下一任务和最新报告入口。

### 6.2 实时会话

- `OpenClaw 助手`：知识库查询、系统任务查询和日常操作。
- `Hermes 研究员`：机会发现、深度分析、方向复盘和继续历史 Session。
- 会话输出流式显示，可将结论转为任务或长期需求草案。
- 模型调用前展示 Profile、Provider、数据范围、允许工具和可用时的费用估计；费用未知时明确显示 unknown。

### 6.3 信号与新鲜度

- 最新信号时间线、类别、来源等级和采集状态。
- `known_latest` 与 `recommended_stable` 分栏。
- 到期 TechState 只标记“需复核”，不自动判定失效。
- 显示五项 Stable gate、正反证据和 surprise bucket。
- 广域采集占比不得低于 80%，定向采集不得高于 20%。定向反馈只能增加检索，不能减少广域来源。

### 6.4 机会与实验

- 机会列表按现有确定性评分排序，支持状态、类型和展示桶过滤。
- 详情包含七维评分、Fact/Inference/Hypothesis、正反证据、失效条件和最小实验。
- observe/validate/active 三列组合，容量默认 `5/2/1`，允许 active 为 0。
- 实验展示 1–14 天周期、指标、继续/停止条件和证据。

### 6.5 任务与调度

- 展示任务状态、Cron、时区、下一执行、最近结果和运行历史。
- V1 可应用字段：`enabled`、Cron 表达式、时区、run-now。
- V1 禁止网页修改 Payload、命令、模型、收件人或直接删除任务。
- 复杂自然语言需求先转成结构化草案；超出 allowlist 的部分只生成操作建议，不自动应用。

### 6.6 审批中心

- 统一管理任务变更、长期偏好、Memory、Skill、自我提升建议和策略变更。
- 展示当前值、目标值、影响范围、下一运行时间、模型/费用影响、快照和回滚方案。
- 支持批准、拒绝、过期、验证失败和回滚记录。

### 6.7 报告

- 本机查看完整私有 daily/weekly/six-week/quarterly 报告。
- 查看知识库脱敏版、GitHub Pages 发布状态和最后成功部署时间。
- GitHub Pages 始终只读，不承载控制接口或私有运行状态。

### 6.8 监控与审计

- 运行探针、任务心跳、钉钉投递、事故状态、重启计数和日志轮转状态。
- 显示版本与模板漂移，但不自动升级 OpenClaw、Hermes 或 ngrok。
- 路径映射为 `profile://`、`kb://`，URL 删除 userinfo、query 和 fragment。

## 7. 实时数据流

- Runtime Probe 在服务端每 10 秒运行短超时只读检查；失败一次先标 `unknown`，连续失败才进入 degraded/down。
- 数据计数和新鲜度每 30 秒重算，文件系统事件经过 debounce，并每 60 秒做一次 reconciliation。
- Opportunity OS 的 `events.jsonl` 由 Event Tailer 顺序读取；SSE 只发送 `{event_id,type,entity_id,at}`，正文由受权 API 单独拉取。
- SSE 支持 `Last-Event-ID` 重连、半行 JSON、文件轮转和重复事件去重。
- GET 请求不得调用会 `initialize()` 或 `touch()` 的 MCP `_store()`，确保读取无副作用。

## 8. 任务修改与审批模型

统一状态机：

```text
draft → previewed → awaiting_approval → approved → applying
      → verified → applied
      → failed → rolled_back
```

每个 Change Request 至少包含：

- `kind`、`target`、标准化 Patch、数据等级。
- `base_revision`/ETag、Payload Digest、有效期和一次性 nonce。
- 影响范围、下一执行时间、模型/费用影响、副作用和回滚点。
- actor、request-id、创建/批准/应用/验证时间。

安全规则：

- 审批绑定完整 Patch Digest，批准后内容变化必须重新审批。
- 应用前 compare-and-swap；目标已变化则拒绝覆盖。
- 单写者锁串行修改；应用后 read-after-write 验证。
- 任务删除不在 V1；先停用并保留旧定义。
- 任何任意 Shell、任意路径、密钥、收件人和模型修改都不进入通用网页控制接口。

### 8.1 Hermes 需求层级

| 层级 | 落点 | 审批与回滚 |
|---|---|---|
| 临时需求 | 单次 Dashboard 任务或 Hermes Session | 只读任务可直接运行；写状态/模型调用先预览；取消即丢弃未提交草案 |
| 长期偏好 | `USER.md` | 逐条审批，下一新 Session 验证；按唯一文本移除或恢复快照 |
| Memory | Pending Memory | 保持 `write_approval=true`；批准前做内容与威胁扫描 |
| Skill | Profile 私有 Skill | 永远 Stage，独立 Diff、扫描和测试；一次只应用一个 Skill |
| 调度 | OpenClaw Cron | 修改频率/时区/启停均二次确认；先 disable、不删除 |
| 评分/容量 | 版本化策略代码 | 最高等级审批，全量 Dry-run、测试和快照；增加 `scoring_policy_version` |

## 9. Hermes 自我提升策略

系统启用 `user_profile_enabled`，但分阶段控制自动 Review：

1. 首先显式设置 `memory.nudge_interval=0` 和 `skills.creation_nudge_interval=0`，保持 Memory/Skill 写审批、Skill guard 和 `profile_build=off`。
2. 用户在仪表盘批准少量 USER 条目；默认只显示条目数量，正文需单独展开。
3. 生产 Cron 使用非交互 Wrapper 时不触发 Memory/Skill 自改；分析改进只写入 `improvement proposal` 草案。
4. 完成费用审计、每日上限和回滚验证后，才在受监督 Canary Session 中恢复 Memory Review；输出仍进入 Pending。
5. 紧急停用时将两个 nudge 设为 0、关闭 user_profile、拒绝 Pending；删除数据需要另行审批。

这样可以利用 Hermes 的学习能力，又避免非交互 `-z` 运行绕过审批后直接改变 Memory 或 Skill。

## 10. OpenClaw、Hermes 与知识库自动节奏

建议统一时序：

| 时间 | 任务 |
|---|---|
| 08:00–13:00 | 保留现有技术、论文、GitHub 与社交信号广域采集 |
| 18:30 | Hermes daily；周日跳过 |
| 周日 19:00 | Hermes weekly 完整复盘 |
| 周日 20:30 | Knowledge Base Lint |
| 21:00 | 晚间摘要；仅重大变化即时推送 |
| 22:00 | 每日知识提炼，不再内嵌同步 |
| 22:30 | 唯一一次 `sync_kb.sh` |
| 22:45 | 仅在 build、push、Pages deploy 全部成功后推送结果与链接 |
| 23:00 | Token/调用统计；费用未知时不估算 |

Hermes Wrapper 只接受固定枚举：`daily / weekly / biweekly / six-week / quarterly`，包含：

- 固定 Profile、Skill、PATH、工作目录和数据边界。
- 原子锁、周期幂等键、run-id、start/end/status/error-class/duration 心跳。
- daily 内层约 20 分钟、外层 25 分钟；weekly 内层约 45 分钟、外层 50 分钟。
- 不启用 terminal、file、browser、delegation、cronjob 或 messaging。
- 不使用 Hermes Cron，不让 Hermes 修改 OpenClaw 配置。

## 11. 报告输出与反哺 OpenClaw

### 11.1 私有输出

完整机会、方向、实验、Review、USER/MEMORY、来源选择与详细日志保留在：

- `profile://opportunity-os/`
- `profile://bridge/`

### 11.2 知识库输出

通过 Sanitizer 生成：

- `wiki/syntheses/个人机会发现仪表盘.md`
- `wiki/syntheses/个人机会发现周报-YYYY-MM-DD.md`
- `wiki/syntheses/技术新鲜度观察.md`
- `wiki/syntheses/方向实验复盘-YYYY-Www.md`

新 Wiki 页面必须符合知识库模板、自评不低于 7.0、更新对应 `index.md` 和 `log.md`。`raw/` 永远只读。发布只能调用既有 `sync_kb.sh`，不得手动复制、Git push 或运行 MkDocs deploy。

### 11.3 反哺 OpenClaw

私有 Bridge 文件保存 14 天 TTL：

- `openclaw-handoff.json`
- `source-feedback.json`
- `experiment-evidence-request.json`

OpenClaw 可据此增加定向搜索，但不能删除或减少广域来源。Bridge 不允许直接修改 OpenClaw Cron、Provider、密钥或安全配置。

## 12. 监控、告警与自恢复

### 12.1 告警等级

- P0：隐私泄漏风险、控制面未授权访问、核心服务不可用——立即钉钉。
- P1：任务失败、报告严重逾期、发布失败——首次进入 FIRING 时钉钉。
- P2：短暂超时、单来源异常——自动重试，连续失败后升级。
- P3：普通变化——只进入仪表盘和摘要。

### 12.2 Incident 状态机

- Key 为 `source + task + error_class`。
- 连续 2–3 次失败才进入 FIRING；P0 和 KB 发布失败可首次告警。
- 相同事故 4–6 小时内去重；恢复连续成功 2 次后只发一次 RECOVERED。
- Gateway 重启最多 1 次/小时、2 次/天；超限后停止自动重启并标记需要人工处理。
- 日志只轮转和按保留期清理，不在故障处理中直接删除。
- OpenClaw 完全退出时无法通过自身钉钉实时通知；由 LaunchAgent 恢复，启动 Hook 补发“曾中断并已恢复”。

### 12.3 钉钉安全与可靠性

- `dmPolicy=allowlist`，只允许唯一 owner。
- 群聊默认 `disabled`；如后续启用，必须显式限定群 ID 和 sender。
- `contextVisibility=allowlist_quote`。
- 任务变更采用两阶段确认：同一 sender/session 在 5 分钟内返回精确 nonce。
- 启用任务级 Failure Alert；不使用会抑制失败告警的 `bestEffort`。
- 修复 HTTP 400 根因并完成一次主动推送验收，不能只检查 Queue 写入。

## 13. 知识库同步可靠性修复

`sync_kb.sh` 需要保持为唯一发布入口，但内部改为：

- 使用单实例锁和严格阶段退出码。
- build、Git push、Pages deploy 任一失败即停止，不输出成功。
- 只暂存本任务拥有的路径，不使用会包含用户无关改动的宽泛提交。
- 不自动覆盖用户修改的 `mkdocs.yml`，检测到漂移时失败并报告。
- 不修改全局 Git 代理。
- 按 `AGENTS.md` 同步声明的根文件，并验证 `docs/raw/`、索引和链接。
- 生成机器可读结果供 Dashboard 和钉钉使用。

## 14. 安全与隐私分级

| 等级 | 示例 | 处理 |
|---|---|---|
| Secret | `.env`、`auth.json`、API/OAuth Token、Cookie、Authorization、带凭据 URL | Broker 原则上不读正文；只检查存在性/权限；永不进入 UI/日志/Git |
| Local Private | 机会标题、实验、个人评分、USER/MEMORY、会话、任务原文、详细日志 | OAuth + App Session 后按需显示；`no-store`；不公开导出 |
| Public Safe | 软件版本、粗粒度健康布尔、策略版本、聚合计数、脱敏报告 | Sanitizer allowlist 后可进入知识库 |

内容级扫描必须覆盖自由文本和 URL query；不能只依赖有限的敏感字段名。公开 ID 使用导出盐散列，文件路径隐藏用户名，错误正文映射为错误码和 trace ID。

## 15. 错误处理与降级

- Probe 超时首先显示 unknown，避免把沙箱或短暂网络问题误报为 down。
- OpenClaw 不可用时，Hermes 私有只读数据和 Dashboard 诊断仍可查看；写操作禁用。
- Hermes 不可用时，OpenClaw 任务与知识库状态仍可管理；Hermes 任务进入可重试失败态。
- ngrok 不可用时，loopback 应急入口可用；外网写操作不可降级为匿名访问。
- 钉钉不可用时告警进入持久队列，恢复后补发；Dashboard 始终显示 delivery 状态。
- GitHub Pages 发布失败时保留本地脱敏报告并显示“未发布”，不得宣称同步成功。
- 任何自动回滚失败都进入 P0/P1，停止后续同类写操作。

## 16. 测试与验收

### 16.1 单元测试

- Read Repository 无初始化副作用、路径逃逸和私有字段泄漏。
- DTO allowlist、内容级 Secret 扫描、URL/路径脱敏。
- Freshness、容量、评分版本和反信息茧房约束。
- Approval TTL、Digest、ETag/CAS、重复 nonce、回滚。
- Incident 去重、冷却、恢复和重启上限。
- Event Tailer 的断点续传、半行、轮转、重复事件和 reconciliation。

### 16.2 集成测试

- 使用临时 Hermes Home、临时 Opportunity OS 和 Fake OpenClaw Adapter，不接触真实 Profile 或知识库。
- OpenClaw CLI 使用固定 Node PATH；验证 list/status/runs/edit/enable/disable/run 契约。
- Hermes Wrapper 验证超时、非零退出、锁冲突、重复周期和心跳。
- 同步脚本注入 build/push/deploy 失败，确认不会假成功或提交无关改动。

### 16.3 安全测试

- 非 allowlist GitHub 用户、恶意 Host/Origin、CSRF、GET mutation、过期/重复 nonce 全部拒绝。
- HTML、网络响应、浏览器存储、日志和审计不含 Gateway Token、API Key、收件人或完整 Payload。
- owner DM 可用，非 owner 和群聊被拒绝。
- 仪表盘 GET 不产生文件写入。

### 16.4 端到端验收

1. 本机与外部网络浏览器均能通过 GitHub OAuth 登录。
2. OpenClaw/Hermes/Opportunity OS/KB/ngrok 状态与宿主机实测一致。
3. 修改 Cron 或启停任务会显示 Diff、审批、应用和验证结果。
4. Hermes daily/weekly 能幂等运行并生成私有报告、脱敏 Wiki 和推送。
5. 注入 Hermes、OpenClaw、钉钉、同步和 ngrok 故障，告警只发一次，恢复只发一次。
6. 主动钉钉消息实际送达，历史 HTTP 400 根因已修复或明确隔离。
7. 重启 Mac 后 OpenClaw、Dashboard、ngrok 自动启动，Cron 和恢复通知正常。
8. Git 工作区中用户原有脏文件保持不变。

## 17. 实施顺序与停顿点

实施在同一计划内连续完成：

1. 测试基线、纯只读 Repository 与隐私 Sanitizer。
2. Dashboard API、SSE、UI 和本机会话。
3. Task/Approval/审计与 OpenClaw/Hermes Adapter。
4. Hermes Wrapper、自动节奏、报告与 Bridge。
5. 钉钉安全、Failure Alert、Incident Sentinel 和同步可靠性。
6. ngrok GitHub OAuth、LaunchAgent 和外网验证。
7. 故障注入、重启验收、文档和状态查看说明。

仅在以下情况暂停要求用户输入：

- ngrok 登录或 Authtoken。
- 确认 GitHub owner 身份。
- 钉钉 owner allowlist 无法从现有可信会话安全解析。
- 需要付费、创建新外部账号或扩大授权范围。

所有 Secret 必须由用户在可见终端或官方浏览器页面输入，不在隐藏终端、聊天消息或日志中粘贴。

## 18. 非目标

- 不匿名公开 Dashboard。
- 不把控制面放入 GitHub Pages。
- 不启用 Hermes messaging 或 Hermes Cron。
- 不提供任意 Shell、任意文件编辑或任务删除。
- 不自动升级 OpenClaw、Hermes、ngrok 或模型。
- 不将 SmartInspector 设为机会发现主轴，也不预设唯一发展方向。
- 不使用 Cloudflare Quick Tunnel 或 Tailscale Funnel。
- 不在首阶段制作 Electron/Tauri 桌面壳。

## 19. 外部依据

- [ngrok 免费版限制](https://ngrok.com/docs/pricing-limits/free-plan-limits)
- [ngrok OAuth Traffic Policy](https://ngrok.com/docs/traffic-policy/examples/oauth-protection)
- [Cloudflare Quick Tunnel 限制](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/do-more-with-tunnels/trycloudflare/)
- [Cloudflare 私有 Web 应用](https://developers.cloudflare.com/cloudflare-one/setup/secure-private-apps/private-web-app/)
- [Tailscale Serve 与 Funnel](https://tailscale.com/docs/features/tailscale-funnel/how-to/host-websites)
