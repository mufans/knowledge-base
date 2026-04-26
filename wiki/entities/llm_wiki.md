# LLM Wiki

> 基于 Karpathy LLM Wiki 方法论的桌面端个人知识库，LLM 自动将文档转化为结构化、可互联的 wiki

## 基本信息

| 属性 | 值 |
|------|-----|
| 名称 | LLM Wiki |
| 作者 | nashsu |
| 仓库 | [nashsu/llm_wiki](https://github.com/nashsu/llm_wiki) |
| 技术栈 | Tauri v2 + React 19 + TypeScript + sigma.js + LanceDB |
| 类型 | 桌面应用 |
| 许可证 | MIT |
| 灵感来源 | [Karpathy LLM Wiki Gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) |

## 核心定位

LLM Wiki 是 Karpathy 的 LLM Wiki 方法论的**完整桌面实现**。核心理念：知识是**编译一次、持续维护**的持久 wiki，而非传统 RAG 的"每次查询从头检索"模式。

## 架构设计（深度分析）

### 三层架构

忠实实现 Karpathy 的三层设计：

1. **raw/** — 不可变原始文档（PDF、网页、论文等），作为知识源
2. **wiki/** — LLM 生成的结构化 wiki 页面，含 YAML frontmatter、`[[wikilinks]]` 交叉引用
3. **schema/** — 结构规则（schema.md 定义页面类型、格式规范）+ purpose.md（新增，定义知识库目标和方向）

**设计决策**：新增 `purpose.md` 是此项目对原版最值得注意的扩展。schema 管"怎么组织"，purpose 管"为什么存在"——LLM 在每次 ingest/query 时都会读取 purpose，确保生成内容不偏离知识库目标。

### 两步摄入流程（Analysis → Generation）

原版是单步 ingest（读+写同时进行），此项目拆分为两个串行 LLM 调用：

**Step 1 — Analysis**：LLM 读取原始文档 → 输出结构化分析
- 提取关键实体、概念、论点
- 建立与现有 wiki 内容的关联
- 识别与已有知识的矛盾和张力
- 输出 wiki 结构建议

**Step 2 — Generation**：基于分析结果生成 wiki 文件
- 含 frontmatter 的源摘要页（type、title、sources[]）
- 实体页、概念页，含交叉引用
- 更新 index.md、log.md、overview.md
- 生成 review items（需人工判断的条目）
- 预生成 Deep Research 搜索查询

**Trade-off 分析**：token 消耗翻倍，但质量提升显著——Analysis 阶段让 LLM 先"理解"再"写作"，避免单步模式下边读边写导致的信息遗漏和结构混乱。对于个人知识库这种"质量优先、成本次要"的场景，这个 trade-off 合理。

### 四信号知识图谱关联度模型

这是项目最有技术深度的设计：

| 信号 | 权重 | 说明 |
|------|------|------|
| Direct link | ×3.0 | 通过 `[[wikilink]]` 直接链接的页面 |
| Source overlap | ×4.0 | frontmatter 中 sources[] 共享同一原始文档 |
| Adamic-Adar | ×1.5 | 共享邻居的关联强度（按邻居度数加权） |
| Type affinity | ×1.0 | 同类型页面加分（entity↔entity） |

**为什么用 Adamic-Adar 而不是 Jaccard/余弦？** Adamic-Adar 对"共享稀有邻居"赋予更高权重——如果两个页面共享一个连接很少的邻居，说明这个关联更独特、更有意义。Jaccard 只看交集比例，会淹没在高度连接的 hub 节点中。

## 核心实现

### 持久化摄入队列

- **串行处理**：防止并发 LLM 调用导致状态冲突
- **磁盘持久化**：队列写入磁盘，应用崩溃/重启后可恢复
- **自动重试**：失败任务最多重试 3 次
- **进度可视化**：Activity Panel 实时显示 pending/processing/failed 状态
- **可取消**：用户可随时取消队列中的任务

### SHA256 增量缓存

对每个原始文档计算 SHA256 哈希，存储在 `.llm-wiki/cache/` 中。摄入前检查哈希，未变化的文件自动跳过。这是"编译一次"理念的工程实现——与增量编译类似，只处理变化的部分。

### Louvain 社区检测

使用 `graphology-communities-louvain` 库实现：
- 基于链接拓扑自动发现知识聚类（不依赖预定义类型）
- 每个社区计算内聚度得分（实际边数 / 可能边数）
- 低内聚度社区（< 0.3）标记为"松散"，提示用户可能需要重新组织
- 支持按类型/社区切换节点着色模式

### 多阶段检索管线

```
Phase 1: 分词搜索（英文词分割 / CJK bigram + 标题匹配加分）
    ↓
Phase 1.5: 向量语义搜索（可选，LanceDB + OpenAI兼容endpoint）
    ↓
Phase 2: 图谱扩展（4信号模型，2跳遍历 + 衰减）
    ↓
Phase 3: 预算控制（可配上下文窗口 4K-1M，60% wiki / 20% 历史 / 5% index / 15% system）
    ↓
Phase 4: 上下文组装（编号引用，指示LLM用[1][2]格式引用）
```

**向量搜索可选的设计理由**：默认关闭，开启后 recall 从 58.2% 提升到 71.4%。可选意味着零配置可用——不需要额外的 embedding API，降低了入门门槛。同时保留了高质量用户的升级路径。

## 设计决策分析

### Tauri vs Electron

| 维度 | Tauri v2 | Electron |
|------|----------|----------|
| 打包体积 | ~10MB | ~150MB+ |
| 内存占用 | Rust 后端，显著更低 | Chromium 全套 |
| 安全模型 | 权限白名单，细粒度 IPC | 全 Node.js 能力 |
| 原生能力 | 直接调用系统 API | 需 Node addons |

**对于知识库工具**：Tauri 的低资源占用是关键优势——用户可能长时间运行此应用。且 Rust 后端处理文件 I/O、SHA256 计算、向量索引等计算密集任务更高效。

### LanceDB vs 其他向量库

选择 LanceDB 的理由：
- **嵌入式**：无需独立服务进程（vs Qdrant/Milvus）
- **Rust 原生**：与 Tauri 后端同生态，IPC 成本低
- **ONNX Runtime**：embedding 推理本地运行，不依赖外部 API
- **列式存储**：适合知识库的"一次写入、多次读取"模式

对比 Chroma（Python 生态首选）和 Faiss（Meta，纯索引库无持久化），LanceDB 在 Tauri+TypeScript 生态中是最自然的选择。

## 与同类方案对比

### vs 纯 Karpathy 方案（Gist 文档级）

| 维度 | Karpathy Gist | LLM Wiki |
|------|---------------|----------|
| 形态 | 方法论文档，复制给 LLM agent 用 | 完整桌面应用 |
| 摄入 | 单步 | 两步（质量更高） |
| 图谱 | 仅 [[wikilinks]] | 完整4信号图谱 + 可视化 |
| 检索 | 简单读取相关页面 | 多阶段管线 + 预算控制 |
| 用户体验 | 需要自己搭建 agent 流程 | 开箱即用 |

### vs Obsidian + AI 插件（如 Copilot、Smart Connections）

| 维度 | Obsidian 方案 | LLM Wiki |
|------|---------------|----------|
| 知识生成 | 手动或半自动 | 全自动两步摄入 |
| 图谱分析 | Smart Connections 插件 | 内置4信号模型 + 社区检测 |
| 原始文档管理 | 需手动整理 | raw/ 目录自动管理 |
| Obsidian 兼容 | 原生 | wiki/ 目录可直接作为 Obsidian vault |

**关键区别**：LLM Wiki 的 wiki/ 目录本身就是 Obsidian vault 兼容的——你可以在 Obsidian 中打开 wiki/ 目录直接浏览和编辑，同时享受 LLM Wiki 的自动化能力。

### vs RAG 方案

| 维度 | 传统 RAG | LLM Wiki |
|------|----------|----------|
| 知识形态 | 每次查询实时检索 | 持久化 wiki，编译一次 |
| Token 消耗 | 每次查询都要处理原始文档 | 摄入时消耗，查询时只读 wiki |
| 知识积累 | 无状态 | 有状态，知识随时间增长 |
| 可解释性 | 黑盒检索 | wiki 页面可人工审核 |

## 可借鉴模式

### 对个人自动化知识库（OpenClaw + mkdocs）的具体借鉴

1. **两步摄入模式**：当前 cron 任务是单步（LLM 直接生成），可改为先分析再生成，提升 wiki 页面质量
2. **SHA256 增量缓存**：对已分析的文档/URL 计算哈希，避免重复处理
3. **Source traceability**：每个 wiki 页面的 frontmatter 记录 sources[]，建立原始素材到知识页面的追溯链
4. **4信号关联模型**：当前知识库的交叉链接靠手动，可引入 Adamic-Adar 等算法自动发现隐含关联
5. **Graph Insights**：自动检测"知识孤岛"（degree ≤ 1 的页面）和"意外连接"，提示需要补充或关联的内容

### Python 低成本复现的设计思想

1. **Louvain 社区检测**：`python-louvain` 库，几行代码即可实现知识聚类
2. **Adamic-Adar**：`networkx` 内置 `adamic_adar_index()`，直接调用
3. **CJK bigram 分词**：简单实现即可覆盖中文检索场景
4. **预算控制**：按 token 比例分配上下文窗口，纯逻辑无需额外依赖
5. **两步摄入**：两个 LLM 调用串联，第一个输出 JSON 作为第二个的输入，任何框架都支持

## 质量评估

| 维度 | 评分 | 说明 |
|------|------|------|
| 代码质量 | ★★★★☆ | TypeScript + Rust 双后端，类型系统完善，结构清晰 |
| 架构成熟度 | ★★★★☆ | 对 Karpathy 方法论的实现非常忠实，扩展有理有据 |
| 实用性 | ★★★★★ | 开箱即用的桌面应用，解决了个人知识库的核心痛点 |
| 创新性 | ★★★☆☆ | 核心方法论来自 Karpathy，但在工程实现上有多个原创设计（4信号模型、社区检测集成） |
| 可维护性 | ★★★☆☆ | 单人项目，功能密集，长期维护存在风险 |

**总评**：这是一个 Karpathy 方法论的**教科书级实现**。不是简单的"照抄 Gist"，而是在忠实于核心理念的基础上做了大量有价值的工程扩展。两步摄入、4信号图谱、社区检测、可选向量搜索——每个设计都有清晰的动机和合理的 trade-off。对于正在搭建个人知识库自动化流程的开发者来说，这个项目的设计思想值得深入研究。

## 相关链接

- [Karpathy LLM Wiki 原始 Gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)
- [sigma.js 图谱可视化库](https://www.sigmajs.org/)
- [LanceDB 向量数据库](https://lancedb.github.io/lancedb/)
- [Tauri v2](https://v2.tauri.app/)
- [graphology 图论库](https://graphology.github.io/)
- [OpenClaw](../entities/OpenClaw.md)
