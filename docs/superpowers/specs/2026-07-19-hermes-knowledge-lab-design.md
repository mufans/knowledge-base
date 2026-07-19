# Hermes Knowledge Lab 隔离试点设计

## 目标

在不影响现有 OpenClaw、不接管其 Cron 和钉钉渠道的前提下，搭建 Hermes Agent v0.18.2 `knowledge-lab` 隔离试点。试点用于验证知识提炼、可验证目标、跨会话检索和 Skill 生命周期管理，不在首期承担生产定时任务。

## 成功标准

1. Hermes 版本固定为 v0.18.2，由 `uv` 管理独立 Python 3.12 运行环境。
2. 创建独立 `knowledge-lab` Profile，不复用 OpenClaw 运行状态、Cron、钉钉凭据或工作区记忆。
3. 主 Provider 为 OpenCode Go `deepseek-v4-flash`，fallback 为 DeepSeek 官方 `deepseek-v4-flash`。
4. API Key 只能由用户在交互式提示中输入；不从 OpenClaw 复制，不出现在 shell 命令参数、日志、Git 或对话输出中。
5. Hermes 能使用主 Provider 完成一次无工具模型调用，并能识别 fallback 配置。
6. Hermes 能读取知识库规则，但首期验证不对 `raw/`、`wiki/` 或现有未提交文件执行写入。
7. 运行知识库质量检查时不改变现有文件，且记录基线结果。

## 方案比较

### 方案 A：OpenCode Go 主模型 + DeepSeek 官方 fallback（采用）

- Hermes 对 `opencode-go` 和 `deepseek` 均有原生 Provider 支持。
- OpenCode Go 承担常态成本，DeepSeek 官方 API 承担订阅限额、网络或 Provider 故障时的回退。
- 避免首期同时调试三个 Provider。

### 方案 B：火山方舟 Coding Plan 主模型 + DeepSeek fallback

- 国内网络链路更短，且 Coding Plan 已声明支持 Hermes。
- Hermes v0.18.2 需通过 OpenAI-compatible custom provider 接入，配置和故障定位复杂度高于原生 Provider。
- 作为第二阶段编码子 Agent Provider 保留。

### 方案 C：仅 DeepSeek 官方 API

- 配置最简单，无订阅周期限额。
- 无法充分利用已订阅的 OpenCode Go，中高频 Agent 负载的成本可能更高。

## 系统边界

### Hermes 运行时

- 安装根目录：Hermes 默认用户级路径 `~/.hermes/`。
- Python：由 `uv` 提供受管 Python 3.12，不使用系统 Python 3.14。
- Profile：`knowledge-lab`，拥有独立 config、env、memory、sessions、skills、cron 和 state database。
- 试点期不安装 Gateway 常驻服务，不启用钉钉。

### 知识库权限

- 默认工作目录指向当前 knowledge 项目。
- Profile 不等于沙箱，因此使用 Docker terminal backend 执行 Agent 命令。
- 容器挂载设计：`raw/` 只读；首期将整个项目按只读方式验证，仅使用独立临时输出目录测试写入。
- 在后续获得单独批准前，不授予 `wiki/` 真实写权限。

## Provider 设计

### 主模型

- Provider：`opencode-go`
- Model：`deepseek-v4-flash`
- 用途：对话、知识分析、轻量工具调用、大多数辅助任务。

### 备用模型

- Provider：`deepseek`
- Model：`deepseek-v4-flash`
- 触发：OpenCode Go 限额、鉴权失败、可恢复服务错误或网络故障。

### 复杂任务

`opencode-go/deepseek-v4-pro` 仅作为手工切换选项，不作为默认模型，避免过早消耗 Pro 的订阅额度。

## 凭据处理

1. 安装与非鉴权配置先完成。
2. 首次需要 OpenCode Go API Key 时，中断自动流程并通知用户。
3. 由用户在 PTY 的隐藏输入提示中粘贴 Key。
4. 重复同样步骤录入 DeepSeek API Key。
5. 不使用 `echo`、命令行参数、shell history 或临时明文文件传递 Key。
6. 验证输出只报告 Provider 是否通过，不显示 Key 前后缀。

## 初始配置

- Curator：启用。
- Curator consolidation：关闭，防止试点阶段自动合并 Skill。
- Cron：不创建生产任务。
- Gateway：不安装常驻服务。
- DingTalk：不配置。
- OpenClaw migration：不执行写入迁移；如需了解可迁移内容，只允许 `--dry-run --preset user-data`。
- OpenClaw cleanup：永不在试点流程中执行。

## 验证流程

1. 确认 Hermes CLI 和 v0.18.2 版本。
2. 确认 `knowledge-lab` Profile 的目录、独立配置与状态。
3. 交互式录入 OpenCode Go Key，执行最小无工具模型调用。
4. 交互式录入 DeepSeek Key，确认 fallback 配置可解析。
5. 验证 Agent 能读取 `AGENTS.md` 与 `purpose.md`。
6. 在容器内验证 `raw/` 写入被拒绝。
7. 将测试输出写入临时目录，确认真实 Wiki 未改变。
8. 运行 `python scripts/check_quality.py` 记录现有基线，不把项目已存质量问题归因于 Hermes 安装。
9. 检查 Git diff，确认除设计、计划和操作日志外，未改动用户文件。

## 故障处理

- 安装失败：保留安装日志，不改动 OpenClaw，优先修复 uv/Python 隔离环境。
- 主 Provider 失败：在配置 fallback 后重试；不在未知原因下反复刷新请求。
- 凭据失败：只要求用户重新输入，不读取 OpenClaw 凭据作为替代。
- Docker backend 不可用：停止文件工具测试，不降级到无边界的 local backend 执行写入。
- 质量检查失败：记录为项目基线，不在本任务中修改无关 Wiki 页面。

## 不在首期范围

- 迁移或删除 OpenClaw 配置。
- 复制 OpenClaw API Key、钉钉 Token 或 Gateway Token。
- 配置钉钉 Bot、Gateway 常驻服务或生产 Cron。
- 将火山方舟 Coding Plan 接入为第三 Provider。
- 让 Hermes 直接写入生产 Wiki。
- 自动运行 Curator LLM consolidation。
- 执行 GitHub Pages 部署、Git push 或知识库同步脚本。

## 回滚

试点不修改 OpenClaw，因此回滚仅涉及停止 `knowledge-lab` Profile 和卸载 Hermes。删除 Profile 或卸载属于破坏性操作，不在默认实施中执行，必须另行获得用户批准。
