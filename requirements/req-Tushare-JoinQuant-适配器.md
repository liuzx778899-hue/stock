# 需求文档：Tushare Pro + JoinQuant K线数据源适配器
创建时间：2026-05-07
状态：待开发
关联 Issue: #159

## 背景

当前5个免费数据源均存在严重限制：
- baostock: 速率限制，日成功率<2%
- mootdx: TCP覆盖有限，9228只股票空数据
- eastmoney/sina: 反爬阻断
- 北交所920xxx: 无Provider支持
- 日采集4592只股票所有源全失败

## 目标

新增 Tushare Pro 和 JoinQuant 两个 HTTP API 数据源，提升K线采集覆盖率和稳定性。

## 涉及文件

| 文件 | 改动 |
|------|------|
| modules/collector/adapters/tushare_provider.py | 新增，实现 DataProvider 接口 |
| modules/collector/adapters/jqdata_provider.py | 新增，实现 DataProvider 接口 |
| modules/collector/providers.yaml | 注册两个新Provider，调整回退链 |
| requirements.txt | 新增 tushare / jqdatasdk |

## Tushare Pro

| 项目 | 说明 |
|------|------|
| 覆盖 | A股全市场含北交所，日/周/月/分钟线，前复权 |
| 费用 | 免费注册送积分，付费 200-500/年 |
| SDK | `pip install tushare` |
| 字段 | ts_code, trade_date, open, high, low, close, pre_close, vol, amount |

## JoinQuant（降级源）

| 项目 | 说明 |
|------|------|
| 覆盖 | 全A股（不含北交所），日K线 |
| 费用 | 免费，每日额度限制 |
| SDK | `pip install jqdatasdk` |
| 字段 | 日期, open, close, high, low, volume, money |

## 回退链

```
tushare → jqdata → mootdx → baostock → eastmoney → sina → tencent
  (付费)   (免费)    (TCP)   (HTTP)     (HTTP)     (HTTP)  (HTTP)
```

## 验收标准

- [ ] tushare_provider: 实现 fetch_kline()，字段覆盖 OHLCV + amount
- [ ] jqdata_provider: 实现 fetch_kline()，字段覆盖 OHLCV
- [ ] 两者通过 DataProvider 基类注册，health_check() 可用
- [ ] providers.yaml 排入回退链
- [ ] 北交所股票可通过 tushare 获取K线

## 不做的事

- 不修改现有 Provider
- 不修改 data_orchestrator 回退逻辑（已有框架自动适配）
