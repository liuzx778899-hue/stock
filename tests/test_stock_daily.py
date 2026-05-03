"""
测试 stock_daily.py - 股票历史日K线数据下载模块
"""
import pytest
import pandas as pd
from datetime import datetime, date
from unittest.mock import patch, MagicMock, call

from stock_daily import StockDailyKlineCollector


class TestStockDailyKlineInit:
    """测试初始化"""

    def test_init_without_engine(self):
        collector = StockDailyKlineCollector()
        assert collector.engine is not None
        assert collector.thread_pool_size >= 1

    def test_init_with_engine(self):
        mock_engine = MagicMock()
        collector = StockDailyKlineCollector(engine=mock_engine)
        assert collector.engine is mock_engine

    def test_init_custom_thread_pool_size(self):
        collector = StockDailyKlineCollector(thread_pool_size=5)
        assert collector.thread_pool_size == 5


class TestTransformKlineData:
    """测试K线数据转换"""

    def test_transform_basic(self, sample_kline_df):
        collector = StockDailyKlineCollector(engine=MagicMock())
        records = collector.transform_kline_data(sample_kline_df, "000001.SZ")
        assert len(records) == 2

    def test_transform_correct_fields(self, sample_kline_df):
        collector = StockDailyKlineCollector(engine=MagicMock())
        records = collector.transform_kline_data(sample_kline_df, "000001.SZ")

        r0 = records[0]
        assert r0['ts_code'] == '000001.SZ'
        assert r0['trade_date'] == date(2024, 1, 2)
        assert r0['open'] == 10.0
        assert r0['high'] == 10.5
        assert r0['low'] == 9.8
        assert r0['close'] == 10.3
        assert r0['pre_close'] == 9.9
        assert r0['volume'] == 1000000
        assert r0['amount'] == 10200000.0
        assert r0['turnover_rate'] == 2.5
        assert r0['pct_chg'] == 4.04

    def test_transform_empty_dataframe(self):
        collector = StockDailyKlineCollector(engine=MagicMock())
        records = collector.transform_kline_data(pd.DataFrame(), "000001.SZ")
        assert records == []

    def test_transform_none_dataframe(self):
        collector = StockDailyKlineCollector(engine=MagicMock())
        records = collector.transform_kline_data(None, "000001.SZ")
        assert records == []

    def test_transform_filter_null_dates(self):
        """trade_date 为 None 的记录被过滤"""
        collector = StockDailyKlineCollector(engine=MagicMock())
        df = pd.DataFrame([{
            "日期": None, "开盘": 10.0, "收盘": 10.5,
            "最高": 11.0, "最低": 9.5, "昨收": 10.0,
            "成交量": 100, "成交额": 1000, "换手率": 1.0, "涨跌幅": 5.0
        }])
        records = collector.transform_kline_data(df, "000001.SZ")
        assert len(records) == 0


class TestParseDate:
    """测试日期解析"""

    def test_parse_yyyymmdd(self):
        collector = StockDailyKlineCollector(engine=MagicMock())
        result = collector._parse_date("20240115")
        assert result == date(2024, 1, 15)

    def test_parse_yyyy_mm_dd(self):
        collector = StockDailyKlineCollector(engine=MagicMock())
        result = collector._parse_date("2024-01-15")
        assert result == date(2024, 1, 15)

    def test_parse_datetime(self):
        collector = StockDailyKlineCollector(engine=MagicMock())
        result = collector._parse_date(datetime(2024, 1, 15))
        assert result == date(2024, 1, 15)

    def test_parse_date_object(self):
        collector = StockDailyKlineCollector(engine=MagicMock())
        result = collector._parse_date(date(2024, 1, 15))
        assert result == date(2024, 1, 15)

    def test_parse_none(self):
        collector = StockDailyKlineCollector(engine=MagicMock())
        assert collector._parse_date(None) is None

    def test_parse_nan(self):
        collector = StockDailyKlineCollector(engine=MagicMock())
        assert collector._parse_date(float('nan')) is None


class TestSaveKlineBatch:
    """测试批量保存"""

    def test_save_empty_records(self):
        collector = StockDailyKlineCollector(engine=MagicMock())
        result = collector.save_kline_batch([])
        assert result == 0

    def test_save_with_records(self):
        mock_session = MagicMock()
        mock_session_factory = MagicMock(return_value=mock_session)
        collector = StockDailyKlineCollector(engine=MagicMock())
        collector.Session = mock_session_factory

        records = [{'ts_code': '000001.SZ', 'trade_date': date(2024, 1, 2), 'open': 10.0}]
        result = collector.save_kline_batch(records)
        assert result == 1
        assert mock_session.execute.called
        assert mock_session.commit.called


