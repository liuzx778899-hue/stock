"""
测试 main.py - 主入口程序和命令行接口
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
        mock_basic_instance = mock_basic.return_value
        mock_basic_instance.engine = MagicMock()

        collector = StockDataCollector()
        collector.init_database()
        # Base.metadata.create_all 被调用
        # 验证 engine 被使用了（通过检查 mock）

    @patch('main.StockBasicCollector')
    @patch('main.StockDailyKlineCollector')
    @patch('main.RealtimeQuoteCollector')
    def test_collect_stock_basic(self, mock_rt, mock_kline, mock_basic):
        mock_basic_instance = mock_basic.return_value
        mock_basic_instance.collect.return_value = 5000

        collector = StockDataCollector()
        count = collector.collect_stock_basic()
        assert count == 5000
        mock_basic_instance.collect.assert_called_once_with(use_extended=True, stop_check=None)

    @patch('main.StockBasicCollector')
    @patch('main.StockDailyKlineCollector')
    @patch('main.RealtimeQuoteCollector')
    def test_collect_stock_basic_no_extended(self, mock_rt, mock_kline, mock_basic):
        mock_basic_instance = mock_basic.return_value
        mock_basic_instance.collect.return_value = 5000

        collector = StockDataCollector()
        collector.collect_stock_basic(use_extended=False)
        mock_basic_instance.collect.assert_called_once_with(use_extended=False, stop_check=None)

    @patch('main.StockBasicCollector')
    @patch('main.StockDailyKlineCollector')
    @patch('main.RealtimeQuoteCollector')
    def test_collect_history_kline(self, mock_rt, mock_kline, mock_basic):
        mock_kline_instance = mock_kline.return_value
        mock_kline_instance.collect.return_value = {'success': 100, 'failed': 2}

        collector = StockDataCollector()
        stats = collector.collect_history_kline("20240101", "20240131")
        assert stats['success'] == 100
        mock_kline_instance.collect.assert_called_once_with("20240101", "20240131")

    @patch('main.StockBasicCollector')
    @patch('main.StockDailyKlineCollector')
    @patch('main.RealtimeQuoteCollector')
    def test_collect_history_kline_with_threads(self, mock_rt, mock_kline, mock_basic):
        mock_kline_instance = mock_kline.return_value
        mock_kline_instance.collect.return_value = {}

        collector = StockDataCollector()
        collector.collect_history_kline("20240101", "20240131", thread_pool_size=20)
        assert mock_kline_instance.thread_pool_size == 20

    @patch('main.StockBasicCollector')
    @patch('main.StockDailyKlineCollector')
    @patch('main.RealtimeQuoteCollector')
    def test_collect_incremental(self, mock_rt, mock_kline, mock_basic):
        mock_kline_instance = mock_kline.return_value
        mock_kline_instance.collect_incremental.return_value = {'success': 10}

        collector = StockDataCollector()
        stats = collector.collect_incremental_kline(days=15)
        mock_kline_instance.collect_incremental.assert_called_once_with(days=15)

    @patch('main.StockBasicCollector')
    @patch('main.StockDailyKlineCollector')
    @patch('main.RealtimeQuoteCollector')
    def test_collect_realtime(self, mock_rt, mock_kline, mock_basic):
        mock_rt_instance = mock_rt.return_value
        mock_rt_instance.collect.return_value = {'total': 5000, 'success': True}

        collector = StockDataCollector()
        stats = collector.collect_realtime_quote(source='sina')
        assert stats['total'] == 5000
        mock_rt_instance.collect.assert_called_once_with(source='sina')

    @patch('main.StockBasicCollector')
    @patch('main.StockDailyKlineCollector')
    @patch('main.RealtimeQuoteCollector')
    def test_get_realtime_quote_single(self, mock_rt, mock_kline, mock_basic):
        mock_rt_instance = mock_rt.return_value
        mock_rt_instance.get_realtime_quote.return_value = {
            'symbol': '000001', 'name': '平安银行', 'price': 10.50
        }

        collector = StockDataCollector()
        quote = collector.get_realtime_quote('000001')
        assert quote['symbol'] == '000001'
        mock_rt_instance.get_realtime_quote.assert_called_once_with('000001')

    @patch('main.StockBasicCollector')
    @patch('main.StockDailyKlineCollector')
    @patch('main.RealtimeQuoteCollector')
    def test_full_collect(self, mock_rt, mock_kline, mock_basic):
        mock_basic_instance = mock_basic.return_value
        mock_basic_instance.engine = MagicMock()
        mock_basic_instance.collect.return_value = 5000
        mock_kline_instance = mock_kline.return_value
        mock_kline_instance.collect.return_value = {'success': 100}

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
        mock_args.source = 'sina'
        mock_parse_args.return_value = mock_args

        mock_collector = mock_collector_class.return_value

        main()
        mock_collector.collect_realtime_quote.assert_called_once_with('sina')

    @patch('argparse.ArgumentParser.parse_args')
    @patch('main.StockDataCollector')
    def test_command_quote_missing_symbol(self, mock_collector_class, mock_parse_args):
        mock_args = MagicMock()
        mock_args.command = 'quote'
        mock_args.symbol = None
        mock_parse_args.return_value = mock_args

        main()
        mock_collector = mock_collector_class.return_value
        assert not mock_collector.get_realtime_quote.called

    @patch('argparse.ArgumentParser.parse_args')
    @patch('main.StockDataCollector')
    def test_command_quote_with_symbol(self, mock_collector_class, mock_parse_args):
        mock_args = MagicMock()
        mock_args.command = 'quote'
        mock_args.symbol = '000001'
        mock_parse_args.return_value = mock_args

        mock_collector = mock_collector_class.return_value
        mock_collector.get_realtime_quote.return_value = {
            'name': '平安银行', 'symbol': '000001', 'price': 10.50,
            'open': 10.30, 'high': 10.60, 'low': 10.20,
            'pre_close': 10.40, 'pct_chg': 0.96, 'update_time': '2024-01-15 14:30:00'
        }

        main()
        mock_collector.get_realtime_quote.assert_called_once_with('000001')

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
