"""
测试 realtime_quote.py - 实时行情接口模块
包含 BUG-001 (missing import) 的验证测试
"""
import pytest
import pandas as pd
from unittest.mock import patch, MagicMock

# BUG-001: realtime_quote.py 缺少 import akshare as ak
# 以下测试在模拟 ak 的情况下进行


class TestRealtimeQuoteInit:
    """测试初始化"""

    @patch('realtime_quote.create_engine')
    @patch('realtime_quote.sessionmaker')
    def test_init_creates_engine(self, mock_sessionmaker, mock_create_engine):
        mock_create_engine.return_value = MagicMock()
        mock_sessionmaker.return_value = MagicMock()

        from realtime_quote import RealtimeQuoteCollector
        collector = RealtimeQuoteCollector()
        assert collector.engine is not None
        assert collector.Session is not None

    @patch('realtime_quote.create_engine')
    @patch('realtime_quote.sessionmaker')
    def test_init_with_external_engine(self, mock_sm, mock_ce):
        mock_engine = MagicMock()
        from realtime_quote import RealtimeQuoteCollector
        collector = RealtimeQuoteCollector(engine=mock_engine)
        assert collector.engine is mock_engine


class TestTransformQuoteData:
    """测试行情数据转换"""

    def test_transform_basic(self, sample_realtime_df):
        from realtime_quote import RealtimeQuoteCollector
        collector = RealtimeQuoteCollector(engine=MagicMock())
        records = collector.transform_quote_data(sample_realtime_df)
        assert len(records) == 1
        r = records[0]
        assert r['symbol'] == '000001'
        assert r['name'] == '平安银行'
        assert r['price'] == 10.50
        assert r['volume'] == 5000000

    def test_transform_empty_df(self):
        from realtime_quote import RealtimeQuoteCollector
        collector = RealtimeQuoteCollector(engine=MagicMock())
        records = collector.transform_quote_data(pd.DataFrame())
        assert records == []

    def test_transform_missing_columns(self):
        """缺少列时不应崩溃"""
        from realtime_quote import RealtimeQuoteCollector
        collector = RealtimeQuoteCollector(engine=MagicMock())
        df = pd.DataFrame([{"代码": "000001"}])  # minimal
        records = collector.transform_quote_data(df)
        assert len(records) == 1

    def test_transform_nan_values(self):
        """NaN 值应转换为 None"""
        import numpy as np
        from realtime_quote import RealtimeQuoteCollector
        collector = RealtimeQuoteCollector(engine=MagicMock())
        df = pd.DataFrame([{
            "代码": "000001", "名称": "测试",
            "最新价": np.nan, "今开": np.nan
        }])
        records = collector.transform_quote_data(df)
        r = records[0]
        assert r['price'] is None
        assert r['open'] is None


class TestSafeDecimal:
    """测试数值安全转换"""

    def test_valid_float(self):
        from realtime_quote import RealtimeQuoteCollector
        collector = RealtimeQuoteCollector(engine=MagicMock())
        assert collector._safe_decimal(10.5) == 10.5

    def test_valid_string(self):
        from realtime_quote import RealtimeQuoteCollector
        collector = RealtimeQuoteCollector(engine=MagicMock())
        assert collector._safe_decimal("10.5") == 10.5

    def test_none_value(self):
        from realtime_quote import RealtimeQuoteCollector
        collector = RealtimeQuoteCollector(engine=MagicMock())
        assert collector._safe_decimal(None) is None

    def test_empty_string(self):
        from realtime_quote import RealtimeQuoteCollector
        collector = RealtimeQuoteCollector(engine=MagicMock())
        assert collector._safe_decimal("") is None

    def test_invalid_string(self):
        from realtime_quote import RealtimeQuoteCollector
        collector = RealtimeQuoteCollector(engine=MagicMock())
        assert collector._safe_decimal("not-a-number") is None


