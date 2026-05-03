"""
数据源注册中心

管理所有数据源适配器的注册、查询、优先级排序。
支持运行时动态添加/移除 Provider。
"""
from typing import List, Optional, Dict
from .base import DataProvider, DataCategory


class DataSourceRegistry:
    """数据源注册中心

    职责:
    - 注册/注销数据源适配器
    - 按数据类别查询可用数据源（自动过滤 disabled）
    - 按优先级排序
    - 生成能力报告
    """

    def __init__(self):
        self._providers: List[DataProvider] = []
        self._priority_overrides: Dict[str, int] = {}

    def register(self, provider: DataProvider) -> None:
        """注册数据源适配器（同名则替换）"""
        self._providers = [p for p in self._providers
                           if p.provider_name != provider.provider_name]
        self._providers.append(provider)
        self._sort()

    def unregister(self, provider_name: str) -> bool:
        """注销数据源适配器"""
        before = len(self._providers)
        self._providers = [p for p in self._providers
                           if p.provider_name != provider_name]
        self._priority_overrides.pop(provider_name, None)
        return len(self._providers) < before

    def register_all(self, providers: List[DataProvider]) -> None:
        """批量注册"""
        for p in providers:
            self.register(p)

    def _sort(self) -> None:
        """按优先级排序（数字越小越优先）"""
        self._providers.sort(key=lambda p: p.priority if p.priority else 99)

    def set_priority(self, provider_name: str, priority: int) -> bool:
        """覆盖数据源优先级"""
        for p in self._providers:
            if p.provider_name == provider_name:
                p._priority = priority
                self._sort()
                return True
        return False

    def get_providers_for(self, category: DataCategory) -> List[DataProvider]:
        """获取能提供指定数据类别的 Provider 列表

        - 自动过滤 disabled 的 Provider
        - 按优先级排序
        """
        providers = [
            p for p in self._providers
            if p.enabled and p.supports(category)
        ]
        return providers

    def get_all_providers(self, include_disabled: bool = False) -> List[DataProvider]:
        """获取所有已注册的 Provider"""
        if include_disabled:
            return self._providers.copy()
        return [p for p in self._providers if p.enabled]

    def get_provider(self, name: str) -> Optional[DataProvider]:
        """按名称获取 Provider"""
        for p in self._providers:
            if p.provider_name == name:
                return p
        return None

    def get_capabilities_report(self) -> Dict:
        """生成能力报告（用于 Web API）"""
        report = {}
        for category in DataCategory:
            providers = self.get_providers_for(category)
            report[category.value] = [
                {
                    "name": p.provider_name,
                    "priority": p.priority,
                    "cost_type": p._capability_scores.get(category.value, "free"),
                    "quality_score": p._get_quality_score(category),
                    "fields": p.get_standard_fields(category),
                    "field_coverage": p.get_capability(category).field_coverage if p.get_capability(category) else 0,
                }
                for p in providers
            ]
        return report

    def get_provider_names(self) -> List[str]:
        """获取所有已注册的 Provider 名称"""
        return [p.provider_name for p in self._providers]

    def count(self, include_disabled: bool = True) -> int:
        """获取已注册的 Provider 数量"""
        if include_disabled:
            return len(self._providers)
        return self.provider_count

    def clear_priority(self, provider_name: str) -> bool:
        """清除优先级覆盖，恢复默认优先级"""
        for p in self._providers:
            if p.provider_name == provider_name:
                p._priority = 99
                self._sort()
                return True
        return False

    @property
    def provider_count(self) -> int:
        return len([p for p in self._providers if p.enabled])

    @property
    def total_count(self) -> int:
        return len(self._providers)


# 全局注册中心实例
registry = DataSourceRegistry()
