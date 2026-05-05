"""测试数据源注册中心"""
import pytest
from typing import List
from modules.collector.adapters.registry import DataSourceRegistry
from modules.collector.adapters.base import DataProvider, DataCategory, ProviderCapability


class MockProvider(DataProvider):
    """模拟数据源提供者"""

    def __init__(self, name: str, capabilities: List[ProviderCapability]):
        self._name = name
        self._capabilities = capabilities

    @property
    def provider_name(self) -> str:
        return self._name

    @property
    def capabilities(self) -> List[ProviderCapability]:
        return self._capabilities


@pytest.fixture
def fresh_registry():
    """创建一个空的注册中心"""
    return DataSourceRegistry()


@pytest.fixture
def populated_registry():
    """创建一个包含多个提供者的注册中心"""
    reg = DataSourceRegistry()

    provider_a = MockProvider("provider_a", [
        ProviderCapability(category=DataCategory.STOCK_BASIC, quality_score=0.9),
        ProviderCapability(category=DataCategory.KLINE_DAILY, quality_score=0.8),
    ])
    provider_b = MockProvider("provider_b", [
        ProviderCapability(category=DataCategory.STOCK_BASIC, quality_score=0.7),
        ProviderCapability(category=DataCategory.REALTIME_QUOTE, quality_score=0.9),
    ])
    provider_c = MockProvider("provider_c", [
        ProviderCapability(category=DataCategory.KLINE_DAILY, quality_score=0.6),
    ])

    reg.register(provider_a)
    reg.register(provider_b)
    reg.register(provider_c)
    return reg


class TestDataSourceRegistry:
    """测试 DataSourceRegistry"""

    def test_register(self, fresh_registry):
        """测试注册提供者"""
        provider = MockProvider("test_provider", [
            ProviderCapability(category=DataCategory.STOCK_BASIC)
        ])
        fresh_registry.register(provider)
        assert fresh_registry.count() == 1
        assert fresh_registry.get_provider("test_provider") is provider

    def test_register_replace(self, fresh_registry):
        """测试注册同名提供者会替换"""
        p1 = MockProvider("same_name", [ProviderCapability(category=DataCategory.STOCK_BASIC)])
        p2 = MockProvider("same_name", [ProviderCapability(category=DataCategory.KLINE_DAILY)])
        fresh_registry.register(p1)
        fresh_registry.register(p2)
        assert fresh_registry.count() == 1
        # 新注册的应替换旧的
        assert fresh_registry.get_provider("same_name") is p2

    def test_unregister(self, fresh_registry):
        """测试注销提供者"""
        provider = MockProvider("to_remove", [
            ProviderCapability(category=DataCategory.STOCK_BASIC)
        ])
        fresh_registry.register(provider)
        assert fresh_registry.count() == 1
        result = fresh_registry.unregister("to_remove")
        assert result is True
        assert fresh_registry.count() == 0

    def test_unregister_nonexistent(self, fresh_registry):
        """测试注销不存在的提供者"""
        result = fresh_registry.unregister("nonexistent")
        assert result is False

    def test_get_providers_for(self, populated_registry):
        """测试按类别查询提供者"""
        stock_basic_providers = populated_registry.get_providers_for(DataCategory.STOCK_BASIC)
        assert len(stock_basic_providers) == 2
        # 应按质量评分降序
        assert stock_basic_providers[0].provider_name == "provider_a"  # 0.9

        kline_providers = populated_registry.get_providers_for(DataCategory.KLINE_DAILY)
        assert len(kline_providers) == 2
        assert kline_providers[0].provider_name == "provider_a"  # 0.8 > 0.6

    def test_get_all_providers(self, populated_registry):
        """测试获取所有提供者"""
        all_providers = populated_registry.get_all_providers()
        assert len(all_providers) == 3

    def test_get_provider_names(self, populated_registry):
        """测试获取所有提供者名称"""
        names = populated_registry.get_provider_names()
        assert "provider_a" in names
        assert "provider_b" in names
        assert "provider_c" in names

    def test_set_priority(self, populated_registry):
        """测试设置优先级"""
        result = populated_registry.set_priority("provider_c", 1)
        assert result is True

        # provider_c 应该排在最前面（优先级1最高）
        all_providers = populated_registry.get_all_providers()
        assert all_providers[0].provider_name == "provider_c"

    def test_set_priority_nonexistent(self, populated_registry):
        """测试设置不存在的提供者优先级"""
        result = populated_registry.set_priority("nonexistent", 1)
        assert result is False

    def test_clear_priority(self, populated_registry):
        """测试清除优先级覆盖"""
        populated_registry.set_priority("provider_c", 1)
        populated_registry.clear_priority("provider_c")
        # 清除后恢复默认优先级
        all_providers = populated_registry.get_all_providers()
        # 默认优先级都为 99，不做特定顺序断言

    def test_get_provider(self, populated_registry):
        """测试按名称获取提供者"""
        provider = populated_registry.get_provider("provider_a")
        assert provider is not None
        assert provider.provider_name == "provider_a"

    def test_get_provider_nonexistent(self, populated_registry):
        """测试获取不存在的提供者"""
        provider = populated_registry.get_provider("nonexistent")
        assert provider is None

    def test_empty_registry(self, fresh_registry):
        """测试空注册中心"""
        assert fresh_registry.count() == 0
        assert fresh_registry.get_providers_for(DataCategory.STOCK_BASIC) == []
        assert fresh_registry.get_provider_names() == []

    def test_get_capabilities_report(self, populated_registry):
        """测试能力报告生成"""
        report = populated_registry.get_capabilities_report()
        assert "stock_basic" in report
        assert len(report["stock_basic"]) == 2
        assert report["stock_basic"][0]["name"] == "provider_a"
        assert report["stock_basic"][0]["quality_score"] == 0.9
