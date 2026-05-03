"""
测试 models.py - 数据库模型模块
"""
import pytest
from datetime import date, datetime
from sqlalchemy import create_engine, inspect

from models import Base, StockBasic, StockDailyKline, StockRealtimeQuote


class TestStockBasic:
    """测试股票基础信息模型"""

    def test_table_name(self):
        assert StockBasic.__tablename__ == 'stock_basic'

    def test_primary_key(self):
        assert StockBasic.ts_code.primary_key is True

    def test_columns_exist(self):
        """验证所有必要列存在"""
        expected = ['ts_code', 'symbol', 'name', 'area', 'industry', 'market',
                     'list_date', 'list_status', 'delist_date', 'is_hs',
                     'created_at', 'updated_at']
        for col in expected:
            assert hasattr(StockBasic, col), f"Missing column: {col}"

    def test_default_list_status(self):
        """list_status 默认值为 'L'"""
        from sqlalchemy.sql import expression
        assert StockBasic.list_status.default.arg == 'L'

    def test_primary_key_serves_as_unique(self):
        """BUG-012 已修复：冗余 UNIQUE KEY 已删除，PRIMARY KEY 本身保证唯一性"""
        # ts_code 是主键，天然具有唯一约束
        assert StockBasic.ts_code.primary_key is True


class TestStockDailyKline:
    """测试日K线模型"""

    def test_table_name(self):
        assert StockDailyKline.__tablename__ == 'stock_daily_kline'

    def test_primary_key_is_auto_increment(self):
        assert StockDailyKline.id.primary_key is True
        # SQLAlchemy 2.0+ 中 autoincrement 返回 True（而非 'auto'）
        assert StockDailyKline.id.autoincrement in (True, 'auto')

    def test_decimal_precision(self):
        """验证 Decimal 列精度"""
        open_col = StockDailyKline.open
        assert str(open_col.type) == 'NUMERIC(12, 4)'

    def test_unique_constraint_on_code_and_date(self):
        from sqlalchemy import UniqueConstraint
        constraints = [c for c in StockDailyKline.__table_args__ if not isinstance(c, dict)]
        has_uk = any(
            isinstance(c, UniqueConstraint) and
            'uk_kline_code_date' == c.name
            for c in constraints if isinstance(c, UniqueConstraint)
        )
        assert has_uk


class TestStockRealtimeQuote:
    """测试实时行情模型"""

    def test_table_name(self):
        assert StockRealtimeQuote.__tablename__ == 'stock_realtime_quote'

    def test_no_unique_constraint_on_id(self):
        """实时行情表没有 ts_code+date 唯一约束，可多次采集"""
        from sqlalchemy import UniqueConstraint
        constraints = [c for c in StockRealtimeQuote.__table_args__ if not isinstance(c, dict)]
        # 不应有 UniqueConstraint
        has_uk = any(isinstance(c, UniqueConstraint) for c in constraints)
        assert not has_uk


class TestAllModels:
    """集成模型测试"""

    def test_all_models_registered_in_base(self):
        """所有模型应注册到 Base.metadata"""
        tables = Base.metadata.tables.keys()
        assert 'stock_basic' in tables
        assert 'stock_daily_kline' in tables
        assert 'stock_realtime_quote' in tables

    def test_create_all_with_in_memory_db(self):
        """使用内存 SQLite 测试表创建"""
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        assert 'stock_basic' in tables
        assert 'stock_daily_kline' in tables
        assert 'stock_realtime_quote' in tables
        engine.dispose()

    def test_model_instantiation(self):
        """测试模型实例化"""
        stock = StockBasic(
            ts_code='000001.SZ',
            symbol='000001',
            name='平安银行',
            list_date=date(1991, 4, 3)
        )
        assert stock.ts_code == '000001.SZ'
        assert stock.symbol == '000001'

    def test_kline_instantiation(self):
        """测试K线模型实例化"""
        kline = StockDailyKline(
            ts_code='000001.SZ',
            trade_date=date(2024, 1, 2),
            open=10.00,
            high=10.50,
            low=9.80,
            close=10.30,
            volume=1000000
        )
        assert kline.open == 10.00
        assert kline.close == 10.30