class TestCollectSingleStock:
    """测试单只股票采集"""

    @patch.object(StockDailyKlineCollector, 'fetch_single_stock_kline')
    @patch.object(StockDailyKlineCollector, 'save_kline_batch')
    def test_successful_collection(self, mock_save, mock_fetch, sample_kline_df):
        mock_fetch.return_value = sample_kline_df
        mock_save.return_value = 2

        collector = StockDailyKlineCollector(engine=MagicMock())
        ts_code, count, error = collector.collect_single_stock(
            "000001.SZ", "20240101", "20240131"
        )
        assert ts_code == "000001.SZ"
        assert count == 2
        assert error == ""

    @patch.object(StockDailyKlineCollector, 'fetch_single_stock_kline')
    def test_no_data_collection(self, mock_fetch):
        mock_fetch.return_value = pd.DataFrame()

        collector = StockDailyKlineCollector(engine=MagicMock())
        ts_code, count, error = collector.collect_single_stock(
            "000001.SZ", "20240101", "20240131"
        )
        assert count == 0
        assert error == "无数据"

    @patch.object(StockDailyKlineCollector, 'fetch_single_stock_kline')
    def test_error_collection(self, mock_fetch):
        mock_fetch.side_effect = ConnectionError("API timeout")

        collector = StockDailyKlineCollector(engine=MagicMock())
        ts_code, count, error = collector.collect_single_stock(
            "000001.SZ", "20240101", "20240131"
        )
        assert count == 0
        assert "API timeout" in error


class TestCollectMultiThreaded:
    """测试多线程采集"""

    @patch.object(StockDailyKlineCollector, 'get_stock_list')
    @patch.object(StockDailyKlineCollector, 'collect_single_stock')
    @patch.object(StockDailyKlineCollector, 'create_table')
    def test_multi_threaded_collection(self, mock_create, mock_single, mock_list):
        mock_list.return_value = ["000001.SZ", "000002.SZ", "600000.SH", "300750.SZ"]
        mock_single.return_value = ("000001.SZ", 10, "")

        collector = StockDailyKlineCollector(engine=MagicMock(), thread_pool_size=2)
        stats = collector.collect("20240101", "20240131", show_progress=False)

        assert stats['total'] == 4
        assert stats['success'] == 4
        assert stats['failed'] == 0
        assert mock_single.call_count == 4

    @patch.object(StockDailyKlineCollector, 'get_stock_list')
    @patch.object(StockDailyKlineCollector, 'collect_single_stock')
    @patch.object(StockDailyKlineCollector, 'create_table')
    def test_partial_failure_stats(self, mock_create, mock_single, mock_list):
        """混合成功和失败"""
        mock_list.return_value = ["000001.SZ", "000002.SZ"]
        mock_single.side_effect = [
            ("000001.SZ", 10, ""),
            ("000002.SZ", 0, "Network error"),
        ]

        collector = StockDailyKlineCollector(engine=MagicMock(), thread_pool_size=1)
        stats = collector.collect("20240101", "20240131", show_progress=False)

        assert stats['total'] == 2
        assert stats['success'] == 1
        assert stats['failed'] == 1
        assert stats['total_records'] == 10

    def test_with_explicit_stock_list(self):
        """手动传入股票列表"""
        collector = StockDailyKlineCollector(engine=MagicMock(), thread_pool_size=1)
        with patch.object(collector, 'collect_single_stock') as mock_single:
            with patch.object(collector, 'create_table'):
                mock_single.return_value = ("custom.SZ", 5, "")
                stats = collector.collect(
                    "20240101", "20240131",
                    stock_list=["custom.SZ"],
                    show_progress=False
                )
                assert stats['success'] == 1


class TestCollectIncremental:
    """测试增量采集"""

    def test_incremental_calls_collect(self):
        collector = StockDailyKlineCollector(engine=MagicMock())
        with patch.object(collector, 'collect') as mock_collect:
            mock_collect.return_value = {'total': 0}
            collector.collect_incremental(days=7)
            mock_collect.assert_called_once()
            # 验证日期格式为 %Y%m%d
            args = mock_collect.call_args
            start = args[1]['start_date'] if args[1].get('start_date') else args[0][0]
            end = args[1]['end_date'] if args[1].get('end_date') else args[0][1]
            assert len(start) == 8
            assert len(end) == 8
