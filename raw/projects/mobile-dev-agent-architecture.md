# Mobile Dev Agent - 架构设计文档

## 1. 项目概述

**名称**：Mobile Dev Agent（移动端智能开发助手）
**定位**：多 Agent 协作系统，输入产品需求 → 输出可运行的移动端代码
**支持平台**：Android (Kotlin) / HarmonyOS (ArkTS) / iOS (Swift)

---

## 2. 系统架构

```
┌─────────────────────────────────────────────────────────┐
│                    用户交互层                              │
│            CLI (Typer) / Web UI (未来)                    │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│                 LangGraph 编排层                          │
│                                                          │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐           │
│  │  需求分析  │───▶│  架构设计  │───▶│  代码生成  │──┐      │
│  │  Agent   │    │  Agent   │    │  Agent   │  │      │
│  └──────────┘    └──────────┘    └──────────┘  │      │
│                                       ▲          │      │
│  ┌──────────┐                         │          │      │
│  │  代码审查  │─────────────────────────┘ (不通过) │      │
│  │  Agent   │                                    │      │
│  └────┬─────┘                                    │      │
│       │ (通过)                                   │      │
│       ▼                                          │      │
│  ┌──────────┐                                    │      │
│  │  测试生成  │                                    │      │
│  │  Agent   │                                    │      │
│  └──────────┘                                    │      │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│                  MCP 工具层                               │
│                                                          │
│  ┌────────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ │
│  │ Context7   │ │ GitHub   │ │ 文件系统  │ │ Figma    │ │
│  │ 文档查询   │ │ 仓库操作  │ │ 读写     │ │ 设计稿   │ │
│  └────────────┘ └──────────┘ └──────────┘ └──────────┘ │
└─────────────────────────────────────────────────────────┘
```

---

## 3. 核心组件

### 3.1 LangGraph 工作流

使用 `StateGraph` 定义有向图，节点是 Agent，边是数据流和控制流。

```python
workflow = StateGraph(AgentState)

# 节点
workflow.add_node("requirement_analyst", ...)
workflow.add_node("architect", ...)
workflow.add_node("coder", ...)
workflow.add_node("reviewer", ...)

# 边
workflow.set_entry_point("requirement_analyst")
workflow.add_edge("requirement_analyst", "architect")
workflow.add_edge("architect", "coder")
workflow.add_edge("coder", "reviewer")

# 条件边（反馈循环）
workflow.add_conditional_edges("reviewer", should_continue, {
    "coder": "coder",   # 审查不通过 → 重新生成
    END: END,            # 审查通过 → 结束
})
```

### 3.2 Agent 状态（AgentState）

所有 Agent 共享一个 TypedDict 状态，通过 LangGraph 的 reducer 机制自动合并更新。

```python
class AgentState(TypedDict):
    user_input: str                    # 原始需求
    platform: str                      # 目标平台
    requirement: dict                  # 需求分析结果
    architecture: dict                 # 架构设计
    generated_files: list[dict]        # 生成的代码文件
    review_result: dict                # 审查结果
    test_files: list[dict]             # 测试文件
    iteration_count: int               # 迭代次数（控制循环）
    messages: list[dict]               # 消息历史
    errors: list[str]                  # 错误记录
    status: str                        # 状态
```

### 3.3 Agent 职责

| Agent | 输入 | 输出 | 关键能力 |
|-------|------|------|---------|
| **需求分析** | 自然语言需求 | 结构化需求 JSON | 需求拆解、完整性检查、隐式需求推断 |
| **架构设计** | 结构化需求 | 架构方案 JSON | 模块划分、分层设计、依赖管理 |
| **代码生成** | 架构方案 | 代码文件列表 | 多文件生成、平台适配、最佳实践 |
| **代码审查** | 代码文件 | 审查结果 JSON | 静态分析、质量评分、修改建议 |
| **测试生成** | 代码文件 | 测试文件 | 单元测试、边界用例 |

---

## 4. 数据流

