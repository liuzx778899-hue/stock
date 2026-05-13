"""
数据库模型 - SQLAlchemy ORM 定义
"""
from datetime import datetime, date
from decimal import Decimal
from sqlalchemy import (
    Column, String, Text, BigInteger, Integer, Numeric, Date, DateTime,
    Index, UniqueConstraint, text, JSON
)
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class StockBasic(Base):
    """股票基础信息表"""
    __tablename__ = 'stock_basic'
    __table_args__ = (
        UniqueConstraint('ts_code', name='uk_stock_basic_ts_code'),
        Index('idx_stock_basic_symbol', 'symbol'),
        Index('idx_stock_basic_list_status', 'list_status'),
        {'comment': 'A股股票基础信息表'}
    )

    ts_code = Column(String(20), primary_key=True, comment='TS代码（如 000001.SZ）')
    symbol = Column(String(10), nullable=False, comment='股票代码')
    name = Column(String(50), nullable=False, comment='股票名称')
    area = Column(String(20), comment='地域')
    industry = Column(String(50), comment='所属行业')
    market = Column(String(10), comment='市场类型（主板/创业板/科创板等）')
    list_date = Column(Date, comment='上市日期')
    list_status = Column(String(2), default='L', comment='上市状态：L上市 D退市 P暂停上市')
    delist_date = Column(Date, comment='退市日期')
    is_hs = Column(String(2), comment='是否沪深港通标的：H沪股通 S深股通 N否')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')


