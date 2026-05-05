"""测试数据源适配器抽象基类"""
import pytest
from modules.collector.adapters.base import DataCategory, ProviderCapability, DataProvider
from modules.collector.adapters import registry


class TestDataCategory:
    """测试 DataCategory 枚举"""

    def test_values(self):
        assert DataCategory.STOCK_BASIC.value == "stock_basic"
        assert DataCategory.STOCK_INDUSTRY.value == "stock_industry"
        assert DataCategory.STOCK_AREA.value == "stock_area"
        assert DataCategory.KLINE_DAILY.value == "kline_daily"
        assert DataCategory.REALTIME_QUOTE.value == "realtime_quote"

    def test_unique_values(self):
        values = [c.value for c in DataCategory]
        assert len(values) == len(set(values))


class TestProviderCapability:
    """测试 ProviderCapability 数据类"""

    def test_default_values(self):
        cap = ProviderCapability(category=DataCategory.STOCK_BASIC)
        assert cap.category == DataCategory.STOCK_BASIC
        assert cap.fields == []
        assert cap.quality_score == 0.5
        assert cap.cost_type == "free"
        assert cap.latency_ms == 100

    def test_custom_values(self):
        cap = ProviderCapability(
            category=DataCategory.KLINE_DAILY,
            fields=["open", "high", "low", "close"],
            quality_score=0.9,
            cost_type="free",
            latency_ms=150
        )
        assert cap.quality_score == 0.9
        assert len(cap.fields) == 4

    def test_to_dict(self):
        cap = ProviderCapability(
            category=DataCategory.REALTIME_QUOTE,
            fields=["symbol", "price"],
            quality_score=0.8
        )
        d = cap.to_dict()
        assert d["category"] == "realtime_quote"
        assert d["fields"] == ["symbol", "price"]
        assert d["quality_score"] == 0.8
        assert d["cost_type"] == "free"


class TestDataProvider:
    """测试 DataProvider 抽象基类"""

    def test_supports(self):
        """测试能力检查"""
        # 获取已注册的提供者
        em_provider = registry.get_provider("eastmoney")
        assert em_provider is not None

        # 检查是否支持基础信息
        assert em_provider.supports(DataCategory.STOCK_BASIC)
        assert em_provider.supports(DataCategory.KLINE_DAILY)
        assert em_provider.supports(DataCategory.REALTIME_QUOTE)

    def test_get_capability(self):
        """测试获取能力声明"""
        em_provider = registry.get_provider("eastmoney")
        cap = em_provider.get_capability(DataCategory.STOCK_BASIC)
        assert cap is not None
        assert cap.quality_score == 0.8
        assert "symbol" in cap.fields

    def test_supports_not_implemented(self):
        """测试不支持的能力"""
        em_provider = registry.get_provider("eastmoney")
        # 东方财富不支持 STOCK_AREA
        assert not em_provider.supports(DataCategory.STOCK_AREA)

    def test_provider_to_dict(self):
        """测试提供者序列化"""
        em_provider = registry.get_provider("eastmoney")
        d = em_provider.to_dict()
        assert d["name"] == "eastmoney"
        assert len(d["capabilities"]) > 0

    def test_not_implemented_raises(self):
        """测试未实现方法抛出 NotImplementedError"""
        class IncompleteProvider(DataProvider):
            @property
            def provider_name(self):
                return "test"
            @property
            def capabilities(self):
                return []

        provider = IncompleteProvider()
        with pytest.raises(NotImplementedError):
            provider.fetch_industry_mapping()

    def test_not_implemented_for_area(self):
        """测试地域能力未实现"""
        em_provider = registry.get_provider("eastmoney")
        assert not em_provider.supports(DataCategory.STOCK_AREA)

    def test_provider_names(self):
        """测试所有内置提供者名称"""
        names = registry.get_provider_names()
        assert "eastmoney" in names
        assert "sina" in names
        assert "tencent" in names
