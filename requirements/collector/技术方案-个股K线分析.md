# 技术方案：个股K线分析（含技术指标）

创建时间：2026-05-03
最后更新：2026-05-04
状态：待开发

## 1. 技术指标计算公式

所有指标从 OHLCV 计算，**不需要额外采集数据**。在后端计算后随 K 线数据一起返回。

### 1.1 BOLL（布林带）

```
中轨 MID  = MA(close, 20)
上轨 UPPER = MID + 2 × STD(close, 20)
下轨 LOWER = MID - 2 × STD(close, 20)
```

叠加在 K 线主图上，用浅色半透明区域表示。

### 1.2 MACD

```
EMA12 = EMA(close, 12)
EMA26 = EMA(close, 26)
DIF   = EMA12 - EMA26
DEA   = EMA(DIF, 9)
MACD柱 = 2 × (DIF - DEA)    // 正值为红柱，负值为绿柱
```

### 1.3 RSI

```
RSI(N) = 100 - 100 / (1 + RS)
其中 RS = avg_gain(N) / avg_loss(N)
  - avg_gain = N日内涨幅均值
  - avg_loss = N日内跌幅均值（取绝对值）
```

返回 RSI6、RSI12、RSI24 三条线。超买线 70（红虚线），超卖线 30（绿虚线）。

### 1.4 MA（移动平均线）

```
MA5 = SMA(close, 5)    // 白色
MA10 = SMA(close, 10)  // 黄色
MA20 = SMA(close, 20)  // 紫色
MA60 = SMA(close, 60)  // 绿色
```

---

## 2. 数据方案

### 2.1 不存冗余数据

周/月/年线从日线 pandas `resample()` 聚合。技术指标在后端用 pandas 实时计算。

### 2.2 完整数据链路

```
stock_daily_kline (已有日线数据)
  │
  ├─ period=day  → 直接查询 → 计算 BOLL + MACD + RSI + MA
  ├─ period=week → resample('W') → 同上计算
  ├─ period=month → resample('M') → 同上计算
  └─ period=year → resample('Y') → 同上计算
```

---

## 3. API 设计

### 3.1 GET /api/stock/{symbol}/kline

```
参数:
  symbol:  股票代码（必填）
  period:  day | week | month | year（默认 day）
  limit:   返回条数（默认 200，最大 800）

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
      "pct_chg": 1.85,
      "ma5": 10.85, "ma10": 10.72, "ma20": 10.56, "ma60": 10.18,
      "boll_mid": 10.56, "boll_upper": 11.20, "boll_lower": 9.92,
      "macd_dif": 0.083, "macd_dea": 0.052, "macd_bar": 0.062,
      "rsi6": 62.5, "rsi12": 55.3, "rsi24": 52.1
    },
    ...
  ]
}
```

### 3.2 后端计算实现（Python pandas）

```python
def calc_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """计算所有技术指标"""
    close = df['close'].astype(float)
    high = df['high'].astype(float)
    low = df['low'].astype(float)
    
    # MA
    for n in [5, 10, 20, 60]:
        df[f'ma{n}'] = close.rolling(n).mean()
    
    # BOLL
    df['boll_mid'] = close.rolling(20).mean()
    std20 = close.rolling(20).std()
    df['boll_upper'] = df['boll_mid'] + 2 * std20
    df['boll_lower'] = df['boll_mid'] - 2 * std20
    
    # MACD
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    df['macd_dif'] = ema12 - ema26
    df['macd_dea'] = df['macd_dif'].ewm(span=9, adjust=False).mean()
    df['macd_bar'] = 2 * (df['macd_dif'] - df['macd_dea'])
    
    # RSI
    for n in [6, 12, 24]:
        delta = close.diff()
        gain = delta.where(delta > 0, 0.0)
        loss = (-delta).where(delta < 0, 0.0)
        avg_gain = gain.rolling(n).mean()
        avg_loss = loss.rolling(n).mean()
        rs = avg_gain / avg_loss
        df[f'rsi{n}'] = 100 - 100 / (1 + rs)
    
    return df.round(4)
```

---

## 4. ECharts 四面板布局

参照同花顺，4 个 grid 面板：

