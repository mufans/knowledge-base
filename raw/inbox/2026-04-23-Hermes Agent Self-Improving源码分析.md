# Hermes Agent 源码分析：Self-Improving 闭环

> 来源：[深入源码：Hermes Agent 如何实现 "Self-Improving"](https://mp.weixin.qq.com/s/Qi68ptxQRyiA932JU49SYQ)
> 作者：三剑（阿里云开发者）
> 日期：2026-04-23
> 标签：#AI-Agent #Self-Improving #Skill-System #Memory-System

## 核心观点

OpenRouter排行榜：Hermes Agent增速+204%，Top Coding Agents排第一。GitHub从0到106k+ Star，上线不到半年。

**关键区别**：OpenClaw的Skill是手写的Markdown文件——你写多少它会多少；Hermes的Agent干完活后，自动把踩坑经验提炼成可复用Skill，用得越久能力越强。

## 三个子系统，一个闭环

### 1. Memory：越用越懂你

- 两个文件：`MEMORY.md`（Agent笔记）+ `USER.md`（用户认知）
- **容量限制**：MEMORY限2200 chars，USER限1375 chars——迫使Agent挑重要的记
- 超限时add失败，返回current_entries让模型自己决定删/合并——这本身就是"自我反思"
- **冻结快照机制**：会话开始时冻结，保护前缀缓存省token
- **声明式事实**：存"User prefers concise responses"不存"Always respond concisely"

### 2. Skill：把做过的事变成会做的事

- 目录结构：`~/.hermes/skills/<category>/<name>/SKILL.md`
- SKILL.md包含：触发条件、步骤、**Pitfalls（踩坑经验）**
- **创建触发**：工具调用超过5次、踩坑修复后、用户纠正后
- **自我修补**：执行中发现遗漏，用fuzzy_find_and_replace做精确patch，安全扫描不通过自动回滚
- **渐进式加载**：系统提示词只放索引，按需加载完整内容
- **对比OpenClaw**：OpenClaw的Skill要么手写要么社区装，Agent本身不会从工作中学习

### 3. Nudge Engine：后台静默审查

- 两个计数器：Memory（每10回合）、Skill（每10迭代）
- **后台fork Agent**：不干扰用户，独立实例做审查
- Review Agent共享Memory，禁用自身nudge避免无限递归
- 每次prompt以"If nothing is worth saving, just say 'Nothing to save.'"收尾

## K8s部署案例：从12次调用到6次零错误

| 维度 | 会话1（冷启动） | 会话2（Skill复用） | 会话3（全协同） |
|------|---------------|-----------------|--------------|
| 工具调用 | 12次 | 9次 | 6次 |
| 错误数 | 2 | 1 | 0 |
| Memory | 无 | 触发写入 | 系统提示词注入 |
| Skill | 触发创建 | 复用+自我修补 | 复用已修补版本 |

## 安全机制

- **Memory内容扫描**：防prompt injection（"ignore previous instructions"等模式）
- **Skill安全扫描**：自创和Hub安装走同一套扫描，不通过回滚
- **RDSHermes增强**：AK/SK加密托管，密钥不落盘

## 对OpenClaw的借鉴价值

1. **Memory容量限制**：OpenClaw的MEMORY.md是纯追加模式，几个月就膨胀成几万行。Hermes的容量限制倒逼信息压缩
2. **Skill自动创建**：OpenClaw缺少从工作中学习的通路——没有创建触发、没有patch机制
3. **冻结快照**：保护前缀缓存，避免每轮API调用重新计费
4. **后台审查**：自省不应占用用户任务的attention budget
5. **patch优先于全量重写**：保留已验证的稳定部分

## 设计取舍

| 设计决策 | 表面效果 | 背后考量 |
|---------|---------|---------|
| Memory限2200 chars | 迫使Agent挑重要的记 | 低质量Memory注入系统提示词=每次API调用都带噪声 |
| 声明式vs操作步骤分离 | Memory存事实，Skill存步骤 | 更新频率、触发条件、安全风险完全不同 |
| 冻结快照模式 | 系统提示词会话内不变 | 保护前缀缓存，避免重复计费 |
| 后台fork审查 | 用户无感知 | 自省不应占用attention budget |
| patch优先于全量重写 | 局部修复Skill | 保留已验证的稳定部分 |

## 下一步方向

- 生命周期管理（last_used、use_count、success_rate）→ 自动降权归档
- 技能组合（经常一起用的Skill合成工作流）
- 创建透明度（创建后通知用户审核）
- 团队治理（写操作二次确认、可审计）
