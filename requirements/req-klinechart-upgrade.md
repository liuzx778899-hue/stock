# 技术方案：KLineChart 同花顺级 K 线图

创建时间：2026-05-04
参照效果图：`requirements/K线图/微信图片_202605040203*.jpg`

## 1. 方案

用 **KLineChart Pro** 替换当前 ECharts，CDN 引入，纯前端改造，后端 API 不变。

```
当前：ECharts (通用图表库，白色底，200行配置)
  ↓
目标：KLineChart (专业K线库，深色底，80行配置，开箱即同花顺)
```

## 2. CDN 引入

```html
<script src="https://unpkg.com/@klinecharts/pro/dist/klinecharts-pro.umd.js"></script>
```

## 3. 数据转换

后端 `GET /api/stock/{symbol}/kline` **不变**，前端转格式：

```javascript
function toKLineData(apiData) {
    return apiData.map(d => ({
        timestamp: new Date(d.trade_date + 'T15:00:00').getTime(),
        open: +d.open, high: +d.high, low: +d.low, close: +d.close,
        volume: Math.round(+d.volume / 100),   // 股→手
        turnover: +d.amount || 0
    }));
}
```

## 4. 配置（对标效果图）

```javascript
const chart = klinecharts.init('kline-container', {
    styles: {
        grid: {
            horizontal: { color: '#2a2e3f', style: 1 },  // 虚线网格
            vertical: { color: '#2a2e3f', style: 1 }
        },
        candle: {
            bar: {
                upColor: '#EF5350', downColor: '#26A69A',        // 红涨绿跌
                upBorderColor: '#EF5350', downBorderColor: '#26A69A',
                upWickColor: '#EF5350', downWickColor: '#26A69A',
                noChangeColor: '#888888'
            }
        },
        crosshair: { show: true },
        xAxis: { tickText: { color: '#9298b4' } },
        yAxis: { tickText: { color: '#9298b4' } }
    },
    periods: [
        { multiplier: 1, timespan: 'day', text: '日K' },
        { multiplier: 1, timespan: 'week', text: '周K' },
        { multiplier: 1, timespan: 'month', text: '月K' },
        { multiplier: 1, timespan: 'year', text: '年K' }
    ]
});

// 主图指标
chart.createIndicator('MA', { id: 'candle_pane',
    styles: { lines: [{color:'#F5F5F5'},{color:'#FBC02D'},{color:'#BA68C8'},{color:'#66BB6A'}] }
});

// 副图面板
chart.createPane({ id: 'vol_pane', height: 120 });
chart.createPane({ id: 'macd_pane', height: 120 });
chart.createPane({ id: 'rsi_pane', height: 120 });

// 副图指标
chart.createIndicator('VOL', { id: 'vol_pane' });
chart.createIndicator('MACD', { id: 'macd_pane' });
chart.createIndicator('RSI', { id: 'rsi_pane' });
```

## 5. 后端简化

删除 `services/data_orchestrator.py` 中的 `_calc_indicators()`——KLineChart 内置所有指标计算。API 只返回 OHLCV 原始数据。

## 6. 修改文件

| 文件 | 变更 | Agent |
|------|------|-------|
| `templates/index.html` | CDN 换 KLineChart + 深色主题配置 | develop2 |
| `services/data_orchestrator.py` | 移除 `_calc_indicators()` | develop1 |

## 7. 验收标准

- [ ] 深色主题，蜡烛红涨绿跌
- [ ] 四面板：主图 / VOL / MACD / RSI
- [ ] 日K/周K/月K/年K 切换
- [ ] 十字光标全面板联动
- [ ] 缩放拖拽流畅
