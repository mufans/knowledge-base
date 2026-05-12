---
title: "OpenMythos"
category: "entities"
tags: ["GitHub", "OS"]
rating: 8.5
description: "tags: #Transformer #Architecture #Claude #Recurrent-Depth #MoE #Looped-Transformer"
date: "2026-05-12"
---

# OpenMythos

> tags: #Transformer #Architecture #Claude #Recurrent-Depth #MoE #Looped-Transformer
> source: [kyegomez/OpenMythos](https://github.com/kyegomez/OpenMythos)
> project: [OpenMythos](https://github.com/kyegomez/OpenMythos)
> score: 技术深度9/10 | 实用价值6/10 | 时效性8/10 | 领域匹配8/10 | 综合 7.8/10

## 核心概念

OpenMythos 是对 Claude "Mythos" 架构的理论重建——基于公开文献从第一性原理实现的 Recurrent-Depth Transformer (RDT)。核心假设是 Claude 可能采用**循环深度结构**：不是堆叠数百个唯一层，而是将部分层循环多次执行（相同权重、多次循环、更深"思考"）。架构分为三段：Prelude（标准Transformer层，执行一次）→ Recurrent Block（循环 T 次）→ Coda（标准层，执行一次），所有推理在**单次 forward pass 内的连续潜空间**中完成，无中间 token 输出。

## 设计原理

### 中心假设：Recurrent-Depth Transformer (RDT)

传统 Transformer 通过堆叠唯一层获得深度，RDT 通过**复用同一组层**获得"计算深度"：

```
Input
  ↓
[Prelude P]        — 标准 Transformer 层，执行一次
  ↓
[Recurrent Block R] — 循环 T 次（相同权重）
  ↑_______↓         (隐藏状态 h 每次循环用输入注入 e 更新)
  ↓
[Coda C]           — 标准 Transformer 层，执行一次
  ↓
Output
```

### 循环更新规则

```
h_{t+1} = A·h_t + B·e + Transformer(h_t, e)
```

- `h_t`：第 t 次循环后的隐藏状态
- `e`：来自 Prelude 的编码输入（每次循环都注入）
- `A` 和 `B`：学习到的注入参数
- 关键：`e` 在每步注入防止模型漂移，保持原始输入信号

### 注意力机制选择
支持 MLA（Multi-head Latent Attention）和 GQA（Grouped-Query Attention）两种模式切换。MLA 模式需要额外配置 `kv_lora_rank`、`q_lora_rank`、`qk_rope_head_dim` 等参数。

### 稀疏 MoE
前馈层使用稀疏 MoE（routed + shared experts），支持计算自适应的深度可变推理。

## 关键实现

### 安装与基础使用
```bash
pip install open-mythos
# Flash Attention 2（需CUDA）:
pip install open-mythos[flash]
```

```python
import torch
from open_mythos.main import OpenMythos, MythosConfig

cfg = MythosConfig(
    vocab_size=1000, dim=256, n_heads=8,
    max_seq_len=128, max_loop_iters=4,
    prelude_layers=1, coda_layers=1,
    n_experts=8, n_shared_experts=1,
    n_experts_per_tok=2, expert_dim=64,
    lora_rank=8, attn_type="mla",
    n_kv_heads=8, kv_lora_rank=32,
    q_lora_rank=64, qk_rope_head_dim=16,
    qk_nope_head_dim=16, v_head_dim=16,
)
model = OpenMythos(cfg)
logits = model(ids, n_loops=4)
```

### 模型变体规模

| 变体 | dim | Experts | expert_dim | 循环次数 | 上下文 | 最大输出 |
|------|-----|---------|------------|---------|--------|---------|
| mythos_1b | 2048 | 64 | 2048 | 16 | 4k | 4k |
| mythos_3b | 3072 | 64 | 4096 | 16 | 4k | 4k |
| mythos_10b | 4096 | 128 | 5632 | 24 | 8k | 4k |
| mythos_100b | 8192 | 256 | 13568 | 32 | 1M | 128k |
| mythos_1t | 16384 | 512 | 34560 | 64 | 1M | 128k |

### 训练配置
- 优化器：AdamW
- 数据集：FineWeb-Edu (HuggingFaceFW/fineweb-edu)
- 精度：bfloat16 (H100/A100)
- 调度：Linear warmup (2000 steps) → cosine decay
- 支持 PyTorch DDP 多GPU训练

### 谱半径验证
```python
A = model.recurrent.injection.get_A()
rho = torch.linalg.eigvals(A).abs().max().item()
# ρ(A) 必须 < 1 以保证循环稳定性
```

## 关联分析

- 与 Transformer 架构演进直接相关：参见 [Transformer-Architecture-Evolution](../sources/Transformer-Architecture-Evolution.md)
- MoE + 循环深度的组合是 [DeepSeek-V4](DeepSeek-V4.md) 等前沿模型的设计趋势
- 对理解 LLM "思考"机制有理论价值：传统 CoT 在 token 空间推理，RDT 在潜空间推理

## 可执行建议

1. **架构研究价值**：理解 RDT 架构对深入理解现代 LLM 设计很重要，即使不直接使用
2. **不建议用于生产**：这是理论重建，非官方实现，且声明与 Anthropic 无关
3. **学习循环深度机制**：`h_{t+1} = A·h_t + B·e + Transformer(h_t, e)` 这个更新公式值得深入研究，是理解"计算自适应推理"的关键
4. **谱半径约束**：`ρ(A) < 1` 的稳定性条件对理解循环网络训练有普遍意义

## 自评
| 维度 | 分数 | 权重 | 加权 |
|------|------|------|------|
| 摘要质量 | 9 | 0.25 | 2.25 |
| 技术深度 | 9 | 0.25 | 2.25 |
| 相关性 | 8 | 0.20 | 1.60 |
| 原创性 | 8 | 0.15 | 1.20 |
| 格式规范 | 9 | 0.15 | 1.35 |
| **加权总分** | | | **8.65** |

> 评分说明：摘要详细描述了RDT架构和循环机制；技术深度极高（具体到更新公式和模型变体参数）；相关性好（LLM架构理解是AI Agent开发的基础知识）；原创性体现在谱半径稳定性分析的提炼。
