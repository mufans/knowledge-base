# Pretext.js: 绕过 DOM 布局重排的高性能文本排版

> 作者：Cheng Lou（Midjourney 工程师、前 React 核心团队成员）
> 仓库：https://github.com/chenglou/pretext
> 大小：仅 15KB | 许可：开源

## 核心问题

Web 应用中，以下场景需要计算文本高度：
- **虚拟列表**：动态计算每行高度以实现虚拟滚动
- **瀑布流布局**：不同宽度的卡片需要精确的高度
- **AI 聊天界面**：气泡高度动态变化，需要锚定滚动位置

传统做法调用 `getBoundingClientRect()` 或 `offsetHeight`，这会触发浏览器的**布局重排（reflow）**——渲染引擎被迫重新计算所有元素的几何信息。在复杂页面或高频操作下，帧率直接崩到 30fps 以下。

## 设计原理

Pretext 的核心洞察：**文本测量可以完全脱离 DOM，用纯数学完成**。

### 两阶段架构

```
prepare() 阶段（一次性成本）：
  Canvas.measureText() → 逐段文本像素宽度 → 缓存到内存

layout() 阶段（高频调用）：
  缓存宽度 + 容器尺寸 → 纯数学计算 → 行数 + 最终高度
```

**关键**：两个阶段都不读 DOM，零 reflow。

### 为什么 Canvas.measureText() 不触发 reflow？

Canvas 是一个离屏绘制 API，`measureText()` 只查询字体度量信息（glyph advance width、ascent、descent），不涉及 DOM 树的布局计算。浏览器的字体缓存保证了这个操作的开销极低。

## 性能数据

- 500 个文本块布局计算：**0.09ms**（Pretext）vs ~55ms（传统 DOM 方法）
- **最高 600 倍性能提升**
- 在实时文本换行场景下稳定维持 **120 FPS**

## 技术实现要点

### 基本用法

```typescript
import { prepare, layout } from 'pretext';

// 1. 准备阶段：测量文本（只需一次）
const blocks = [
  { id: 1, text: '这是一段需要测量高度的文本', font: '14px sans-serif' },
  { id: 2, text: '另一段文本，可能换行', font: '14px sans-serif' },
];
await prepare(blocks);

// 2. 布局阶段：根据容器宽度计算高度（可反复调用）
const containerWidth = 300;
const results = layout(blocks, containerWidth);
// results: [{ id: 1, height: 38, lines: 2 }, { id: 2, height: 19, lines: 1 }]
```

### 虚拟列表中的应用

```typescript
// 关键：resize 时无需重新 prepare，只需重新 layout
useEffect(() => {
  const observer = new ResizeObserver(entries => {
    const width = entries[0].contentRect.width;
    const heights = layout(cachedBlocks, width);  // 0.09ms 级别
    updateVirtualList(heights);
  });
  observer.observe(containerRef.current);
  return () => observer.disconnect();
}, []);
```

### 与 CSS 方案的对比

| 方案 | 多语言支持 | RTL | 性能 | 容器自适应 |
|------|-----------|-----|------|-----------|
| CSS Grid Masonry | 部分 | 部分 | 好（原生） | 需要 resize 重算 |
| CSS overflow-anchor | N/A | N/A | 好 | 有限 |
| JS + getBoundingClientRect | 完整 | 完整 | 差（reflow） | 灵活但慢 |
| **Pretext.js** | **完整** | **完整** | **极好** | **灵活且快** |

## AI 辅助开发的典范

Pretext 的多语言支持（韩语、阿拉伯语 RTL、emoji 混排）是通过 **AI 循环** 完成的：

> 将浏览器的真实渲染结果作为基准，交给 Claude 和 Codex，在不同容器宽度下反复测量与迭代，持续数周。

这是一个"以现有软件行为为 ground truth"的 AI 开发范式——不是让 AI 凭空生成代码，而是用真实浏览器渲染结果作为验证标准，让 AI 通过试错逼近正确实现。

## 对移动端开发的启示

### 1. React Native 的类似痛点
RN 中的 `onLayout` 回调本质上和 DOM reflow 类似——需要等原生渲染完成才能拿到尺寸。Pretext 的思路启发了一个方向：**能否在 JS 层用文本度量预计算布局，减少原生测量次数？**

### 2. 性能优化的新层级
传统前端性能优化聚焦在：
- 减少 DOM 操作（虚拟 DOM）
- 减少重排重绘（批量更新、will-change）
- 虚拟滚动（只渲染可见区域）

Pretext 开辟了第四个层级：**绕过布局引擎本身**。这对追求极致性能的移动端 Web 应用（PWA、小程序 WebView）有直接参考价值。

### 3. 鸿蒙场景
鸿蒙的声明式 UI 也有类似的布局测量机制。如果能在 ArkUI 中实现类似的文本预计算，可以显著提升长列表场景的帧率。

## 参见
- [Real-world AI Applications](#Real-world AI Applications) — AI 辅助开发的实际案例
