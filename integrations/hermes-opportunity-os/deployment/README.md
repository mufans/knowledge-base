# Native deployment boundary

这些资产只做声明与薄适配，不实现第二套调度、重试、失败告警、消息队列、IM 或 ngrok LaunchAgent。

- `openclaw/cron-jobs.json` 通过 OpenClaw 官方 `cron` CLI 对账；默认 dry-run，`--apply` 才修改。只有 description 带固定 `[managed-by:opportunity-os/v1]` marker 的作业才属于受管集合；同名非受管作业或重复名称会 fail-closed。删除清单中的旧受管作业只会被禁用，不会自动删除。生产副本必须把 `__OPENCLAW_DINGTALK_OWNER__` 替换为明确 owner 目标，未替换时 `--apply` 会拒绝执行。
- 知识库同步只调用 `AGENTS.md` 指定的 `/Users/liujun/.openclaw/workspace/scripts/sync_kb.sh`，仓库不包含副本。
- `ngrok` 只通过官方 `ngrok service install/start/restart` 管理。配置必须把 upstream 指向 `http://127.0.0.1:<port>`，并严格按 GitHub OAuth、拒绝非 owner、注入 `x-opportunity-origin` 三条规则执行。状态查询通过 loopback `127.0.0.1:4040` 的 ngrok agent API 读取，不伪造官方不存在的 `service status` 命令。
- macOS LaunchAgent 只负责 loopback Dashboard 自启动；ngrok 不创建自定义 plist。Dashboard LaunchAgent 以 `0600` 保存，并注入 `DASHBOARD_HOME`、随机域名对应的 `DASHBOARD_REMOTE_HOST` 和强随机 `DASHBOARD_ORIGIN_CREDENTIAL`。

所有命令都使用固定 argv、`shell=False` 和最小环境变量。以下命令默认只预览：

```bash
python -m opportunity_os.deployment cron-reconcile \
  --manifest deployment/openclaw/cron-jobs.json \
  --openclaw /opt/homebrew/bin/openclaw

python -m opportunity_os.deployment dashboard-agent \
  --executable /absolute/path/to/opportunity-os \
  --private-home /absolute/path/to/private-state \
  --destination /absolute/path/to/Library/LaunchAgents/com.opportunity-os.dashboard.plist \
  --remote-host owner.ngrok-free.app \
  --origin-credential-file /absolute/private/path/dashboard-origin

python -m opportunity_os.deployment ngrok-config \
  --authtoken-file /absolute/private/path/ngrok-authtoken \
  --owner-email-file /absolute/private/path/github-owner-email \
  --origin-credential-file /absolute/private/path/dashboard-origin \
  --destination /absolute/private/path/ngrok.yml

python -m opportunity_os.deployment ngrok-status
```

生产应用时在确认 dry-run 后显式增加 `--apply`。三个输入文件必须是绝对路径、非符号链接、普通文件且权限为 `0600` 或更严格；CLI 直接安全读取，秘密不会出现在 argv 或 shell 替换命令中。origin credential 使用至少 32 字节随机数编码为 43 个以上 URL-safe 字符。

`ngrok-config` 结构化生成完整 v3 YAML（模板仅供审计），使用 `url: https://` 申请随机 HTTPS 地址并以 `0600` 原子写入；`ngrok service install` 前适配器还会执行本地严格 schema 校验与官方 `ngrok config check --config`。获得随机域名后，以纯 hostname（不含 scheme/path）重建 Dashboard LaunchAgent，使 Host allowlist 与 ngrok origin header 同时闭环。
