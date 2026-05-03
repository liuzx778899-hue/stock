"""
测试 stock_basic.py - 股票基础信息采集模块
"""
import pytest
import pandas as pd
from datetime import datetime, date
from unittest.mock import patch, MagicMock, call

from stock_basic import StockBasicCollector


class TestStockBasicCollectorInit:
    """测试初始化"""

    def test_init_without_engine(self):
        collector = StockBasicCollector()
        assert collector.engine is not None
        assert collector.Session is not None
        assert collector.rate_limiter is not None

    def test_init_with_external_engine(self):
        mock_engine = MagicMock()
        collector = StockBasicCollector(engine=mock_engine)
        assert collector.engine is mock_engine


class TestTransformData:
    """测试数据转换"""

    def test_transform_basic_dataframe(self, sample_stock_df):
        collector = StockBasicCollector(engine=MagicMock())
        records = collector.transform_data(sample_stock_df)
        assert len(records) == 5

    def test_ts_code_sh_market(self):
        """上海股票 .SH 后缀"""
        collector = StockBasicCollector(engine=MagicMock())
        df = pd.DataFrame([{"代码": "600000", "名称": "浦发银行"}])
        records = collector.transform_data(df)
        assert records[0]['ts_code'] == '600000.SH'

    def test_ts_code_sz_market(self):
        """深圳股票 .SZ 后缀"""
        collector = StockBasicCollector(engine=MagicMock())
        df = pd.DataFrame([{"代码": "000001", "名称": "平安银行"}])
        records = collector.transform_data(df)
        assert records[0]['ts_code'] == '000001.SZ'

    def test_ts_code_gem_market(self):
        """创业板股票 .SZ 后缀"""
        collector = StockBasicCollector(engine=MagicMock())
        df = pd.DataFrame([{"代码": "300750", "名称": "宁德时代"}])
        records = collector.transform_data(df)
        assert records[0]['ts_code'] == '300750.SZ'

    def test_ts_code_star_market(self):
        """科创板股票 .SH 后缀"""
        collector = StockBasicCollector(engine=MagicMock())
        df = pd.DataFrame([{"代码": "688981", "名称": "中芯国际"}])
        records = collector.transform_data(df)
        assert records[0]['ts_code'] == '688981.SH'

    def test_ts_code_beijing_market(self):
        """北交所 8 开头 → 当前逻辑归为 .SZ（可能不正确，记录为已知行为）"""
        collector = StockBasicCollector(engine=MagicMock())
        df = pd.DataFrame([{"代码": "830000", "名称": "测试北交所"}])
        records = collector.transform_data(df)
        # 8开头不是6，当前逻辑归为SZ
        assert records[0]['ts_code'] == '830000.SZ'

    def test_transform_default_list_status(self):
        collector = StockBasicCollector(engine=MagicMock())
        df = pd.DataFrame([{"代码": "000001", "名称": "测试"}])
        records = collector.transform_data(df)
        assert records[0]['list_status'] == 'L'

    def test_transform_empty_dataframe(self):
        collector = StockBasicCollector(engine=MagicMock())
        df = pd.DataFrame()
        records = collector.transform_data(df)
        assert records == []

    def test_transform_missing_columns(self):
        """缺少可选列时不报错"""
        collector = StockBasicCollector(engine=MagicMock())
        df = pd.DataFrame([{"代码": "000001"}])  # 缺少 '名称'
        records = collector.transform_data(df)
        assert len(records) == 1
        assert records[0]['name'] == ''


class TestParseDate:
    """测试日期解析"""

    def test_parse_date_yyyymmdd_string(self):
        collector = StockBasicCollector(engine=MagicMock())
        result = collector._parse_date("20240115")
        assert result == date(2024, 1, 15)

    def test_parse_date_datetime_object(self):
        collector = StockBasicCollector(engine=MagicMock())
        result = collector._parse_date(datetime(2024, 1, 15))
        assert result == date(2024, 1, 15)

    def test_parse_date_none(self):
        collector = StockBasicCollector(engine=MagicMock())
        assert collector._parse_date(None) is None

    def test_parse_date_nan(self):
        collector = StockBasicCollector(engine=MagicMock())
        assert collector._parse_date(float('nan')) is None

    def test_parse_date_invalid_string(self):
        collector = StockBasicCollector(engine=MagicMock())
        # 无效日期字符串 → 返回 None
        result = collector._parse_date("not-a-date")
        assert result is None

    def test_parse_date_yyyy_mm_dd_format(self):
        """BUG-005 已修复: YYYY-MM-DD 格式现在被支持"""
        collector = StockBasicCollector(engine=MagicMock())
        result = collector._parse_date("2024-01-15")
        # BUG-005 已修复，现在应正确解析
        from datetime import date
        assert result == date(2024, 1, 15)


