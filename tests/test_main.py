"""
测试 main.py - 主入口程序和命令行接口（重构版）
"""
import pytest
from unittest.mock import patch, MagicMock

from main import StockDataCollector, main


class TestStockDataCollector:
    """测试主采集器类"""

    @patch('main.StockBasicCollector')
    @patch('main.StockDailyKlineCollector')
    @patch('main.RealtimeQuoteCollector')
    def test_init_creates_all_collectors(self, mock_rt, mock_kline, mock_basic):
        """初始化创建三个采集器"""
        collector = StockDataCollector()
        assert collector.basic_collector is not None
        assert collector.kline_collector is not None
        assert collector.realtime_collector is not None
        mock_basic.assert_called_once()
        mock_kline.assert_called_once()
        mock_rt.assert_called_once()

    @patch('main.StockBasicCollector')
    @patch('main.StockDailyKlineCollector')
    @patch('main.RealtimeQuoteCollector')
    def test_init_database(self, mock_rt, mock_kline, mock_basic):
        """测试数据库初始化"""
        mock_engine = MagicMock()
        mock_basic.return_value.engine = mock_engine
        mock_kline.return_value.engine = mock_engine
        mock_rt.return_value.engine = mock_engine

        collector = StockDataCollector()
        collector.init_database()

    @patch('main.StockBasicCollector')
    @patch('main.StockDailyKlineCollector')
    @patch('main.RealtimeQuoteCollector')
    def test_collect_stock_basic(self, mock_rt, mock_kline, mock_basic):
        """测试股票基础信息采集"""
        mock_basic_instance = mock_basic.return_value
        mock_basic_instance.collect.return_value = {'success': True, 'saved': 5000}

        collector = StockDataCollector()
        result = collector.collect_stock_basic()
        assert result['success'] == True
        assert result['saved'] == 5000
        mock_basic_instance.collect.assert_called_once()

    @patch('main.StockBasicCollector')
    @patch('main.StockDailyKlineCollector')
    @patch('main.RealtimeQuoteCollector')
    def test_collect_history_kline(self, mock_rt, mock_kline, mock_basic):
        """测试K线数据采集"""
        mock_kline_instance = mock_kline.return_value
        mock_kline_instance.collect.return_value = {'success': True, 'success_count': 100}

        collector = StockDataCollector()
        stats = collector.collect_history_kline("20240101", "20240131")
        assert stats['success'] == True
        mock_kline_instance.collect.assert_called_once()

    @patch('main.StockBasicCollector')
    @patch('main.StockDailyKlineCollector')
    @patch('main.RealtimeQuoteCollector')
    def test_collect_history_kline_with_threads(self, mock_rt, mock_kline, mock_basic):
        """测试K线采集设置线程数"""
        mock_kline_instance = mock_kline.return_value
        mock_kline_instance.collect.return_value = {}

        collector = StockDataCollector()
        collector.collect_history_kline("20240101", "20240131", thread_pool_size=20)
        assert mock_kline_instance.thread_pool_size == 20

    @patch('main.StockBasicCollector')
    @patch('main.StockDailyKlineCollector')
    @patch('main.RealtimeQuoteCollector')
    def test_collect_incremental(self, mock_rt, mock_kline, mock_basic):
        """测试增量K线采集"""
        mock_kline_instance = mock_kline.return_value
        mock_kline_instance.collect_incremental.return_value = {'success': True, 'success_count': 10}

        collector = StockDataCollector()
        stats = collector.collect_incremental_kline(days=15)
        assert stats['success'] == True
        mock_kline_instance.collect_incremental.assert_called_once()

    @patch('main.StockBasicCollector')
    @patch('main.StockDailyKlineCollector')
    @patch('main.RealtimeQuoteCollector')
    def test_collect_realtime(self, mock_rt, mock_kline, mock_basic):
        """测试实时行情采集"""
        mock_rt_instance = mock_rt.return_value
        mock_rt_instance.collect.return_value = {'success': True, 'total': 5000}

        collector = StockDataCollector()
        stats = collector.collect_realtime_quote()
        assert stats['total'] == 5000
        mock_rt_instance.collect.assert_called_once()

    @patch('main.StockBasicCollector')
    @patch('main.StockDailyKlineCollector')
    @patch('main.RealtimeQuoteCollector')
    def test_collect_realtime_single(self, mock_rt, mock_kline, mock_basic):
        """测试单只股票实时行情采集"""
        mock_rt_instance = mock_rt.return_value
        mock_rt_instance.collect.return_value = {
            'success': True,
            'saved': 1
        }

        collector = StockDataCollector()
        result = collector.collect_realtime_quote(symbol='000001')
        assert result['success'] == True
        mock_rt_instance.collect.assert_called_once_with(symbol='000001', progress_callback=None, stop_check=None)

    @patch('main.StockBasicCollector')
    @patch('main.StockDailyKlineCollector')
    @patch('main.RealtimeQuoteCollector')
    def test_full_collect(self, mock_rt, mock_kline, mock_basic):
        """测试全量采集"""
        mock_basic_instance = mock_basic.return_value
        mock_basic_instance.engine = MagicMock()
        mock_basic_instance.collect.return_value = {'success': True, 'saved': 5000}
        mock_kline_instance = mock_kline.return_value
        mock_kline_instance.collect.return_value = {'success': True, 'success_count': 100}

        collector = StockDataCollector()
        collector.full_collect("20240101", "20240131")

        # 验证调用了基础信息采集和K线采集
        mock_basic_instance.collect.assert_called_once()
        mock_kline_instance.collect.assert_called_once()


