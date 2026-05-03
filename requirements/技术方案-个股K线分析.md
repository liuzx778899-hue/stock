# 技术方案：个股K线分析

创建时间：2026-05-03
状态：待开发

## 1. 技术选型

| 维度 | 选择 | 理由 |
|------|------|------|
| 图表库 | **ECharts 5.x** | CDN 引入，原生 candlestick + volume + MA 支持 |
| 数据源 | 日线数据聚合 | 不重复存储，周月年线从日线实时 GROUP BY 计算 |
| 前端渲染 | templates/index.html | 8000 端口，新增个股详情页 |
| 交互 | ECharts dataZoom + tooltip | 内置缩放/平移/十字光标 |

## 2. 数据方案

### 2.1 日线聚合算法

不新建表，从 `stock_daily_kline` 实时聚合。MySQL 原生支持：

```sql
-- 周线 (按周分组)
SELECT 
    MIN(trade_date) as trade_date,
    SUBSTRING(trade_date,1,4) as year,
    WEEK(trade_date,1) as week_num,
    MAX(close) as high,
    MIN(close) as low,
    SUM(volume) as volume,
    (SELECT open FROM stock_daily_kline sd2 
     WHERE sd2.symbol=sd.symbol AND sd2.trade_date=MIN(sd.trade_date)) as open,
    (SELECT close FROM stock_daily_kline sd2 
     WHERE sd2.symbol=sd.symbol AND sd2.trade_date=MAX(sd.trade_date)) as close
FROM stock_daily_kline sd
WHERE symbol='000001'
GROUP BY YEAR(trade_date), WEEK(trade_date,1)
ORDER BY MIN(trade_date)
```

**简化方案**（推荐）：后端 Python 用 pandas 聚合，更灵活：

```python
def aggregate_kline(df, period):
    """日线聚合为周/月/年线"""
    df = df.copy()
    df['trade_date'] = pd.to_datetime(df['trade_date'])
    df = df.set_index('trade_date').sort_index()
    
    if period == 'week':
        freq = 'W'
    elif period == 'month':
        freq = 'M'
    elif period == 'year':
        freq = 'Y'
    else:
        return df  # daily, no aggregation
    
    agg = df.resample(freq).agg({
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum',
        'amount': 'sum',
    }).dropna()
    
    return agg.reset_index()
```

### 2.2 为什么不存周月年表

| 方案 | 存储 | 同步维护 | 数据一致性 |
|------|------|---------|-----------|
| 独立存储 | 3 张表 × 5000 只 | 需 4 套采集流程 | 可能与日线不一致 |
| **日线聚合** | 0 额外存储 | 无需维护 | 永远与日线一致 ✅ |

---

## 3. API 设计

### 3.1 GET /api/stock/{symbol}/kline（新增）

```
参数:
  symbol:  股票代码（必填）
  period:  day | week | month | year（默认 day）
  limit:   返回条数（默认 200，最大 800）
  end_date: 截止日期（默认今天）

返回:
{
  "symbol": "000001",
  "name": "平安银行",
  "period": "day",
  "data": [
    {
      "trade_date": "2026-04-30",
      "open": 10.98, "close": 11.00,
      "high": 11.03, "low": 10.85,
      "volume": 58271012, "amount": 637580000,
      "pct_chg": 1.85
    },
    ...
  ]
}
```

### 3.2 现有 API 复用

- `GET /api/stocks?search=xxx` — 搜索股票，已有
- 点击搜索结果 → 跳转个股详情 → 调用 kline API

---

## 4. 前端设计

### 4.1 页面结构