class StockDailyKline(Base):
    """股票日K线数据表（前复权）"""
    __tablename__ = 'stock_daily_kline'
    __table_args__ = (
        UniqueConstraint('ts_code', 'trade_date', name='uk_kline_code_date'),
        Index('idx_kline_trade_date', 'trade_date'),
        Index('idx_kline_code_date', 'ts_code', 'trade_date'),
        {'comment': 'A股股票日K线数据表（前复权）'}
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    ts_code = Column(String(20), nullable=False, comment='TS代码')
    trade_date = Column(Date, nullable=False, comment='交易日期')
    open = Column(Numeric(12, 4), comment='开盘价')
    high = Column(Numeric(12, 4), comment='最高价')
    low = Column(Numeric(12, 4), comment='最低价')
    close = Column(Numeric(12, 4), comment='收盘价')
    pre_close = Column(Numeric(12, 4), comment='昨收价')
    volume = Column(BigInteger, comment='成交量（手）')
    amount = Column(Numeric(20, 4), comment='成交额（千元）')
    turnover_rate = Column(Numeric(10, 4), comment='换手率（%）')
    pct_chg = Column(Numeric(10, 4), comment='涨跌幅（%）')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')


class StockRealtimeQuote(Base):
    """股票实时行情表"""
    __tablename__ = 'stock_realtime_quote'
    __table_args__ = (
        Index('idx_realtime_symbol', 'symbol'),
        Index('idx_realtime_time', 'update_time'),
        {'comment': 'A股股票实时行情表'}
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    symbol = Column(String(10), nullable=False, comment='股票代码')
    name = Column(String(50), comment='股票名称')
    price = Column(Numeric(12, 4), comment='当前价格')
    open = Column(Numeric(12, 4), comment='开盘价')
    high = Column(Numeric(12, 4), comment='最高价')
    low = Column(Numeric(12, 4), comment='最低价')
    pre_close = Column(Numeric(12, 4), comment='昨收价')
    volume = Column(BigInteger, comment='成交量（手）')
    amount = Column(Numeric(20, 4), comment='成交额（千元）')
    bid_price1 = Column(Numeric(12, 4), comment='买一价')
    bid_volume1 = Column(BigInteger, comment='买一量')
    ask_price1 = Column(Numeric(12, 4), comment='卖一价')
    ask_volume1 = Column(BigInteger, comment='卖一量')
    update_time = Column(DateTime, comment='行情更新时间')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')


class CollectLog(Base):
    """数据采集日志表"""
    __tablename__ = 'collect_log'
    __table_args__ = (
        Index('idx_collect_log_task_type', 'task_type'),
        Index('idx_collect_log_start_time', 'start_time'),
        {'comment': '数据采集日志表'}
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    task_name = Column(String(50), nullable=False, comment='任务名称')
    task_type = Column(String(20), nullable=False, comment='任务类型（basic/kline/realtime）')
    start_time = Column(DateTime, nullable=False, comment='开始时间')
    end_time = Column(DateTime, comment='结束时间')
    total_count = Column(Integer, default=0, comment='总数量')
    success_count = Column(Integer, default=0, comment='成功数量')
    failed_count = Column(Integer, default=0, comment='失败数量')
    status = Column(String(10), default='running', comment='状态（running/success/failed）')
    extra_info = Column(Text, comment='额外信息（JSON格式）')
    error_msg = Column(Text, comment='错误信息')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')


class DatasourceConfig(Base):
    """数据源配置表"""
    __tablename__ = 'datasource_config'
    __table_args__ = (
        Index('idx_datasource_priority', 'priority'),
        Index('idx_datasource_enabled', 'enabled'),
        {'comment': '数据源配置表'}
    )

    id = Column(String(50), primary_key=True, comment='数据源ID')
    name = Column(String(100), nullable=False, comment='数据源名称')
    type = Column(String(20), nullable=False, comment='类型')
    api_url = Column(String(500), comment='API地址')
    api_key = Column(String(500), comment='API密钥')
    auth_type = Column(String(20), default='none', comment='认证类型')
    priority = Column(Integer, default=99, comment='优先级')
    enabled = Column(Integer, default=1, comment='是否启用')
    is_builtin = Column(Integer, default=0, comment='是否内置数据源')
    description = Column(String(500), comment='描述')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')


class DataQualityReport(Base):
    """数据质量检查报告表"""
    __tablename__ = 'data_quality_report'
    __table_args__ = (
        Index('idx_quality_category_time', 'data_category', 'check_time'),
        {'comment': '数据质量检查报告表'}
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    check_time = Column(DateTime, nullable=False, comment='检查时间')
    data_category = Column(String(32), nullable=False, comment='数据类别(stock_basic|kline_daily|realtime_quote)')
    total_score = Column(Numeric(5, 1), nullable=False, comment='总分(0-100)')
    completeness_score = Column(Numeric(5, 1), nullable=False, comment='完整度分数')
    freshness_score = Column(Numeric(5, 1), nullable=False, comment='新鲜度分数')
    anomaly_score = Column(Numeric(5, 1), nullable=False, comment='异常检测分数(100=无异常)')
    completeness_detail = Column(JSON, comment='各字段覆盖率明细')
    freshness_detail = Column(JSON, comment='新鲜度明细(last_update/days_lag)')
    anomaly_detail = Column(JSON, comment='异常明细列表')
    status = Column(String(16), default='ok', comment='状态(ok|warning|critical)')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')


class Concept(Base):
    """概念板块表"""
    __tablename__ = 'concept'
    __table_args__ = (
        Index('idx_concept_stock_count', 'stock_count'),
        {'comment': '概念板块表'}
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, unique=True, comment='概念名称')
    block_type = Column(Integer, comment='通达信板块类型')
    stock_count = Column(Integer, default=0, comment='所含股票数')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')


class StockConcept(Base):
    """股票-概念关联表（多对多）"""
    __tablename__ = 'stock_concept'
    __table_args__ = (
        UniqueConstraint('symbol', 'concept_id', name='uk_stock_concept'),
        Index('idx_stock_concept_symbol', 'symbol'),
        Index('idx_stock_concept_concept_id', 'concept_id'),
        {'comment': '股票-概念关联表'}
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False, comment='股票代码')
    concept_id = Column(Integer, nullable=False, comment='概念ID')


class SystemConfig(Base):
    """系统配置表（加密存储敏感配置）"""
    __tablename__ = 'system_config'
    __table_args__ = (
        {'comment': '系统配置表（加密存储敏感配置）'}
    )

    config_key = Column(String(100), primary_key=True, comment='配置键')
    config_value = Column(Text, nullable=False, comment='配置值（JSON加密存储）')
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')


class QualityCheckRecord(Base):
    """质量检查结果记录表（按天存储）"""
    __tablename__ = 'quality_check_record'
    __table_args__ = (
        UniqueConstraint('check_date', name='uk_quality_check_date'),
        Index('idx_quality_check_date', 'check_date'),
        {'comment': '质量检查结果记录表（按天存储）'}
    )

    check_date = Column(Date, primary_key=True, comment='检查日期')
    stock_count = Column(Integer, nullable=False, default=0, comment='检查股票数')
    kline_covered = Column(Integer, nullable=False, default=0, comment='K线有数据的股票数')
    kline_missing = Column(Integer, nullable=False, default=0, comment='K线无数据的股票数')
    report_json = Column(Text, nullable=False, comment='完整报告 JSON')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')


# ========== QMT 数据源新增表 ==========

class StockDailyBasic(Base):
    """每日基础指标表"""
    __tablename__ = 'stock_daily_basic'
    __table_args__ = (
        UniqueConstraint('ts_code', 'trade_date', name='uk_daily_basic_code_date'),
        Index('idx_daily_basic_trade_date', 'trade_date'),
        Index('idx_daily_basic_code_date', 'ts_code', 'trade_date'),
        {'comment': 'A股股票每日基础指标表'}
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    ts_code = Column(String(20), nullable=False, comment='TS代码')
    trade_date = Column(Date, nullable=False, comment='交易日期')
    total_share = Column(BigInteger, comment='总股本（股）')
    circ_share = Column(BigInteger, comment='流通股本（股）')
    total_mv = Column(Numeric(20, 4), comment='总市值（元）')
    circ_mv = Column(Numeric(20, 4), comment='流通市值（元）')
    turnover_rate = Column(Numeric(10, 4), comment='换手率（%）')
    pe = Column(Numeric(12, 4), comment='市盈率')
    pb = Column(Numeric(12, 4), comment='市净率')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')


class StockFinancialIncome(Base):
    """利润表"""
    __tablename__ = 'stock_financial_income'
    __table_args__ = (
        UniqueConstraint('ts_code', 'end_date', name='uk_fin_income_code_date'),
        Index('idx_fin_income_end_date', 'end_date'),
        Index('idx_fin_income_code_date', 'ts_code', 'end_date'),
        {'comment': 'A股股票利润表'}
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    ts_code = Column(String(20), nullable=False, comment='TS代码')
    ann_date = Column(Date, comment='公告日期')
    f_ann_date = Column(Date, comment='实际公告日期')
    end_date = Column(Date, nullable=False, comment='报告期')
    operating_revenue = Column(Numeric(20, 4), comment='营业收入（元）')
    oper_cost = Column(Numeric(20, 4), comment='营业成本（元）')
    oper_profit = Column(Numeric(20, 4), comment='营业利润（元）')
    net_profit = Column(Numeric(20, 4), comment='净利润（元）')
    basic_eps = Column(Numeric(12, 4), comment='基本每股收益（元）')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')


class StockFinancialBalance(Base):
    """资产负债表"""
    __tablename__ = 'stock_financial_balance'
    __table_args__ = (
        UniqueConstraint('ts_code', 'end_date', name='uk_fin_balance_code_date'),
        Index('idx_fin_balance_end_date', 'end_date'),
        Index('idx_fin_balance_code_date', 'ts_code', 'end_date'),
        {'comment': 'A股股票资产负债表'}
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    ts_code = Column(String(20), nullable=False, comment='TS代码')
    ann_date = Column(Date, comment='公告日期')
    end_date = Column(Date, nullable=False, comment='报告期')
    total_assets = Column(Numeric(20, 4), comment='资产总计（元）')
    fix_assets = Column(Numeric(20, 4), comment='固定资产（元）')
    total_liabilities = Column(Numeric(20, 4), comment='负债合计（元）')
    total_equity = Column(Numeric(20, 4), comment='所有者权益合计（元）')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')


class StockFinancialCashflow(Base):
    """现金流量表"""
    __tablename__ = 'stock_financial_cashflow'
    __table_args__ = (
        UniqueConstraint('ts_code', 'end_date', name='uk_fin_cashflow_code_date'),
        Index('idx_fin_cashflow_end_date', 'end_date'),
        Index('idx_fin_cashflow_code_date', 'ts_code', 'end_date'),
        {'comment': 'A股股票现金流量表'}
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    ts_code = Column(String(20), nullable=False, comment='TS代码')
    ann_date = Column(Date, comment='公告日期')
    end_date = Column(Date, nullable=False, comment='报告期')
    net_cash_flows_oper_act = Column(Numeric(20, 4), comment='经营活动现金流量净额（元）')
    net_cash_flows_inv_act = Column(Numeric(20, 4), comment='投资活动现金流量净额（元）')
    net_cash_flows_fin_act = Column(Numeric(20, 4), comment='筹资活动现金流量净额（元）')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')


class StockFinancialPerShare(Base):
    """每股指标表"""
    __tablename__ = 'stock_financial_per_share'
    __table_args__ = (
        UniqueConstraint('ts_code', 'end_date', name='uk_fin_per_share_code_date'),
        Index('idx_fin_per_share_end_date', 'end_date'),
        Index('idx_fin_per_share_code_date', 'ts_code', 'end_date'),
        {'comment': 'A股股票每股指标表'}
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    ts_code = Column(String(20), nullable=False, comment='TS代码')
    ann_date = Column(Date, comment='公告日期')
    end_date = Column(Date, nullable=False, comment='报告期')
    eps = Column(Numeric(12, 4), comment='每股收益（元）')
    bvps = Column(Numeric(12, 4), comment='每股净资产（元）')
    revenue_per_share = Column(Numeric(12, 4), comment='每股营业收入（元）')
    oper_profit_per_share = Column(Numeric(12, 4), comment='每股营业利润（元）')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')


class StockShareholderTop10(Base):
    """十大股东/流通股东表"""
    __tablename__ = 'stock_shareholder_top10'
    __table_args__ = (
        UniqueConstraint('ts_code', 'ann_date', 'holder_rank', 'holder_type', name='uk_holder_top10'),
        Index('idx_holder_top10_code_date', 'ts_code', 'ann_date'),
        {'comment': 'A股股票十大股东/流通股东表'}
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    ts_code = Column(String(20), nullable=False, comment='TS代码')
    ann_date = Column(Date, nullable=False, comment='公告日期')
    holder_name = Column(String(100), comment='股东名称')
    hold_amount = Column(BigInteger, comment='持股数量（股）')
    hold_ratio = Column(Numeric(10, 4), comment='持股比例（%）')
    holder_rank = Column(Integer, comment='股东排名')
    holder_type = Column(String(20), comment='股东类型(holder/circ_holder)')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')


class StockShareholderCount(Base):
    """股东户数表"""
    __tablename__ = 'stock_shareholder_count'
    __table_args__ = (
        UniqueConstraint('ts_code', 'ann_date', name='uk_holder_count'),
        Index('idx_holder_count_code_date', 'ts_code', 'ann_date'),
        {'comment': 'A股股票股东户数表'}
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    ts_code = Column(String(20), nullable=False, comment='TS代码')
    ann_date = Column(Date, nullable=False, comment='公告日期')
    holder_num = Column(Integer, comment='股东户数')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')


class StockStStatus(Base):
    """ST状态表"""
    __tablename__ = 'stock_st_status'
    __table_args__ = (
        UniqueConstraint('ts_code', name='uk_st_status'),
        Index('idx_st_status_is_st', 'is_st'),
        {'comment': 'A股股票ST状态表'}
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    ts_code = Column(String(20), nullable=False, comment='TS代码')
    st_type = Column(String(20), comment='ST类型')
    is_st = Column(Integer, default=0, comment='是否ST(0/1)')
    start_date = Column(Date, comment='ST开始日期')
    end_date = Column(Date, comment='ST结束日期')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')


class StockIpoInfo(Base):
    """IPO信息表"""
    __tablename__ = 'stock_ipo_info'
    __table_args__ = (
        UniqueConstraint('ts_code', name='uk_ipo_info'),
        Index('idx_ipo_info_ipo_date', 'ipo_date'),
        {'comment': 'A股股票IPO信息表'}
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    ts_code = Column(String(20), nullable=False, comment='TS代码')
    ipo_date = Column(Date, comment='上市日期')
    issue_price = Column(Numeric(12, 4), comment='发行价格（元）')
    issue_amount = Column(BigInteger, comment='发行数量（股）')
    raise_amount = Column(Numeric(20, 4), comment='募集资金（元）')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')


class StockTickData(Base):
    """Tick明细表"""
    __tablename__ = 'stock_tick_data'
    __table_args__ = (
        UniqueConstraint('ts_code', 'trade_time', name='uk_tick_code_time'),
        Index('idx_tick_code_time', 'ts_code', 'trade_time'),
        {'comment': 'A股股票Tick明细表'}
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    ts_code = Column(String(20), nullable=False, comment='TS代码')
    trade_time = Column(DateTime, nullable=False, comment='成交时间')
    price = Column(Numeric(12, 4), comment='成交价格（元）')
    volume = Column(BigInteger, comment='成交量（股）')
    amount = Column(Numeric(20, 4), comment='成交额（元）')
    trade_type = Column(String(10), comment='成交类型')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')


class StockLonghubang(Base):
    """龙虎榜表"""
    __tablename__ = 'stock_longhubang'
    __table_args__ = (
        UniqueConstraint('ts_code', 'trade_date', 'rank', 'direction', name='uk_longhubang'),
        Index('idx_longhubang_code_date', 'ts_code', 'trade_date'),
        {'comment': 'A股股票龙虎榜表'}
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    ts_code = Column(String(20), nullable=False, comment='TS代码')
    trade_date = Column(Date, nullable=False, comment='交易日期')
    direction = Column(String(10), comment='买卖方向(buy/sell)')
    rank = Column(Integer, comment='排名')
    sales_department = Column(String(100), comment='营业部名称')
    amount = Column(Numeric(20, 4), comment='成交金额（元）')
    net_amount = Column(Numeric(20, 4), comment='净成交金额（元）')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')


class StockRealtimeDepth(Base):
    """五档盘口表"""
    __tablename__ = 'stock_realtime_depth'
    __table_args__ = (
        UniqueConstraint('symbol', name='uk_realtime_depth'),
        Index('idx_realtime_depth_time', 'update_time'),
        {'comment': 'A股股票五档盘口表'}
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    symbol = Column(String(10), nullable=False, comment='股票代码')
    bid_price1 = Column(Numeric(12, 4), comment='买一价')
    bid_vol1 = Column(BigInteger, comment='买一量')
    bid_price2 = Column(Numeric(12, 4), comment='买二价')
    bid_vol2 = Column(BigInteger, comment='买二量')
    bid_price3 = Column(Numeric(12, 4), comment='买三价')
    bid_vol3 = Column(BigInteger, comment='买三量')
    bid_price4 = Column(Numeric(12, 4), comment='买四价')
    bid_vol4 = Column(BigInteger, comment='买四量')
    bid_price5 = Column(Numeric(12, 4), comment='买五价')
    bid_vol5 = Column(BigInteger, comment='买五量')
    ask_price1 = Column(Numeric(12, 4), comment='卖一价')
    ask_vol1 = Column(BigInteger, comment='卖一量')
    ask_price2 = Column(Numeric(12, 4), comment='卖二价')
    ask_vol2 = Column(BigInteger, comment='卖二量')
    ask_price3 = Column(Numeric(12, 4), comment='卖三价')
    ask_vol3 = Column(BigInteger, comment='卖三量')
    ask_price4 = Column(Numeric(12, 4), comment='卖四价')
    ask_vol4 = Column(BigInteger, comment='卖四量')
    ask_price5 = Column(Numeric(12, 4), comment='卖五价')
    ask_vol5 = Column(BigInteger, comment='卖五量')
    update_time = Column(DateTime, comment='更新时间')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')


class QmtPumpCheckpoint(Base):
    """QMT数据泵断点续传表"""
    __tablename__ = 'qmt_pump_checkpoint'
    __table_args__ = (
        UniqueConstraint('pump_name', name='uk_pump_checkpoint'),
        {'comment': 'QMT数据泵断点续传表'}
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    pump_name = Column(String(50), nullable=False, comment='泵脚本名称')
    current_index = Column(Integer, default=0, comment='当前索引')
    total_count = Column(Integer, default=0, comment='总数')
    last_code = Column(String(20), comment='最后处理的代码')
    status = Column(String(20), default='running', comment='状态(running/completed/failed)')
    error_msg = Column(Text, comment='错误信息')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')