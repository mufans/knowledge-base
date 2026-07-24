---
title: "LLM Wiki"
category: "entities"
tags: ["LLM", "Wiki", "知识库", "MCP", "Agent", "Desktop"]
rating: 9.5
description: "跨平台桌面知识库应用，基于 Karpathy LLM Wiki 方法论，LLM 自动将文档转化为结构化、可互联的 wiki"
date: "2026-07-24"
---

# LLM Wiki

## 基本信息

| 属性 | 值 |
|------|------|
| 名称 | LLM Wiki |
| 作者 | [nashsu](https://github.com/nashsu) |
| 仓库 | [nashsu/llm_wiki](https://github.com/nashsu/llm_wiki) |
| 技术栈 | Tauri v2 + React 19 + TypeScript + sigma.js + LanceDB + Rust Agent |
| 类型 | 跨平台桌面应用 |
| 许可证 | MIT |
| 活跃度 | ⭐ 高（持续开发中，最近提交 2026-07-20） |
| 灵感来源 | [Karpathy LLM Wiki Gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) |

## 核心定位

基于 Karpathy LLM Wiki 方法论的**完整桌面实现**。核心理念：知识是"编译一次、持续维护"的持久 wiki，而非传统 RAG 的"每次查询从头检索"。

## 2026-07 版本新增功能（与 4月分析对比）

### 1. Rust 后端聊天 Agent（全新子系统）

从浏览器端 TypeScript 循环升级为 **Rust 后端 Agent 运行时**：

- **Tool-using Agent** — 可调用 wiki 搜索、源码搜索、图谱搜索、Web 搜索、工作区文件工具
- **Shell 执行** — 工作区命令自动放行，外部 shell 命令需要用户批准
- **Agent Skills** — 扫描并启用本地 `SKILL.md` 目录，通过 `/skill` 选择技能，Agent 按需读取
- **生成输出预览** — Agent 创建的 Markdown、HTML、图片等工作区文件显示为输出，可预览和打开
- **Mermaid 渲染** — chat 中直接渲染 Mermaid 代码块，语法错误显示为紧凑卡片而非原始 parser 输出

### 2. MCP Server + Local HTTP API（关键集成层）

- **本地 HTTP API** — `127.0.0.1:19828` JSON API，支持混合搜索、文件读取、图谱遍历
- **内置 MCP Server** — 随应用启动，通过 MCP 协议暴露知识库能力
- **Agent Skill 一键安装** — `npx skills add llm_wiki_skill` 即可将 LLM Wiki 接入 Claude Code / Codex
- 实现知识库的**外部化访问** — 不只是桌面应用，还是其他 AI agent 的知识库后端

### 3. 多格式文档解析增强

| 格式 | 支持方式 |
|------|---------|
| PDF | MinerU（本地/云端）、内置解析 |
| Office | .docx, .pptx, .xlsx |
| EPUB/MOBI | 电子书格式 |
| Org mode | Emacs 生态 |
| 图片/媒体 | 多模态摄入 |
| 网页剪藏 | Chrome Web Clipper 一键抓取 + 自动摄入 |
| URL 批量 | 批量导入网页 |

### 4. 多模态图像摄入

- PDF 中嵌入的图片自动提取
- 视觉 LLM 生成事实性文字说明
- 图像感知搜索结果，支持灯箱预览 + 跳转到源

### 5. 灵活模型配置

- 每项目独立配置模型
- Chat 和 Ingest 使用独立模型路由
- 自定义 Provider、headers、streaming 设置

### 6. 纯源检索模式（Read Sources Only）

新增模式：只从原始导入材料中回答，不依赖 wiki 页面。在需要严格的事实核查场景下很有用。

### 7. 项目管理与迁移

- 完整项目打包导出/导入
- 跨设备迁移
- 从现有页面重建 Wiki 索引

### 8. Source Folder Auto-Watch

`raw/sources/` 目录外部变更自动检测——文件增删改自动触发摄入/删除，无需手动操作。

### 9. Thinking/Reasoning 显示

对输出 `<think>` 块的模型（DeepSeek、QwQ 等）：
- 流式显示滚动 5 行 + 透明度渐隐
- 完成后折叠，点击展开
- 与主回复视觉分离

## 关键设计决策分析

### Rust Backend Agent vs TypeScript-only

**为什么要迁移到 Rust 后端**：
1. **Tool-using 更安全** — Rust 后端可以细粒度控制 shell 执行权限（工作区 vs 外部）
2. **性能** — 知识库查询、图谱遍历等计算密集型操作在 Rust 侧更快
3. **IPC 统一** — MCP Server、HTTP API、Agent 共享同一个后端，避免多进程资源竞争
4. **Tauri 原生能力** — 直接调用系统 API，文件 I/O 更高效

### MCP Server 的战略意义

MCP Server 将 LLM Wiki 从"桌面知识库应用"扩展为**知识库基础设施**：
- Claude Code / Codex 可以直接查询你的知识库
- 其他支持 MCP 的 agent 工具也可以接入
- 知识库不再被桌面应用 UI 绑定

### Chrome Web Clipper

实用的一键剪藏功能——对比 Obsidian Web Clipper：不需要手动选文件夹/分类，剪藏后自动进入摄入队列，LLM 自动分类和组织。

## 与知识工作流的整合

LLM Wiki 的 MCP Server + Agent Skill 组合意味着：
1. 桌面应用内用 Chat 查询知识库（带图谱交互）
2. Claude Code/Codex 开发时通过 MCP 访问同一知识库
3. HTTP API 可供自定义脚本/工作流调用
4. Chrome Clipper 一键抓取网页并自动入库

## 更新分析（对比4月版本）

| 维度 | 4月版本 | 7月版本 |
|------|---------|---------|
| 聊天引擎 | TypeScript 浏览器端 | Rust 后端 Agent 运行时 |
| MCP 支持 | ❌ | ✅ 内置 MCP Server + HTTP API |
| Agent Skills | ❌ | ✅ SKILL.md 扫描 + 按需加载 |
| 文档格式 | PDF 为主 | PDF/Office/EPUB/MOBI/Org/图片/网页 |
| 外部集成 | ❌ | Chrome Clipper、MCP、HTTP API |
| Shell 执行 | ❌ | ✅ 带权限控制 |
| 多模态 | ❌ | ✅ 图片提取 + 视觉 LLM 说明 |
| 项目管理 | ❌ | ✅ 项目导出/导入/迁移 |
| 翻译 | 英文 | 英文/中文/日文/韩文 |

## 值得关注的设计

1. **场景模板** — Research/Reading/Personal Growth/Business/General 各有预配置的 purpose.md 和 schema.md，降低使用门槛
2. **分层内容分区** — `agent-workspace/` 独立目录存储 Agent 生成的文件，不影响核心知识库结构
3. **Mermaid 渲染容错** — 语法错误显示为紧凑卡片而非原始 parser 输出，保持 chat 整洁
4. **渐进式 Sources 视图** — 大源文件夹按需渲染，保持大型知识库的响应性

## 相关链接

- [项目仓库](https://github.com/nashsu/llm_wiki)
- [Karpathy 原始 Gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)
- [LLM Wiki Agent Skill](https://github.com/nashsu/llm_wiki_skill)
- [sigma.js 图谱可视化](https://www.sigmajs.org/)
- [LanceDB 向量数据库](https://lancedb.github.io/lancedb/)
