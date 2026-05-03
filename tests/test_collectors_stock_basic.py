"""测试股票基础信息采集器（重构版）"""
from unittest.mock import patch, MagicMock, PropertyMock
import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from models import Base as ModelBase


@pytest.fixture
def memory_engine():
    """内存数据库引擎"""
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
    )
    ModelBase.metadata.create_all(engine)
    return engine


class TestStockBasicCollector:
    """测试 StockBasicCollector"""

    def test_import(self):
        """测试模块可导入"""
        from collectors.stock_basic import StockBasicCollector
        assert StockBasicCollector is not None

    def test_init_with_engine(self, memory_engine):
        """测试使用外部引擎初始化"""
        from collectors.stock_basic import StockBasicCollector
        collector = StockBasicCollector(engine=memory_engine)
        assert collector.orchestrator is not None
        assert collector.engine is memory_engine

    def test_init_without_engine(self):
        """测试自动创建引擎"""
        from collectors.stock_basic import StockBasicCollector
        collector = StockBasicCollector()
        assert collector.engine is not None

    def test_build_ts_code_sh(self):
        """测试上证 ts_code"""
        from collectors.stock_basic import StockBasicCollector
        collector = StockBasicCollector()
        assert collector._build_ts_code("600000") == "600000.SH"
        assert collector._build_ts_code("600001") == "600001.SH"

    def test_build_ts_code_sz(self):
        """测试深证 ts_code"""
        from collectors.stock_basic import StockBasicCollector
        collector = StockBasicCollector()
        assert collector._build_ts_code("000001") == "000001.SZ"
        assert collector._build_ts_code("002001") == "002001.SZ"

    def test_build_ts_code_gem(self):
        """测试创业板 ts_code"""
        from collectors.stock_basic import StockBasicCollector
        collector = StockBasicCollector()
        assert collector._build_ts_code("300001") == "300001.SZ"

    def test_build_ts_code_bj(self):
        """测试北交所 ts_code"""
        from collectors.stock_basic import StockBasicCollector
        collector = StockBasicCollector()
        assert collector._build_ts_code("400001") == "400001.BJ"
        assert collector._build_ts_code("800001") == "800001.BJ"

    def test_build_ts_code_with_suffix(self):
        """测试已有后缀的代码"""
        from collectors.stock_basic import StockBasicCollector
        collector = StockBasicCollector()
        assert collector._build_ts_code("000001.SZ") == "000001.SZ"

    def test_build_ts_code_none(self):
        """测试 None 代码"""
        from collectors.stock_basic import StockBasicCollector
        collector = StockBasicCollector()
        assert collector._build_ts_code(None) is None

    def test_transform_data_basic(self):
        """测试基本数据转换"""
        from collectors.stock_basic import StockBasicCollector
        collector = StockBasicCollector()

        df = pd.DataFrame({
            "symbol": ["000001", "600000"],
            "name": ["平安银行", "浦发银行"],
            "industry": ["金融", "金融"],
            "area": ["深圳", "上海"]
        })
        result = collector._transform_data(df)
        assert "ts_code" in result.columns
        assert "market" in result.columns
        assert result.iloc[0]["ts_code"] == "000001.SZ"
        assert result.iloc[1]["ts_code"] == "600000.SH"

    def test_transform_data_empty(self):
        """测试空数据转换"""
        from collectors.stock_basic import StockBasicCollector
        collector = StockBasicCollector()
        assert collector._transform_data(pd.DataFrame()).empty
        assert collector._transform_data(None) is None

    @patch('collectors.stock_basic.orchestrator')
    def test_collect_with_stop(self, mock_orchestrator, memory_engine):
        """测试采集被停止"""
        from collectors.stock_basic import StockBasicCollector
        collector = StockBasicCollector(engine=memory_engine)

        mock_orchestrator.collect_stock_basic.return_value = pd.DataFrame({
            "symbol": ["000001"],
            "name": ["平安银行"],
            "industry": ["金融"],
            "area": ["深圳"]
        })

        result = collector.collect(stop_check=lambda: True)
        assert result["success"] is False
        assert result["status"] == "stopped"

    @patch('collectors.stock_basic.orchestrator')
    def test_collect_empty_data(self, mock_orchestrator, memory_engine):
        """测试采集空数据"""
        from collectors.stock_basic import StockBasicCollector
        collector = StockBasicCollector(engine=memory_engine)

        mock_orchestrator.collect_stock_basic.return_value = pd.DataFrame()
        result = collector.collect()
        assert result["success"] is False

    @patch('collectors.stock_basic.StockBasicCollector._save_to_db')
    @patch('collectors.stock_basic.orchestrator')
    def test_collect_success(self, mock_orchestrator, mock_save, memory_engine):
        """测试采集成功"""
        from collectors.stock_basic import StockBasicCollector
        collector = StockBasicCollector(engine=memory_engine)

        mock_orchestrator.collect_stock_basic.return_value = pd.DataFrame({
            "symbol": ["000001", "600000"],
            "name": ["平安银行", "浦发银行"],
            "industry": ["金融", "金融"],
            "area": ["深圳", "上海"]
        })
        mock_save.return_value = 2

        result = collector.collect()
        assert result["success"] is True
        assert result["total"] == 2
        assert result["saved"] == 2

    @patch('collectors.base.sessionmaker')
    def test_save_to_db(self, mock_sessionmaker, memory_engine):
        """测试保存到数据库"""
        from collectors.stock_basic import StockBasicCollector

        mock_session = MagicMock()
        mock_session_class = MagicMock()
        mock_session_class.return_value = mock_session
        mock_sessionmaker.return_value = mock_session_class

        collector = StockBasicCollector(engine=memory_engine)

        df = pd.DataFrame({
            "symbol": ["000001", "600000"],
            "name": ["平安银行", "浦发银行"],
            "industry": ["金融", "金融"],
            "area": ["深圳", "上海"]
        })
        df = collector._transform_data(df)
        saved = collector._save_to_db(df)
        assert saved == 2
        assert mock_session.execute.call_count >= 2
        assert mock_session.commit.call_count >= 1
        mock_session.close.assert_called_once()

    @patch('collectors.base.sessionmaker')
    def test_get_stock_list(self, mock_sessionmaker, memory_engine):
        """测试获取股票列表"""
        from collectors.stock_basic import StockBasicCollector

        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = [("000001.SZ",), ("600000.SH",)]

        mock_session_class = MagicMock()
        mock_session_class.return_value = mock_session
        mock_sessionmaker.return_value = mock_session_class

        collector = StockBasicCollector(engine=memory_engine)

        stocks = collector.get_stock_list()
        assert len(stocks) == 2
        assert "000001.SZ" in stocks

    def test_get_stock_list_empty_db(self, memory_engine):
        """测试空数据库的股票列表"""
        from collectors.stock_basic import StockBasicCollector
        collector = StockBasicCollector(engine=memory_engine)

        stocks = collector.get_stock_list()
        assert stocks == []

    @patch('collectors.base.sessionmaker')
    def test_save_to_db_upsert(self, mock_sessionmaker, memory_engine):
        """测试 UPSERT 功能（重复保存）"""
        from collectors.stock_basic import StockBasicCollector

        mock_session = MagicMock()
        mock_session_class = MagicMock()
        mock_session_class.return_value = mock_session
        mock_sessionmaker.return_value = mock_session_class

        collector = StockBasicCollector(engine=memory_engine)

        df = pd.DataFrame({
            "symbol": ["000001"],
            "name": ["平安银行"],
            "industry": ["金融"],
            "area": ["深圳"]
        })
        df = collector._transform_data(df)
        saved1 = collector._save_to_db(df)
        assert saved1 == 1

        # 再次保存（UPSERT）
        saved2 = collector._save_to_db(df)
        assert saved2 == 1