```
用户输入 "做一个登录页面"
    │
    ▼
[需求分析 Agent]
    → summary: "实现用户登录注册功能"
    → features: ["手机号登录", "验证码", "密码登录", "第三方登录"]
    → screens: [登录页, 注册页, 验证码页]
    │
    ▼
[架构设计 Agent]
    → pattern: MVVM
    → modules: [auth/ui, auth/viewmodel, auth/repository, auth/model]
    → directory_structure: {完整项目结构}
    │
    ▼
[代码生成 Agent]
    → files: [
        LoginScreen.kt,
        LoginViewModel.kt,
        AuthRepository.kt,
        ...
      ]
    │
    ▼
[代码审查 Agent]
    → passed: true/false
    → score: 85
    → issues: [...]
    │
    ├── 通过 → 输出最终代码
    └── 不通过 → 回到代码生成（带上审查建议），最多重试3次
```

---

## 5. 目录结构

```
mobile-dev-agent/
├── src/
│   ├── __init__.py
│   ├── workflow.py              # LangGraph 工作流定义（核心入口）
│   ├── models/
│   │   ├── __init__.py
│   │   └── state.py             # AgentState 定义 + 数据模型
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── requirement_analyst.py  # 需求分析 Agent
│   │   ├── architect.py            # 架构设计 Agent
│   │   ├── coder.py                # 代码生成 Agent
│   │   └── reviewer.py             # 代码审查 Agent
│   ├── tools/                   # 工具函数（Phase 4）
│   ├── mcp_server/              # MCP Server（Phase 4）
│   ├── utils/                   # 通用工具
│   └── templates/               # 代码模板
├── config/                      # 配置文件
├── tests/                       # 测试
├── docs/                        # 文档
├── scripts/
│   └── cli.py                   # CLI 入口
├── output/                      # 生成的代码输出
├── pyproject.toml               # 项目配置
├── .env.example                 # 环境变量模板
├── .gitignore
└── README.md
```

---

## 6. 技术栈

| 层级 | 技术 | 用途 |
|------|------|------|
| Agent 编排 | **LangGraph** | 工作流图、条件路由、状态管理 |
| LLM 调用 | **LangChain + ChatOpenAI** | 统一 LLM 接口 |
| LLM 模型 | **GLM-5** | 主要模型（免费） |
| 工具协议 | **MCP** | 外部工具调用（Phase 4） |
| CLI | **Typer + Rich** | 命令行界面 |
| 数据验证 | **Pydantic** | 结构化输出验证 |

---

## 7. 分阶段实施

### Phase 1：基础设施（当前）✅
- [x] 项目骨架搭建
- [x] LangGraph StateGraph 基础 workflow
- [x] AgentState Schema 定义
- [x] 4 个核心 Agent 框架
- [ ] 跑通最小链路（输入需求 → 输出代码）

### Phase 2：完善代码生成
- [ ] Few-shot 示例（你的移动端经验沉淀）
- [ ] 平台特定模板（Android/鸿蒙/iOS）
- [ ] 条件路由（按平台选择不同策略）
- [ ] 代码文件保存到磁盘

### Phase 3：反馈循环
- [ ] 代码审查 Agent 完善
- [ ] 审查不通过 → 重新生成的循环
- [ ] 迭代次数控制
- [ ] 测试生成 Agent

### Phase 4：MCP 工具集成
- [ ] 开发 MCP Server（移动端工具集）
- [ ] 接入 Context7（实时文档查询）
- [ ] Human-in-the-Loop（人工审核节点）

### Phase 5：产品化
- [ ] CLI 完善（mdev 命令）
- [ ] Web UI（可视化 workflow）
- [ ] 项目模板系统
- [ ] 开源发布

---

## 8. 使用方式

```bash
# 环境准备
cd ~/projects/mobile-dev-agent
cp .env.example .env
# 编辑 .env 填入 API Key

# 安装依赖
pip install -e ".[dev]"

# 生成代码
mdev "做一个用户列表页，支持下拉刷新" -p harmony

# 审查项目
mdev review ./my-app -p android

# 查看配置
mdev info
```

---

*文档版本: 0.1.0 | 创建时间: 2026-03-27*
