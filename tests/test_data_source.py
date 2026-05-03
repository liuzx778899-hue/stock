"""
测试 data_source.py - 数据源适配器模块
测试多数据源切换、自动降级、接口一致性
"""
import pytest
import pandas as pd
from unittest.mock import patch, MagicMock, PropertyMock

from data_source import DataSourceAdapter, AkShareAdapter, data_source_adapter
from config import DataSourceConfig


class TestDataSourceAdapter:
    """测试数据源适配器基类"""

    def test_init_with_enabled_sources(self):
        adapter = DataSourceAdapter()
        assert len(adapter.data_sources) >= 1
        assert adapter.current_source_index == 0

    def test_get_current_source(self):
        adapter = DataSourceAdapter()
        source = adapter.get_current_source()
        assert source is not None
        assert isinstance(source, DataSourceConfig)

    def test_get_current_source_after_exhaustion(self):
        adapter = DataSourceAdapter()
        adapter.current_source_index = 999  # beyond available sources
        source = adapter.get_current_source()
        assert source is None

    def test_switch_to_next_source_success(self):
        adapter = DataSourceAdapter()
        initial = adapter.current_source_index
        result = adapter.switch_to_next_source()
        assert result is True
        assert adapter.current_source_index == initial + 1

    def test_switch_to_next_source_exhausted(self):
        adapter = DataSourceAdapter()
        adapter.current_source_index = len(adapter.data_sources) - 1
        result = adapter.switch_to_next_source()
        assert result is False

    def test_reset_source(self):
        adapter = DataSourceAdapter()
        adapter.current_source_index = 2
        adapter.reset_source()
        assert adapter.current_source_index == 0

    def test_with_fallback_success_first_source(self):
        """首次数据源就成功"""
        adapter = DataSourceAdapter()

        @adapter.with_fallback
        def fetch_data(source_config=None):
            return pd.DataFrame({"col": [1, 2, 3]})

        result = fetch_data()
        assert isinstance(result, pd.DataFrame)
        assert len(result) == 3
        assert adapter.current_source_index == 0  # 未切换

    def test_with_fallback_fallback_to_second_source(self):
        """第一个数据源失败，降级到第二个"""
        adapter = DataSourceAdapter()
        call_log = []

        @adapter.with_fallback
        def fetch_data(source_config=None):
            call_log.append(source_config.name if source_config else "none")
            if source_config and "em" in source_config.name:
                raise ConnectionError("EM source failed")
            return pd.DataFrame({"col": [1]})

        # Mock switch_to_next_source to actually work
        result = fetch_data()
        assert len(result) == 1
        # 第一个调用 em 失败，第二个 sina 成功
        assert "em" in call_log[0]
        assert "sina" in call_log[1]

    def test_with_fallback_all_sources_fail(self):
        """所有数据源都失败"""
        adapter = DataSourceAdapter()

        @adapter.with_fallback
        def fetch_data(source_config=None):
            raise ConnectionError(f"{source_config.name if source_config else 'unknown'} failed")

        with pytest.raises(Exception):
            fetch_data()
        # 重置回主数据源
        assert adapter.current_source_index == 0

    def test_with_fallback_reset_on_partial_failure(self):
        """部分失败后重置到主源"""
        adapter = DataSourceAdapter()

        @adapter.with_fallback
        def fetch_data(source_config=None):
            if source_config and "em" in source_config.name:
                raise ConnectionError("fail")
            return pd.DataFrame()

        fetch_data()
        # 降级成功，但不会自动 reset（需要手动调用）
        # 在 with_fallback 成功后不自动 reset，由调用方决定