class TestSafeInt:
    """测试整数安全转换"""

    def test_valid_int(self):
        from realtime_quote import RealtimeQuoteCollector
        collector = RealtimeQuoteCollector(engine=MagicMock())
        assert collector._safe_int(100) == 100

    def test_float_to_int(self):
        from realtime_quote import RealtimeQuoteCollector
        collector = RealtimeQuoteCollector(engine=MagicMock())
        assert collector._safe_int("100.9") == 100  # 截断

    def test_none_value(self):
        from realtime_quote import RealtimeQuoteCollector
        collector = RealtimeQuoteCollector(engine=MagicMock())
        assert collector._safe_int(None) is None


class TestSaveToDb:
    """测试保存到数据库"""

    def test_save_empty_records(self):
        from realtime_quote import RealtimeQuoteCollector
        collector = RealtimeQuoteCollector(engine=MagicMock())
        result = collector.save_to_db([])
        assert result == 0

    def test_save_with_records(self):
        from realtime_quote import RealtimeQuoteCollector
        collector = RealtimeQuoteCollector(engine=MagicMock())
        mock_session = MagicMock()
        collector.Session = MagicMock(return_value=mock_session)

        records = [{'symbol': '000001', 'name': 'test', 'price': 10.0}]
        result = collector.save_to_db(records)
        assert result == 1
        assert mock_session.commit.called

    def test_save_rollback_on_error(self):
        from realtime_quote import RealtimeQuoteCollector
        collector = RealtimeQuoteCollector(engine=MagicMock())
        mock_session = MagicMock()
        mock_session.execute.side_effect = RuntimeError("DB error")
        collector.Session = MagicMock(return_value=mock_session)

        with pytest.raises(RuntimeError):
            collector.save_to_db([{'symbol': '000001'}])
        assert mock_session.rollback.called


class TestGetTopLists:
    """测试排行榜"""

    def test_get_top_gainers(self):
        from realtime_quote import RealtimeQuoteCollector
        collector = RealtimeQuoteCollector(engine=MagicMock())
        # Mock _get_all_realtime_df to avoid network calls
        collector._get_all_realtime_df = MagicMock(return_value=pd.DataFrame([
            {"代码": "000001", "名称": "A", "涨跌幅": 10.0},
            {"代码": "000002", "名称": "B", "涨跌幅": 5.0},
            {"代码": "000003", "名称": "C", "涨跌幅": -2.0},
        ]))
        result = collector.get_top_gainers(limit=2)
        assert len(result) == 2

    def test_get_top_gainers_api_error(self):
        from realtime_quote import RealtimeQuoteCollector
        collector = RealtimeQuoteCollector(engine=MagicMock())
        collector._get_all_realtime_df = MagicMock(side_effect=ConnectionError("API error"))

        result = collector.get_top_gainers()
        assert result == []  # 异常时返回空列表


class TestGetRealtimeQuote:
    """测试单只股票行情"""

    def test_get_quote_found(self):
        from realtime_quote import RealtimeQuoteCollector
        collector = RealtimeQuoteCollector(engine=MagicMock())
        collector._get_all_realtime_df = MagicMock(return_value=pd.DataFrame([
            {"代码": "000001", "名称": "平安银行", "最新价": 10.50,
             "今开": 10.20, "最高": 10.60, "最低": 10.15, "昨收": 10.30,
             "成交量": 5000000, "成交额": 52000000.0, "涨跌额": 0.20, "涨跌幅": 1.94}
        ]))

        result = collector.get_realtime_quote("000001")
        assert result is not None
        assert result['symbol'] == '000001'
        assert result['price'] == 10.50

    def test_get_quote_not_found(self):
        from realtime_quote import RealtimeQuoteCollector
        collector = RealtimeQuoteCollector(engine=MagicMock())
        collector._get_all_realtime_df = MagicMock(return_value=pd.DataFrame([
            {"代码": "600000", "名称": "浦发银行"}
        ]))

        result = collector.get_realtime_quote("000001")
        assert result is None
