# Open Design: 本地优先的AI设计工具

> tags: #Design-Tool #Local-First #Claude-Code #Agent-Skill #TypeScript
> source: [2026-04-29-GitHub项目](../../raw/inbox/2026-04-29-GitHub项目.md)
> project: [nexu-io/open-design](https://github.com/nexu-io/open-design)
> score: 技术深度7/10 | 实用价值8/10 | 时效性9/10 | 领域匹配7/10 | 综合 7.8/10

## 核心概念

Open Design是一个**本地优先、开源**的设计工具，定位为Anthropic Claude Design的替代方案。内置19个Skills、71个品牌级设计系统，支持沙盒预览和HTML/PDF/PPTX多格式导出。可运行在Claude Code、Codex、Cursor、Gemini CLI、OpenCode、Qwen等多种AI编码Agent上。

## 设计原理

- **Trade-off**: 放弃云端协作（Figma的核心优势）换取本地运行、隐私保护和AI Agent深度集成
- **关键决策**: 以"Skill"为设计能力单元，每个Skill封装一个设计任务（如生成配色方案、布局组件等），AI Agent通过调用Skill完成设计
- **与竞品差异**: Figma是协作设计平台，Open Design是**AI Agent的设计工具**——设计由Agent驱动而非人类拖拽

## 关键实现

- **19个设计Skills**: 封装设计任务为可编程Skill，Agent可组合调用
- **71个品牌级设计系统**: 预置设计规范，确保生成内容的品牌一致性
- **沙盒预览**: 设计结果在隔离环境中预览，不影响本地系统
- **多格式导出**: HTML/PDF/PPTX，覆盖主要交付场景
- **多Agent兼容**: 支持Claude Code、Codex、Cursor、Gemini CLI、OpenCode、Qwen
- ⭐3188，TypeScript实现

## 关联分析

- 设计思路与[mattpocock-skills](mattpocock-skills.md)类似——将领域能力封装为Skill供Agent使用
- 可与[Skill-Auto-Creation](../concepts/Skill-Auto-Creation.md)结合，探索设计Skill的自动生成
- 对Vibe Coding方向有参考价值：AI生成代码+AI生成设计=完整的AI应用开发链路

## 可执行建议

1. **Vibe Coding集成**: 在AI应用开发流程中引入Open Design，实现代码+设计的AI全链路生成
2. **Skill模式借鉴**: 其将设计能力封装为Agent Skill的模式，可推广到其他垂直领域（如测试、文档、部署）
3. **多Agent兼容策略**: 研究其如何同时支持6种不同Agent平台，对自研工具的跨平台适配有参考价值
