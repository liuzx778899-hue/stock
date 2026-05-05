"""
数据源适配器模块

提供统一的数据源注册和发现机制。

使用方式:
    from adapters import registry, init_providers

    # 初始化（从 providers.yaml 加载所有 Provider）
    init_providers()

    # 查询
    providers = registry.get_providers_for(DataCategory.KLINE_DAILY)

添加新数据源:
    1. 编写适配器类（继承 DataProvider）
    2. 在 providers.yaml 中添加配置
    3. 重启服务即可生效（零代码改动）
"""
from modules.collector.adapters.base import (
    DataProvider,
    DataCategory,
    ProviderCapability,
    CATEGORY_STANDARD_FIELDS,
)
from modules.collector.adapters.registry import registry, DataSourceRegistry
from modules.collector.adapters.loader import loader, ProviderLoader
from utils import logger


def init_providers(reload: bool = False) -> int:
    """从 providers.yaml 加载并注册所有数据源

    Args:
        reload: 是否强制重新加载配置

    Returns:
        成功注册的 Provider 数量
    """
    if reload:
        loader.load_config()

    providers = loader.load_all_providers()
    registry.register_all(providers)

    orchestration_config = loader.get_orchestration_config()
    if orchestration_config:
        registry.set_orchestration_config(orchestration_config)

    logger.info(f"初始化完成: {registry.provider_count} 个 Provider 已注册")
    return registry.provider_count


# 自动注册内置 Provider（确保 import adapters 后立即可用）
init_providers()

__all__ = [
    "registry",
    "DataSourceRegistry",
    "loader",
    "ProviderLoader",
    "init_providers",
    "DataProvider",
    "DataCategory",
    "ProviderCapability",
    "CATEGORY_STANDARD_FIELDS",
]
