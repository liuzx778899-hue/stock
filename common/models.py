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