class TestSaveToDb:
    """测试数据库保存"""

    def test_save_empty_records(self):
        collector = StockBasicCollector(engine=MagicMock())
        collector.Session = MagicMock()
        count = collector.save_to_db([])
        # save_to_db 对空列表仍会尝试执行（这是潜在问题）
        # 注意：当前实现没有空列表检查

    def test_save_batch_commit_called(self):
        mock_session = MagicMock()
        mock_session_factory = MagicMock(return_value=mock_session)
        collector = StockBasicCollector(engine=MagicMock())
        collector.Session = mock_session_factory

        records = [{'ts_code': '000001.SZ', 'symbol': '000001', 'name': '测试'}]
        collector.save_to_db(records, batch_size=500)
        assert mock_session.commit.called

    def test_save_rollback_on_error(self):
        mock_session = MagicMock()
        mock_session.execute.side_effect = RuntimeError("DB connection lost")
        mock_session_factory = MagicMock(return_value=mock_session)
        collector = StockBasicCollector(engine=MagicMock())
        collector.Session = mock_session_factory

        records = [{'ts_code': '000001.SZ'}]
        with pytest.raises(RuntimeError):
            collector.save_to_db(records)
        assert mock_session.rollback.called


class TestCollectFlow:
    """测试完整采集流程"""

    @patch('stock_basic.StockBasicCollector.fetch_stock_info')
    @patch('stock_basic.StockBasicCollector.save_to_db')
    @patch('stock_basic.Base')
    def test_collect_basic_flow(self, mock_base, mock_save, mock_fetch, sample_stock_df):
        mock_fetch.return_value = sample_stock_df
        mock_save.return_value = None

        collector = StockBasicCollector(engine=MagicMock())
        collector.Session = MagicMock()
        count = collector.collect(use_extended=False)

        assert count == 5
        mock_fetch.assert_called_once()
        mock_save.assert_called_once()

    @patch('stock_basic.StockBasicCollector.fetch_stock_info_extended')
    @patch('stock_basic.StockBasicCollector.save_to_db')
    def test_collect_extended_flow(self, mock_save, mock_fetch_extended, sample_stock_df):
        mock_fetch_extended.return_value = sample_stock_df
        mock_save.return_value = None

        collector = StockBasicCollector(engine=MagicMock())
        collector.Session = MagicMock()
        count = collector.collect(use_extended=True)

        assert count == 5
        mock_fetch_extended.assert_called_once()


class TestFetchStockInfoExtended:
    """测试扩展数据获取"""

    @patch('stock_basic.data_source_adapter')
    def test_fetches_all_markets(self, mock_adapter):
        """验证使用数据源适配器获取数据（BUG-016 已改用适配器）"""
        mock_df = pd.DataFrame({"代码": ["000001", "600000"], "名称": ["test1", "test2"]})
        mock_adapter.fetch_realtime_with_fallback.return_value = mock_df

        collector = StockBasicCollector(engine=MagicMock())
        collector.rate_limiter = MagicMock()
        df = collector.fetch_stock_info_extended()

        assert len(df) == 2
        mock_adapter.fetch_realtime_with_fallback.assert_called_once()

    @patch('stock_basic.data_source_adapter')
    def test_fallback_on_extended_failure(self, mock_adapter):
        """扩展接口失败时回退到基础接口"""
        mock_adapter.fetch_realtime_with_fallback.side_effect = ConnectionError("API failed")

        collector = StockBasicCollector(engine=MagicMock())
        collector.rate_limiter = MagicMock()

        with patch.object(collector, 'fetch_stock_info') as mock_basic:
            mock_basic.return_value = pd.DataFrame({"代码": ["000001"]})
            df = collector.fetch_stock_info_extended()
            mock_basic.assert_called_once()