class TestAkShareAdapter:
    """测试 AkShare 特定适配器"""

    @patch('data_source.ak')
    def test_fetch_stock_list_em(self, mock_ak):
        mock_ak.stock_zh_a_spot_em.return_value = pd.DataFrame({"代码": ["000001"]})
        adapter = AkShareAdapter()
        df = adapter.fetch_stock_list_em()
        assert len(df) == 1
        mock_ak.stock_zh_a_spot_em.assert_called_once()

    @patch('data_source.ak')
    def test_fetch_stock_list_em_empty(self, mock_ak):
        """空数据返回"""
        mock_ak.stock_zh_a_spot_em.return_value = pd.DataFrame()
        adapter = AkShareAdapter()
        df = adapter.fetch_stock_list_em()
        assert df.empty

    @patch('data_source.ak')
    def test_fetch_kline_em(self, mock_ak):
        mock_df = pd.DataFrame({"日期": ["2024-01-02"], "开盘": [10.0]})
        mock_ak.stock_zh_a_hist.return_value = mock_df

        adapter = AkShareAdapter()
        df = adapter.fetch_kline_em("000001", "20240101", "20240131")
        assert not df.empty
        mock_ak.stock_zh_a_hist.assert_called_once_with(
            symbol="000001", period="daily",
            start_date="20240101", end_date="20240131", adjust="qfq"
        )

    @patch('data_source.ak')
    def test_fetch_kline_em_returns_none_for_empty(self, mock_ak):
        mock_ak.stock_zh_a_hist.return_value = pd.DataFrame()
        adapter = AkShareAdapter()
        df = adapter.fetch_kline_em("000001", "20240101", "20240131")
        assert df is not None  # 返回空 DataFrame，不是 None
        assert df.empty

    @patch('data_source.ak')
    def test_fetch_kline_with_fallback_first_works(self, mock_ak):
        """fallback 方法：第一个数据源就成功"""
        mock_df = pd.DataFrame({"日期": ["2024-01-02"]})
        mock_ak.stock_zh_a_hist.return_value = mock_df

        adapter = AkShareAdapter()
        df = adapter.fetch_kline_with_fallback("000001", "20240101", "20240131")
        assert not df.empty

    @patch('data_source.ak')
    def test_fetch_kline_with_fallback_first_fails_second_works(self, mock_ak):
        """fallback 方法：第一个数据源失败，第二个成功"""
        mock_ak.stock_zh_a_hist.side_effect = ConnectionError("EM failed")
        mock_ak.stock_zh_a_daily.return_value = pd.DataFrame({"日期": ["2024-01-02"]})

        adapter = AkShareAdapter()
        # 第二个数据源 sina 会调用 fetch_kline_sina -> ak.stock_zh_a_daily
        df = adapter.fetch_kline_with_fallback("000001", "20240101", "20240131")
        assert df is not None

    @patch('data_source.ak')
    def test_fetch_kline_with_fallback_all_fail(self, mock_ak):
        """fallback 方法：所有数据源失败"""
        mock_ak.stock_zh_a_hist.side_effect = ConnectionError("EM failed")
        mock_ak.stock_zh_a_daily.side_effect = ConnectionError("Sina failed")
        mock_ak.stock_zh_a_hist_tx.side_effect = AttributeError("No such function")

        adapter = AkShareAdapter()
        df = adapter.fetch_kline_with_fallback("000001", "20240101", "20240131")
        assert df is None  # 所有源都失败返回 None

    @patch('data_source.ak')
    def test_fetch_realtime_with_fallback(self, mock_ak):
        mock_ak.stock_zh_a_spot_em.return_value = pd.DataFrame({"代码": ["000001"]})
        adapter = AkShareAdapter()
        df = adapter.fetch_realtime_with_fallback()
        assert not df.empty

    @patch('data_source.ak')
    def test_fetch_stock_basic_with_none_source(self, mock_ak):
        """source_config 为 None 时使用默认"""
        mock_ak.stock_zh_a_spot_em.return_value = pd.DataFrame({"代码": ["000001"]})
        adapter = AkShareAdapter()
        df = adapter.fetch_stock_basic(source_config=None)
        assert not df.empty

    @patch('data_source.ak')
    def test_fetch_stock_basic_with_source_name(self, mock_ak):
        """根据 source_config.name 选择数据源"""
        mock_ak.stock_zh_a_spot_em.return_value = pd.DataFrame({"代码": ["000001"]})
        adapter = AkShareAdapter()
        source = DataSourceConfig(name="akshare_em", type="akshare", priority=1)
        df = adapter.fetch_stock_basic(source_config=source)
        assert not df.empty
        mock_ak.stock_zh_a_spot_em.assert_called_once()