```javascript
option = {
    grid: [
        { top: '5%',  height: '42%' },   // 主图: K线 + BOLL + MA
        { top: '52%', height: '14%' },   // 副图1: VOL
        { top: '70%', height: '14%' },   // 副图2: MACD
        { top: '88%', height: '10%' }    // 副图3: RSI
    ],
    series: [
        // 主图 grid[0]
        { name: 'K线', type: 'candlestick', xAxisIndex: 0, yAxisIndex: 0 },
        { name: 'MA5', type: 'line', xAxisIndex: 0, yAxisIndex: 0, color: '#fff' },
        { name: 'MA10', type: 'line', xAxisIndex: 0, yAxisIndex: 0, color: '#ff0' },
        { name: 'MA20', type: 'line', xAxisIndex: 0, yAxisIndex: 0, color: '#f0f' },
        { name: 'MA60', type: 'line', xAxisIndex: 0, yAxisIndex: 0, color: '#0f0' },
        { name: 'BOLL上轨', type: 'line', xAxisIndex: 0, yAxisIndex: 0 },
        { name: 'BOLL中轨', type: 'line', xAxisIndex: 0, yAxisIndex: 0 },
        { name: 'BOLL下轨', type: 'line', xAxisIndex: 0, yAxisIndex: 0 },
        // 副图1 grid[1]
        { name: 'VOL', type: 'bar', xAxisIndex: 1, yAxisIndex: 1 },
        // 副图2 grid[2]
        { name: 'MACD柱', type: 'bar', xAxisIndex: 2, yAxisIndex: 2 },
        { name: 'DIF', type: 'line', xAxisIndex: 2, yAxisIndex: 2, color: '#fff' },
        { name: 'DEA', type: 'line', xAxisIndex: 2, yAxisIndex: 2, color: '#ff0' },
        // 副图3 grid[3]
        { name: 'RSI6', type: 'line', xAxisIndex: 3, yAxisIndex: 3, color: '#fff' },
        { name: 'RSI12', type: 'line', xAxisIndex: 3, yAxisIndex: 3, color: '#ff0' },
        { name: 'RSI24', type: 'line', xAxisIndex: 3, yAxisIndex: 3, color: '#f0f' },
        // 参考线
        { name: '超买70', type: 'line', xAxisIndex: 3, yAxisIndex: 3, 
          markLine: { yAxis: 70 }, lineStyle: { color: 'red', type: 'dashed' } },
        { name: '超卖30', type: 'line', xAxisIndex: 3, yAxisIndex: 3,
          markLine: { yAxis: 30 }, lineStyle: { color: 'green', type: 'dashed' } },
    ],
    dataZoom: [
        { type: 'inside', xAxisIndex: [0,1,2,3] },   // 四面板联动缩放
        { type: 'slider', xAxisIndex: [0,1,2,3], bottom: 0 }  // 底部滑块
    ],
    tooltip: { trigger: 'axis' }  // 十字光标联动
};
```

---

## 5. 修改文件清单

| 文件 | 变更 | Agent |
|------|------|-------|
| `services/data_orchestrator.py` | `get_kline()` 增加指标计算（calc_indicators） | develop1 |
| `web_app.py` | `GET /api/stock/{symbol}/kline` 返回含指标字段 | develop2 |
| `templates/index.html` | 个股详情页：四面板 ECharts + CDN 引入 | develop2 |

## 6. 性能评估

| 操作 | 耗时 | 说明 |
|------|------|------|
| 日线 800 条 + 全部指标 | < 100ms | pandas 向量化计算 |
| 周线 200 条 + 聚合 + 指标 | < 200ms | resample + 计算 |
| ECharts 四面板渲染 | < 800ms | 800 数据点 |
| 总计首屏加载 | < 1.5 秒 | 达到目标 |

## 7. 开发任务拆解

### [develop1] 后端计算层
- [ ] T-1: `services/data_orchestrator.py` — `get_kline()` 增加 `calc_indicators()` 方法

### [develop2] API + 前端
- [ ] T-2: `web_app.py` — `GET /api/stock/{symbol}/kline` 返回指标字段
- [ ] T-3: `templates/index.html` — 四面板 ECharts（K线BOLL+MA / VOL / MACD / RSI）
- [ ] T-4: `templates/index.html` — 股票列表增加"查看"按钮

## 8. 验收标准

- [ ] K线蜡烛图 + BOLL(3线) + MA(4线) 正确叠加在主图
- [ ] 成交量 VOL 红涨绿跌与 K 线颜色同步
- [ ] MACD 含 DIF(白)/DEA(黄) + 红绿柱
- [ ] RSI 含 RSI6/RSI12/RSI24 + 30/70 参考虚线
- [ ] 四面板 dataZoom 联动（缩放/平移同步）
- [ ] 十字光标在所有面板中同步移动
- [ ] 日K/周K/月K/年K 切换后指标重新计算