```
┌─────────────────────────────────────────┐
│ ← 返回列表    平安银行 000001            │
│ [日线] [周线] [月线] [年线]              │
├─────────────────────────────────────────┤
│                                         │
│         K 线图（蜡烛图 + 均线）           │
│         ┌─────────────────────┐         │
│         │   ECharts           │         │
│         │   candlestick       │         │
│         │   + MA5/MA10/MA20   │         │
│         └─────────────────────┘         │
│                                         │
│         成交量柱状图                      │
│         ████ ██ ██████ ███ ████         │
│                                         │
├─────────────────────────────────────────┤
│ 开盘: 10.98  收盘: 11.00                 │
│ 最高: 11.03  最低: 10.85                 │
│ 成交量: 5827万  涨幅: +1.85%             │
└─────────────────────────────────────────┘
```

### 4.2 ECharts 配置要点

```javascript
option = {
    grid: [
        { top: '10%', height: '55%' },     // K线区域
        { top: '70%', height: '20%' }      // 成交量区域
    ],
    xAxis: [{ gridIndex: 0 }, { gridIndex: 1 }],
    yAxis: [
        { gridIndex: 0, scale: true },     // 价格轴
        { gridIndex: 1 }                    // 成交量轴
    ],
    series: [
        { name: 'K线', type: 'candlestick', xAxisIndex: 0, yAxisIndex: 0,
          data: [[open, close, low, high], ...] },
        { name: 'MA5', type: 'line', data: [...] },
        { name: 'MA10', type: 'line', data: [...] },
        { name: 'MA20', type: 'line', data: [...] },
        { name: '成交量', type: 'bar', xAxisIndex: 1, yAxisIndex: 1,
          data: [...] }
    ],
    dataZoom: [{ type: 'inside', xAxisIndex: [0,1] }],  // 滚轮缩放
    tooltip: { trigger: 'axis' }                          // 十字光标
};
```

### 4.3 图表库引入

CDN 引入 ECharts（无需 npm install）：

```html
<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
```

---

## 5. 页面导航流程

```
股票列表页 (已有)
  │
  ├─ 每行增加"查看"按钮
  │    ↓ 点击
  ├─ 跳转个股详情页（新增 page: stock-detail）
  │    ├─ 默认显示日线
  │    ├─ 切换周期 Tab → 重新请求 API → 刷新图表
  │    └─ 返回按钮 → 回到股票列表
```

---

## 6. 修改文件清单

| 文件 | 变更 | Agent |
|------|------|-------|
| `web_app.py` | 新增 `GET /api/stock/{symbol}/kline` | develop2 |
| `templates/index.html` | 新增个股详情页 + ECharts CDN + 股票列表加"查看"按钮 | develop2 |
| `services/data_orchestrator.py` | 新增 `get_kline()` 查询 + 聚合方法 | develop1 |

## 7. 性能评估

| 操作 | 耗时 | 说明 |
|------|------|------|
| 日线查询（200条） | < 50ms | 索引查询，无聚合 |
| 周线聚合（200周） | < 200ms | pandas resample, ~800条日线输入 |
| 月线聚合（200月） | < 300ms | ~2400条日线输入 |
| 年线聚合（50年） | < 200ms | ~4000条日线输入 |
| 前端渲染 | < 500ms | ECharts 渲染 200 个蜡烛 |

## 8. 开发任务拆解

### [develop1] 后端聚合层
- [ ] T-1: `services/data_orchestrator.py` — 新增 `get_kline(symbol, period, limit, end_date)` 方法

### [develop2] API + 前端
- [ ] T-2: `web_app.py` — 新增 `GET /api/stock/{symbol}/kline` 端点
- [ ] T-3: `templates/index.html` — 新增个股详情页 + ECharts CDN + 图表渲染
- [ ] T-4: `templates/index.html` — 股票列表每行增加"查看"按钮 → 跳转详情页

## 9. 验收标准

- [ ] 日线/周线/月线/年线 Tab 全部可切换
- [ ] 蜡烛图正确显示红涨绿跌
- [ ] MA5/MA10/MA20 均线叠加显示
- [ ] 鼠标滚轮缩放 + 拖拽平移可用
- [ ] 十字光标悬停显示 OHLCV 数据
- [ ] 股票列表"查看"按钮跳转正常