class TestMainCli:
    """测试命令行接口"""

    @patch('argparse.ArgumentParser.parse_args')
    @patch('main.StockDataCollector')
    def test_command_init(self, mock_collector_class, mock_parse_args):
        mock_args = MagicMock()
        mock_args.command = 'init'
        mock_parse_args.return_value = mock_args

        mock_collector = mock_collector_class.return_value

        main()
        mock_collector.init_database.assert_called_once()

    @patch('argparse.ArgumentParser.parse_args')
    @patch('main.StockDataCollector')
    def test_command_basic(self, mock_collector_class, mock_parse_args):
        mock_args = MagicMock()
        mock_args.command = 'basic'
        mock_parse_args.return_value = mock_args

        mock_collector = mock_collector_class.return_value

        main()
        mock_collector.collect_stock_basic.assert_called_once()

    @patch('argparse.ArgumentParser.parse_args')
    @patch('main.StockDataCollector')
    def test_command_kline_missing_dates(self, mock_collector_class, mock_parse_args):
        """kline 命令缺少日期参数"""
        mock_args = MagicMock()
        mock_args.command = 'kline'
        mock_args.start_date = None
        mock_args.end_date = None
        mock_parse_args.return_value = mock_args

        main()
        # 不应调用 collect_history_kline
        mock_collector = mock_collector_class.return_value
        assert not mock_collector.collect_history_kline.called

    @patch('argparse.ArgumentParser.parse_args')
    @patch('main.StockDataCollector')
    def test_command_kline_with_dates(self, mock_collector_class, mock_parse_args):
        mock_args = MagicMock()
        mock_args.command = 'kline'
        mock_args.start_date = '20240101'
        mock_args.end_date = '20240131'
        mock_args.threads = 10
        mock_parse_args.return_value = mock_args

        mock_collector = mock_collector_class.return_value

        main()
        mock_collector.collect_history_kline.assert_called_once_with(
            '20240101', '20240131', 10
        )

    @patch('argparse.ArgumentParser.parse_args')
    @patch('main.StockDataCollector')
    def test_command_incremental(self, mock_collector_class, mock_parse_args):
        mock_args = MagicMock()
        mock_args.command = 'incremental'
        mock_args.days = 60
        mock_parse_args.return_value = mock_args

        mock_collector = mock_collector_class.return_value

        main()
        mock_collector.collect_incremental_kline.assert_called_once_with(60)

    @patch('argparse.ArgumentParser.parse_args')
    @patch('main.StockDataCollector')
    def test_command_realtime(self, mock_collector_class, mock_parse_args):
        mock_args = MagicMock()
        mock_args.command = 'realtime'
        mock_args.source = 'em'
        mock_parse_args.return_value = mock_args

        mock_collector = mock_collector_class.return_value

        main()
        mock_collector.collect_realtime_quote.assert_called_once()

    @patch('argparse.ArgumentParser.parse_args')
    @patch('main.StockDataCollector')
    def test_command_quote_missing_symbol(self, mock_collector_class, mock_parse_args):
        mock_args = MagicMock()
        mock_args.command = 'quote'
        mock_args.symbol = None
        mock_parse_args.return_value = mock_args

        main()
        mock_collector = mock_collector_class.return_value
        assert not mock_collector.collect_realtime_quote.called

    @patch('argparse.ArgumentParser.parse_args')
    @patch('main.StockDataCollector')
    def test_command_quote_with_symbol(self, mock_collector_class, mock_parse_args):
        mock_args = MagicMock()
        mock_args.command = 'quote'
        mock_args.symbol = '000001'
        mock_parse_args.return_value = mock_args

        mock_collector = mock_collector_class.return_value
        mock_collector.collect_realtime_quote.return_value = {
            'success': True, 'saved': 1
        }

        main()
        mock_collector.collect_realtime_quote.assert_called_once()

    @patch('argparse.ArgumentParser.parse_args')
    @patch('main.StockDataCollector')
    def test_command_full_missing_dates(self, mock_collector_class, mock_parse_args):
        mock_args = MagicMock()
        mock_args.command = 'full'
        mock_args.start_date = None
        mock_args.end_date = None
        mock_parse_args.return_value = mock_args

        main()
        mock_collector = mock_collector_class.return_value
        assert not mock_collector.full_collect.called

    @patch('argparse.ArgumentParser.parse_args')
    @patch('main.StockDataCollector')
    def test_command_full_with_dates(self, mock_collector_class, mock_parse_args):
        mock_args = MagicMock()
        mock_args.command = 'full'
        mock_args.start_date = '20240101'
        mock_args.end_date = '20240131'
        mock_parse_args.return_value = mock_args

        mock_collector = mock_collector_class.return_value

        main()
        mock_collector.full_collect.assert_called_once_with('20240101', '20240131')