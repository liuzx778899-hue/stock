# 技术方案：概念板块 Hover Tooltip

创建时间：2026-05-05
关联需求：req-concept-tooltip.md

## 涉及文件

| 文件 | 改动 |
|------|------|
| `templates/index.html` | 概念标签添加 tooltip 交互 |
| `frontend/src/views/Dashboard.vue` | 添加概念列 + tooltip（当前 Vue 前端未展示概念） |
| `frontend/src/api/index.js` | 确认 API 已返回 concepts 字段（无需改动） |

## 实现方案

### 模板前端（templates/index.html）

**现状**：概念标签行内渲染，`s.concepts` 数组已就绪，最多展示 4 个 + `+N`。

**方案**：CSS 纯原生 tooltip

```
<span class="concept-tag" data-tooltip="锂电,新能源车,储能,...">锂电池</span>
<span class="concept-tag concept-more" data-tooltip="锂电,新能源车,储能,...">+3</span>
```

- 每个概念标签加 `data-tooltip` 属性，值为全部概念（逗号分隔）
- CSS `::after` 伪元素渲染 tooltip，`position: absolute` 定位在标签上方
- hover 时 `opacity: 0 → 1`，带 200ms 过渡

**CSS 关键规则**：
```css
.concept-tag { position: relative; cursor: pointer; }
.concept-tag:hover::after {
  content: attr(data-tooltip);
  position: absolute; bottom: 100%; left: 50%;
  transform: translateX(-50%);
  background: #333; color: #fff;
  padding: 6px 12px; border-radius: 4px;
  white-space: nowrap; font-size: 12px;
  z-index: 1000;
}
```

**JS 改动**：渲染标签时拼接完整概念列表写入 `data-tooltip`：`s.concepts.join('、')`。

### Vue 前端（frontend/）

**现状**：Dashboard.vue 不展示概念板块列。

**方案**：

1. **Dashboard.vue 表格加"概念板块"列**：渲染概念标签，逻辑同模板前端
2. **Tooltip 方案二选一**：
   - 方案 A：同样用 CSS `::after` + `data-tooltip`（轻量，无依赖）
   - 方案 B：用 `<el-tooltip>`（Element Plus 自带，功能更完善，但需确认已安装）

**推荐方案 A**（与模板前端一致，零依赖）。

### 边界情况

- 概念数 ≤4：标签逐个展示，hover 任一标签仍显示全部（统一行为）
- 无概念：显示 `-`，无 tooltip
- 概念名含特殊字符：`attr()` 自动转义，无需额外处理
- 长 tooltip 换行：概念超过 8 个时改为 `white-space: normal; max-width: 200px;`

## 不涉及

- 后端 API（概念数据已通过 `/api/stocks` 的 `concepts` 字段返回）
- 概念详情页
- 搜索过滤逻辑
