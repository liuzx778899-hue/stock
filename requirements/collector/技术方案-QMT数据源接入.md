# 技术方案：QMT 数据源接入

创建时间：2026-05-12
状态：待开发
PM Agent 输出

---

## 背景

QMT（国信iQuant）是券商直连交易所的数据源，API 测试已验证可覆盖 64 个数据接口。核心约束：QMT 策略只能在 iQuant GUI 内运行，无法被外部 Python 调用。

## 目标

将 QMT 接入数据采集系统，作为最高优先级数据源，覆盖 K线/财务/股本/股东/实时行情等数据类别。

## 架构设计

采用"数据库桥接"模式：

```
QMT GUI (iQuant 策略环境)                系统侧 (Stock 项目)
                                        
qmt_pump_kline.py ──────┐               QMTProvider (只读适配器)
qmt_pump_financial.py ───┤  pymysql         ├── 声明 12 类数据能力
qmt_pump_shareholder.py ──┤  直写           ├── 从 OB 表 SELECT
qmt_pump_basic.py ───────┤  OceanBase      └── priority=0 最高级
qmt_pump_tick.py ────────┘               
qmt_pump_longhubang.py ───┘               DataOrchestrator
                                              └── QMT有数据用QMT
                                              └── 无数据降级 tushare/eastmoney
```

## 数据库扩展

### 新增表（13张）

| 表名 | 用途 | 关键字段 |
|------|------|---------|
| stock_daily_basic | 每日基础指标 | total_share, circ_share, total_mv, circ_mv, turnover_rate |
| stock_financial_income | 利润表 | operating_revenue, oper_profit, net_profit, basic_eps |
| stock_financial_balance | 资产负债表 | total_assets, fix_assets, total_liabilities, total_equity |
| stock_financial_cashflow | 现金流量表 | net_cash_flows_oper_act, net_cash_flows_inv_act, net_cash_flows_fin_act |
| stock_financial_per_share | 每股指标 | eps, bvps, revenue_per_share, oper_profit_per_share |
| stock_shareholder_top10 | 十大股东/流通股东 | holder_name, hold_amount, hold_ratio, holder_rank, holder_type |
| stock_shareholder_count | 股东户数 | holder_num |
| stock_st_status | ST状态 | st_type, is_st, start_date, end_date |
| stock_ipo_info | IPO信息 | ipo_date, issue_price, issue_amount, raise_amount |
| stock_tick_data | Tick明细 | trade_time, price, volume, amount, trade_type |
| stock_longhubang | 龙虎榜 | direction, rank, sales_department, amount, net_amount |
| stock_realtime_depth | 五档盘口 | bid_price/vol 1-5, ask_price/vol 1-5 |
| qmt_pump_checkpoint | 断点续传 | pump_name, current_index, total_count, last_code, status |

## QMT 数据泵脚本

所有脚本统一规范：`#coding:gbk` 编码、pymysql 直连 OB、`qmt_pump_checkpoint` 断点续传、`INSERT ON DUPLICATE KEY UPDATE` 幂等。

| 脚本 | 数据类别 | QMT API |
|------|---------|---------|
| qmt_pump_kline_v2.py | K线+换手率+股本+市值 | get_market_data_ex + get_turnover_rate + get_total_share + get_last_volume |
| qmt_pump_financial.py | 利润表/现金流/负债/每股指标 | get_financial_data(['表名.字段名']) |
| qmt_pump_shareholder.py | 十大股东+流通股东+股东户数 | get_top10_share_holder + get_holder_num |
| qmt_pump_basic.py | ST状态/IPO/行业 | get_st_status + get_ipo_data + BLKNAME |
| qmt_pump_tick.py | 逐笔成交 | download_history_data('tick') |
| qmt_pump_longhubang.py | 龙虎榜 | getlonghubang |

## 系统侧改动

