# Hermes Opportunity Discovery OS

这是 Hermes 私有 Profile 的确定性后端：把 OpenClaw 已采集的广域技术信号转化为机会卡、低成本实验、方向组合、周期复盘与技术新鲜度状态。

## 边界

```text
OpenClaw（唯一生产调度与采集）
  → knowledge/raw/inbox（只读）
  → Opportunity OS MCP（校验与持久化）
  → ~/.hermes/profiles/opportunity-discovery/opportunity-os（私人）
  → Hermes opportunity-discovery Skill（分析与交互）
```

- 本目录只保存无秘密的代码、测试、Skill 和 Profile 模板。
- 个人机会、实验、方向、求职反馈与复盘只保存在 Hermes 私有目录。
- 不修改 OpenClaw，不安装 Hermes Cron，不写 `raw/` 或 `wiki/`。
- OpenCode Go 为常态模型，DeepSeek 官方 API 为服务错误、限额或鉴权故障的 fallback。

## 安装后路径

- Profile：`/Users/liujun/.hermes/profiles/opportunity-discovery`
- 私人状态：`/Users/liujun/.hermes/profiles/opportunity-discovery/opportunity-os`
- Skill：`/Users/liujun/.hermes/profiles/opportunity-discovery/skills/productivity/opportunity-discovery`
- 密钥：`/Users/liujun/.hermes/profiles/opportunity-discovery/.env`，权限 `0600`

## 本地开发

```bash
UV_CACHE_DIR=/private/tmp/hermes-uv-cache uv run --extra test pytest -q
UV_CACHE_DIR=/private/tmp/hermes-uv-cache uv run opportunity-os --help
UV_CACHE_DIR=/private/tmp/hermes-uv-cache uv run python -c "import mcp_server; print(mcp_server.mcp.name)"
```

## 私人状态初始化与检查

```bash
uv run --directory "/Users/liujun/Nutstore Files/我的坚果云/knowledge/integrations/hermes-opportunity-os" \
  opportunity-os init \
  --home "/Users/liujun/.hermes/profiles/opportunity-discovery/opportunity-os" \
  --knowledge-root "/Users/liujun/Nutstore Files/我的坚果云/knowledge"

uv run --directory "/Users/liujun/Nutstore Files/我的坚果云/knowledge/integrations/hermes-opportunity-os" \
  opportunity-os doctor \
  --home "/Users/liujun/.hermes/profiles/opportunity-discovery/opportunity-os" \
  --knowledge-root "/Users/liujun/Nutstore Files/我的坚果云/knowledge" \
  --format json
```

## 使用节奏

运行时始终显式加载专用 Skill：

```bash
hermes -p opportunity-discovery chat --skills opportunity-discovery
```

建议提示：

- 每日：`执行每日机会扫描：读取最近 3 天广域信号，保留至少一项意外发现，区分最新信号和稳定建议。`
- 每周：`执行每周机会发现：保存 3–5 张机会卡、方向组合与一个最小实验，不要对外行动。`
- 每两周：`复盘当前验证实验，记录支持和反对证据，并决定继续、调整或停止。`
- 每六周：`执行方向组合复盘，最多 5 个观察、2 个验证、1 个主动方向，允许没有主动方向。`
- 每季度：`执行假设清零复核、来源效果审查和 Stable 基线审查。`

这些提示不会自动运行。生产调度仍由 OpenClaw 单独管理。

## 新鲜度与采用

`known_latest` 表示已知最新，`recommended_stable` 表示建议采用。任何新版本默认进入 Frontier，只有官方稳定发布、文档完整、最小兼容测试通过、无严重已知问题和回滚路径五项均通过才晋升 Stable。`review_due_at` 到期只触发复核。

升级 Hermes 前先运行：

```bash
hermes update --check
hermes -p opportunity-discovery profile export opportunity-discovery -o "/Users/liujun/.hermes/profiles/opportunity-discovery/backups/pre-update.tar.gz"
```

不要自动跟随 `main`；确认官方 Release、安装测试和回滚命令后再升级固定版本。

## 快照与恢复

```bash
uv run --directory "/Users/liujun/Nutstore Files/我的坚果云/knowledge/integrations/hermes-opportunity-os" \
  opportunity-os snapshot \
  --home "/Users/liujun/.hermes/profiles/opportunity-discovery/opportunity-os" \
  --format json
```

快照不包含 `.env`。恢复时先停止该 Profile 的会话，将归档解压到一个新目录，运行 `doctor`，确认后再把 `config.yaml` 中 `OPPORTUNITY_OS_HOME` 指向新目录；不要覆盖原目录。

## 禁用与回滚

- 临时禁用：不运行 `hermes -p opportunity-discovery` 即可；OpenClaw 不受影响。
- Provider 故障：保留私有状态与待处理信号，恢复后重跑；不要循环消耗 API。
- Profile 级回滚：使用 `hermes profile export/import` 创建新 Profile 名进行验证。
- 代码回滚：切回本仓库上一提交；私有 JSON 数据格式保持向后兼容。

## 安全验证

```bash
uv run --directory "/Users/liujun/Nutstore Files/我的坚果云/knowledge/integrations/hermes-opportunity-os" --extra test pytest -q
rg -n --hidden --glob '!.git/**' --glob '!raw/**' \
  '(go-[A-Za-z0-9_-]{12,}|sk-[A-Za-z0-9_-]{12,}|OPENCODE_GO_API_KEY=.+|DEEPSEEK_API_KEY=.+)' \
  "/Users/liujun/Nutstore Files/我的坚果云/knowledge"
```

任何外部发布、岗位投递、联系他人、付费、删除、推送和 OpenClaw 修改都不在本系统授权范围内。
