# Ghostty 离开 GitHub: 开源基础设施的信任危机

> tags: #GitHub #OpenSource #Developer-Tools #Ghostty #Mitchell-Hashimoto
> source: [2026-04-29-新闻热点](../../raw/inbox/2026-04-29-新闻热点.md)
> score: 技术深度6/10 | 实用价值7/10 | 时效性10/10 | 领域匹配7/10 | 综合 7.5/10

## 核心概念

Ghostty终端创始人Mitchell Hashimoto（HashiCorp联合创始人）宣布将Ghostty代码仓库从GitHub迁移至自托管平台，GitHub将变为只读镜像。原因：GitHub在微软治理下"不再是一个适合认真工作的地方"，过去一个月几乎天天宕机。此事件在Hacker News获得2846分，引发开发者社区对GitHub可靠性的广泛讨论。

## 设计原理

- **核心问题**: GitHub作为全球最大代码托管平台的单点故障风险——当平台本身不稳定时，所有依赖它的开发者都受影响
- **Mitchell的观点**: 代码托管是基础设施，基础设施需要可靠性优先，而GitHub在微软治理下追求增长和功能扩张，牺牲了稳定性
- **迁移策略**: 自托管+GitHub镜像，既保证自主可控，又保留GitHub的曝光和社区发现能力

## 关联分析

- 与[Warp终端](Warp-Terminal-Analysis.md)开源事件同日发生——两个重要终端项目都在重新定义与开源社区的关系
- 对使用GitHub托管项目的开发者有直接影响——评估是否需要代码仓库的多地备份策略

## 可执行建议

1. **代码备份**: 确保重要项目有GitHub之外的备份（GitLab、自托管Gitea等）
2. **关注Ghostty**: Ghostty是高性能终端，迁移后的新平台值得关注
3. **风险评估**: 如果正在构建依赖GitHub API的工具（如CI/CD、知识库采集），需要考虑GitHub不稳定的备选方案
