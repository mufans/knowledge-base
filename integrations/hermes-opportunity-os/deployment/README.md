# Native deployment boundary

这些资产只做声明与薄适配，不实现第二套调度、重试、失败告警、消息队列、IM 或 ngrok LaunchAgent。

- `openclaw/cron-jobs.json` 通过 OpenClaw 官方 `cron` CLI 对账；默认 dry-run，`--apply` 才修改。删除清单中的旧受管作业只会被禁用，不会自动删除。生产副本必须把 `__OPENCLAW_DINGTALK_OWNER__` 替换为明确 owner 目标，未替换时 `--apply` 会拒绝执行。
- 知识库同步只调用 `AGENTS.md` 指定的 `/Users/liujun/.openclaw/workspace/scripts/sync_kb.sh`，仓库不包含副本。
- `ngrok` 只通过官方 `ngrok service install/start/restart/status` 管理。配置必须把 upstream 指向 `http://127.0.0.1:<port>`，内联 GitHub OAuth 和拒绝非 owner 的规则，并以 `0600` 保存。
- macOS LaunchAgent 只负责 loopback Dashboard 自启动；ngrok 不创建自定义 plist。

所有命令都使用固定 argv、`shell=False` 和最小环境变量。以下命令默认只预览：

```bash
python -m opportunity_os.deployment cron-reconcile \
  --manifest deployment/openclaw/cron-jobs.json \
  --openclaw /opt/homebrew/bin/openclaw

python -m opportunity_os.deployment dashboard-agent \
  --executable /absolute/path/to/opportunity-os \
  --private-home /absolute/path/to/private-state \
  --destination /absolute/path/to/Library/LaunchAgents/com.opportunity-os.dashboard.plist

python -m opportunity_os.deployment ngrok-service status \
  --ngrok /absolute/path/to/ngrok \
  --config /absolute/path/to/ngrok.yml
```

生产应用时在确认 dry-run 后显式增加 `--apply`。OAuth owner 邮箱和 ngrok authtoken 不进入仓库；配置密钥在可见终端由用户输入后写入 `0600` 的运行时配置。

ngrok 运行时配置从 `deployment/ngrok/ngrok.yml.template` 复制，只替换 `__NGROK_AUTHTOKEN__` 和 `__OWNER_GITHUB_EMAIL__`。该 v3 配置留空具体域名，使用 `url: https://` 申请随机 HTTPS 地址；`ngrok service install` 前安装器会先调用官方 `ngrok config check --config` 验证。
