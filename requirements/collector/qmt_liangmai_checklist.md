# QMT vs 量脉 逐项对照表

## 一、已验证通过 ✅ (15项)

| # | 量脉接口 | QMT实现 | 备注 |
|---|---------|---------|------|
| 1 | hs_list_main 股票列表 | `get_stock_list_in_sector('沪深A股')` | |
| 2 | sector_constituents 板块成分股 | `get_stock_list_in_sector(板块名)` | |
| 3 | 日K线 quote_bars | `get_market_data_ex([...], code, period='1d')` | 字段: open/high/low/close/volume/amount/pre_close |
| 4 | 换手率 | `vol × 100 / get_last_volume × 100` | 已验证300253=7.94% √ |
| 5 | 总股本 zgb | `get_total_share(code)` | 300253=2201270000 |
| 6 | 流通股本 ltg | `get_last_volume(code)` | 300253=1810500000 |
| 7 | 涨跌幅 pct_chg | `(close-pre_close)/pre_close×100` | 从K线计算 |
| 8 | 实时行情 stock_realtime | `get_market_data_ex` | |
| 9 | 多股实时 | `get_market_data_ex([多股])` | |
| 10 | 指数列表 index_list | `get_stock_list_in_sector(指数板块)` | |
| 11 | 指数实时/历史K线 | `get_market_data_ex(指数代码)` | |
| 12 | 京市列表/实时 | `get_stock_list_in_sector('北证A股')` | DAT文件确认存在 |
| 13 | 科创列表/实时 | `get_stock_list_in_sector('科创板')` | |
| 14 | 流通市值 | `get_last_volume × close` | |
| 15 | 总市值 | `get_total_share × close` | |

---

## 二、函数已找到，需跑测试确认 🔧 (22项)

> 跑 `qmt_ext_data_test.py` 即可批量验证

| # | 量脉接口 | QMT函数 | 测试要点 |
|---|---------|---------|---------|
| 1 | IPO日历 ipo_calendar | `get_ipo_data` | 返什么字段？历史还是未来？ |
| 2 | ST状态 | `get_st_status` | 返L/D/P/N？ |
| 3 | 行业名称 | `get_industry_name_of_stock` | 返什么行业分类？ |
| 4 | 板块树 sector_tree | `get_sector_list` | 返回层级结构？ |
| 5 | 股票所属板块 stock_sectors | `get_sector_list` 或 `get_industry_name_of_stock` | |
| 6 | 十大股东 | `get_top10_holder` | 字段: 股东名/持股数/比例？ |
| 7 | 股东人数 | `get_holder_number` | 历史序列还是最新？ |
| 8 | 逐笔成交 | `get_trade_detail_data` | 逐笔还是汇总？ |
| 9 | **利润表** fin_income_statement | `get_financial_data('ASHAREINCOME', ...)` 或 `ext_data` | 48字段能取哪些？ |
| 10 | **现金流量表** fin_cashflow_statement | `get_financial_data('ASHARECASHFLOW', ...)` | 78字段能取哪些？ |
| 11 | **资产负债表** fin_balance_sheet | `get_financial_data('ASHAREBALANCESHEET', ...)` | 96字段能取哪些？ |
| 12 | **每股指标** fin_per_share_index | `get_financial_data('PERSHAREINDEX', ...)` | EPS/BVPS等31字段 |
| 13 | 财务指标85字段 | `ext_data_range` | 返什么格式？时间范围？ |
| 14 | 季度利润 | `get_financial_data('ASHAREINCOME', ...)` | 季度还是年度？ |
| 15 | 季度现金流 | `get_financial_data('ASHARECASHFLOW', ...)` | |
| 16 | 业绩预告 | `ext_data` | 有没有这个表？ |
| 17 | 分红 history | `ext_data` | 有无 DIVIDEND 表？ |
| 18 | 增发 history | `ext_data` | 有无 SEO 表？ |
| 19 | 公司简介 profile | `get_financial_data` | |
| 20 | 涨跌停价格 | `stopprice(1)` / `stopprice(2)` | 全局函数，需确认签名 |
| 21 | ETF信息 | `get_etf_info` / `get_etf_iopv` | |
| 22 | get_turnover_rate API | `ContextInfo.get_turnover_rate` | 下载股本后应可用 |

---

## 三、可从K线派生计算 ⚠️ (10项)

| # | 量脉接口 | 派生方式 |
|---|---------|---------|
| 1 | MACD | pandas计算，已有函数 |
| 2 | MA均线(3/5/10/20/30/60/120/200/250) | pandas rolling |
| 3 | BOLL | pandas计算 |
| 4 | KDJ | pandas计算 |
| 5 | 涨停股池 | K线 pct_chg ≥ 9.8% 筛选 |
| 6 | 跌停股池 | K线 pct_chg ≤ -9.8% 筛选 |
| 7 | 强势股池 | 多周期涨幅+量比筛选 |
| 8 | 次新股池 | 上市日期 < N天 筛选 |
| 9 | 炸板股池 | 盘中触及涨停但收盘跌落 |
| 10 | 行情指标(量比/涨速/换手) | 从K线+volume计算 |

---

## 四、待确认是否缺失 ❌ (4项)

| # | 量脉接口 | 说明 |
|---|---------|------|
| 1 | 资金流向 capital_flow_history (81字段) | QMT函数列表未发现，可能在ContextInfo里 |
| 2 | 高管/董事会/监事会历史 | QMT可能有但未找到对应函数 |
| 3 | 解禁限售 company_unlock | 限售股解禁计划 |
| 4 | 基金持股 | QMT有 get_etf_info 但不一定有基金持仓数据 |

---

## 五、QMT独有，量脉没有 🔥 (5项)

| # | QMT函数 | 功能 |
|---|---------|------|
| 1 | `get_chip_distribution` / `get_chips_price` / `get_winner_chips` | 筹码分布/成本分析 |
| 2 | `get_bond_*` 系列(10+个) | 债券到期/付息/评级/类型 |
| 3 | `get_etf_iopv` / `get_product_net_value` | ETF实时净值/申赎 |
| 4 | `turnover_rate` (独立函数) | 换手率全局版本 |
| 5 | `get_hkt_exchange_rate` | 港股汇率 |

---

## 下一步

**先跑 `qmt_ext_data_test.py`**，把第二组 22 项批量确认。需要你：
1. iQuant 下载**财务数据+股本数据**
2. 策略设 300253.SZ 日线
3. 跑脚本，贴输出
