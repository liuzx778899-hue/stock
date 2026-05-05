"""测试数据编排器"""
from unittest.mock import patch, MagicMock
import pandas as pd
import pytest
from modules.collector.adapters.base import DataCategory
from modules.collector.services.data_orchestrator import DataOrchestrator


class MockProgressCallback:
    """模拟进度回调"""

    def __init__(self):
        self.calls = []

    def __call__(self, current, total, stage):
        self.calls.append((current, total, stage))


class TestDataOrchestrator:
    """测试 DataOrchestrator"""

    def setup_method(self):
        self.orchestrator = DataOrchestrator()

    def test_get_providers(self):
        """测试获取提供者列表"""
        providers = self.orchestrator.get_providers(DataCategory.STOCK_BASIC)
        assert len(providers) >= 1
        # 验证返回的 Provider 都支持请求的类别
        for p in providers:
            assert p.supports(DataCategory.STOCK_BASIC)

    def test_get_providers_all_categories(self):
        """测试所有类别都有提供者"""
        for category in DataCategory:
            providers = self.orchestrator.get_providers(category)
            assert len(providers) >= 1, f"{category} 没有可用的提供者"

    def test_get_registry(self):
        """测试获取注册中心"""
        reg = self.orchestrator.get_registry()
        assert reg is not None
        assert reg.count() >= 3  # 至少 3 个内置提供者

    def test_fetch_with_fallback_all_fail(self):
        """测试所有数据源都失败的情况"""
        mock_provider = MagicMock()
        mock_provider.provider_name = "test_provider"
        mock_provider.supports.return_value = True
        mock_provider.fetch_stock_basic.side_effect = Exception("API Error")

        self.orchestrator.registry = MagicMock()
        self.orchestrator.registry.get_providers_for.return_value = [mock_provider]

        result = self.orchestrator._fetch_with_fallback(DataCategory.STOCK_BASIC)
        assert result is None

    def test_field_report_initial(self):
        """测试初始字段报告"""
        report = self.orchestrator.get_field_report()
        assert report == {}

    @patch.object(DataOrchestrator, 'get_providers')
    def test_supplement_field_not_needed(self, mock_get_providers):
        """测试字段覆盖充分时不需要补充"""
        df = pd.DataFrame({
            "symbol": ["000001", "000002"],
            "industry": ["金融", "地产"]
        })
        result = self.orchestrator._supplement_field(df, DataCategory.STOCK_INDUSTRY, "industry")
        assert len(result) == 2
        assert result["industry"].tolist() == ["金融", "地产"]
        # 覆盖率 > 90%，不需要调用 provider
        mock_get_providers.assert_not_called()

    def test_collect_kline_no_symbol(self):
        """测试采集不存在股票的 K 线"""
        df = self.orchestrator.collect_kline("999999", "20240101", "20240105")
        # 可能返回空 DataFrame 或抛出异常
        assert isinstance(df, pd.DataFrame)

    def test_collect_realtime(self):
        """测试采集实时行情"""
        df = self.orchestrator.collect_realtime()
        assert isinstance(df, pd.DataFrame)

    @patch.object(DataOrchestrator, 'collect_kline')
    def test_collect_batch_kline_stop(self, mock_collect_kline):
        """测试批量采集停止"""
        mock_collect_kline.return_value = pd.DataFrame({
            "open": [1.0], "high": [1.5], "low": [0.5], "close": [1.2]
        })

        stop_check = lambda: True  # 立即停止
        results = self.orchestrator.collect_kline_batch(
            ["000001", "000002"], "20240101", "20240105",
            stop_check=stop_check
        )
        assert len(results) == 0  # 停止时尚未处理任何股票

    def test_collect_kline_batch_empty(self):
        """测试空列表批量采集"""
        results = self.orchestrator.collect_kline_batch([], "20240101", "20240105")
        assert results == {}

    def test_progress_callback_kline(self):
        """测试 K 线采集进度回调"""
        callback = MockProgressCallback()
        results = self.orchestrator.collect_kline_batch(
            ["000001"], "20240101", "20240105",
            progress_callback=callback
        )
        # 至少有一次进度回调
        assert len(callback.calls) >= 1
        symbol_progress = [c for c in callback.calls if "采集" in str(c[2])]
        assert len(symbol_progress) >= 1

    def test_collect_stock_basic_with_callback(self):
        """测试基础信息采集进度回调"""
        callback = MockProgressCallback()
        df = self.orchestrator.collect_stock_basic(progress_callback=callback)
        if not df.empty:
            assert len(callback.calls) > 0
            # 应有 3 个 stage
            unique_stages = len(set(c[2] for c in callback.calls))
            assert unique_stages >= 2  # 至少 2 个不同阶段