### 适配器层
- `base.py`：扩展 DataCategory 枚举（新增 DAILY_BASIC / FINANCIAL_INCOME / FINANCIAL_BALANCE / FINANCIAL_CASHFLOW / FINANCIAL_PER_SHARE / SHAREHOLDER_TOP10 / SHAREHOLDER_COUNT / ST_STATUS / IPO_INFO / TICK_DATA / LONGHUBANG / REALTIME_DEPTH）
- `qmt_provider.py`：新建，只读适配器，fetch_xxx 从 OB 表 SELECT
- `providers.yaml`：QMT priority=0，覆盖 kline_daily / daily_basic / financial_* / shareholder_* / st_status / ipo_info / longhubang

### 采集器层
- `collectors/stock_financial.py`：财务数据采集器
- `collectors/stock_shareholder.py`：股东数据采集器
- `collectors/stock_daily_basic.py`：每日基础指标采集器

### 编排器层
- `services/data_orchestrator.py`：新增 collect_financial / collect_shareholders / collect_daily_basic 方法
- `main.py`：新增 collect_financial / collect_shareholders 入口

## QMT API 确认状态

### 已验证通过

| API | 返回 | 备注 |
|-----|------|------|
| get_market_data_ex([...], code, '1d') | DataFrame (OHLCV+额) | K线全字段 |
| get_turnover_rate([code], start, end) | DataFrame | 日换手率，需下载股本数据 |
| get_total_share(code) | int | 总股本(股) |
| get_last_volume(code) | int | 流通股本(股) |
| get_financial_data(['表.字段'], [code], start, end) | DataFrame | 四大财务表 |
| get_full_tick([code]) | dict | 实时价+五档盘口 |
| get_top10_share_holder([code], 'holder'/'flow_holder', start, end) | DataFrame | 十大股东 |
| get_holder_num([code], start, end) | DataFrame | 股东户数(表头有，数据空) |
| download_history_data(code, 'tick', start, end) | OK | 逐笔数据下载成功 |
| get_stock_list_in_sector('沪深A股') | list | 全A股代码 |
| get_ipo_data(code) | dict | IPO信息 |
| get_st_status(code) | dict | ST状态 |
| BLKNAME | string | 申万行业名称 |

### QMT 缺失数据（7项，不做）

业绩预告/分红/增发/解禁限售/高管历史/董事会历史/基金持股

## 涉及文件

| 文件 | 操作 |
|------|------|
| common/models.py | 新增 13 张表模型 |
| modules/collector/adapters/base.py | 扩展 DataCategory + 标准字段 |
| modules/collector/adapters/qmt_provider.py | 新建 QMTProvider |
| modules/collector/providers.yaml | 注册 QMT，设置 priority=0 |
| modules/collector/services/data_orchestrator.py | 新增采集方法 |
| modules/collector/collectors/stock_financial.py | 新建 |
| modules/collector/collectors/stock_shareholder.py | 新建 |
| modules/collector/collectors/stock_daily_basic.py | 新建 |
| main.py | 新增入口 |
| requirements/collector/qmt_pump_kline_v2.py | 新建（QMT侧） |
| requirements/collector/qmt_pump_financial.py | 新建（QMT侧） |
| requirements/collector/qmt_pump_shareholder.py | 新建（QMT侧） |
| requirements/collector/qmt_pump_basic.py | 新建（QMT侧） |
| requirements/collector/qmt_pump_tick.py | 新建（QMT侧） |
| requirements/collector/qmt_pump_longhubang.py | 新建（QMT侧） |

## 开发顺序

1. **Phase 1**：数据库建表（common/models.py）
2. **Phase 2**：QMT 数据泵脚本（requirements/collector/）
3. **Phase 3**：QMTProvider 适配器 + base.py 扩展
4. **Phase 4**：采集器 + 编排器 + main.py 入口
5. **Phase 5**：端到端验证

## 验收标准

- [ ] 13 张新表在 OceanBase 创建成功
- [ ] 6 个 QMT pump 脚本在 iQuant 内运行通过，checkpoint.status=completed
- [ ] QMTProvider 适配器能从 DB 读取所有 12 类数据
- [ ] 编排器在 QMT 无数据时自动降级到 tushare/eastmoney
- [ ] `pytest tests/ -v` 全部通过（无回归）
- [ ] QMT 换手率数据与同花顺一致（300253=7.94%）
