"""
Provider 加载器

从 providers.yaml 读取配置，加载适配器类，注入运行时参数。
零硬编码：所有数据源的 priority/quality_score/enabled 均由 YAML 配置。
"""
from __future__ import annotations

import importlib
import os
from pathlib import Path
from typing import List, Optional, Dict, Any

import yaml

from utils import logger


class ProviderConfig:
    """单个 Provider 的配置数据"""

    def __init__(self, name: str, config: Dict[str, Any]):
        self.name = name
        self.class_path: str = config.get("class", "")
        self.provider_type: str = config.get("type", "unknown")
        self.enabled: bool = config.get("enabled", True)
        self.priority: int = config.get("priority", 99)
        self.cost_type: str = config.get("cost_type", "free")
        self.description: str = config.get("description", "")
        self.capability_scores: Dict[str, float] = {}

        capabilities = config.get("capabilities", {})
        for cat_name, cat_config in capabilities.items():
            self.capability_scores[cat_name] = cat_config.get("quality_score", 0.5)


class OrchestrationConfig:
    """编排策略配置"""

    def __init__(self, config: Dict[str, Any]):
        self.field_completion: Dict[str, Dict] = {}
        self.required_fields: Dict[str, List[str]] = {}
        self.expected_fields: Dict[str, List[str]] = {}

        for category, cat_config in config.items():
            if "field_completion" in cat_config:
                self.field_completion[category] = cat_config["field_completion"]
            if "required_fields" in cat_config:
                self.required_fields[category] = cat_config["required_fields"]
            if "expected_fields" in cat_config:
                self.expected_fields[category] = cat_config["expected_fields"]


class ProviderLoader:
    """从 YAML 配置加载并实例化 Provider

    职责：
    1. 读取 providers.yaml
    2. 动态 import 适配器类
    3. 将配置注入到 Provider 实例（priority/quality/enabled）
    4. 返回配置好的 Provider 列表
    """

    def __init__(self, config_path: str = None):
        if config_path is None:
            config_path = Path(__file__).parent.parent / "providers.yaml"
        self.config_path = Path(config_path)
        self._provider_configs: Dict[str, ProviderConfig] = {}
        self._orchestration_config: Optional[OrchestrationConfig] = None

    def load_config(self) -> None:
        """解析 YAML 配置文件"""
        if not self.config_path.exists():
            logger.warning(f"Provider 配置文件不存在: {self.config_path}")
            return

        with open(self.config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        # 解析 Provider 配置
        providers_data = data.get("providers", {})
        for name, cfg in providers_data.items():
            self._provider_configs[name] = ProviderConfig(name, cfg)

        # 解析编排策略配置
        orchestration_data = data.get("orchestration", {})
        if orchestration_data:
            self._orchestration_config = OrchestrationConfig(orchestration_data)

        logger.info(f"加载 {len(self._provider_configs)} 个 Provider 配置")

    def load_provider(self, name: str):
        """加载单个 Provider 实例"""
        if not self._provider_configs:
            self.load_config()

        config = self._provider_configs.get(name)
        if config is None:
            logger.error(f"Provider 配置不存在: {name}")
            return None

        if not config.enabled:
            logger.info(f"Provider {name} 已禁用，跳过加载")
            return None

        if not config.class_path:
            logger.error(f"Provider {name} 未配置 class 路径")
            return None

        try:
            # 动态导入适配器类
            module_path, class_name = config.class_path.rsplit(".", 1)
            module = importlib.import_module(module_path)
            provider_class = getattr(module, class_name)

            # 实例化
            provider = provider_class()

            # 注入配置：provider.set_config()
            provider.set_config(
                priority=config.priority,
                quality_score=None,  # 由每个 capability 单独设置
                cost_type=config.cost_type,
                enabled=config.enabled,
            )

            # 注入每个 capability 的质量评分
            if hasattr(provider, "_capability_scores"):
                provider._capability_scores = config.capability_scores

            logger.info(f"加载 Provider: {name} (priority={config.priority}, type={config.provider_type})")
            return provider

        except (ImportError, AttributeError) as e:
            logger.error(f"加载 Provider {name} 失败，无法导入 {config.class_path}: {e}")
            return None
        except Exception as e:
            logger.error(f"加载 Provider {name} 失败: {e}")
            return None

    def load_all_providers(self) -> List:
        """加载所有已启用的 Provider 实例"""
        if not self._provider_configs:
            self.load_config()

        providers = []
        for name in self._provider_configs:
            provider = self.load_provider(name)
            if provider is not None:
                providers.append(provider)

        # 按优先级排序（数字越小越优先）
        providers.sort(key=lambda p: p.priority if hasattr(p, 'priority') else 99)
        logger.info(f"共加载 {len(providers)} 个 Provider")

        return providers

    def get_orchestration_config(self) -> Optional[OrchestrationConfig]:
        """获取编排策略配置"""
        if self._orchestration_config is None and self._provider_configs:
            self.load_config()
        return self._orchestration_config

    def reload(self) -> List:
        """重新加载配置和所有 Provider"""
        self._provider_configs.clear()
        self._orchestration_config = None
        self.load_config()
        return self.load_all_providers()

    def list_available(self) -> List[Dict[str, Any]]:
        """列出所有可用的 Provider 配置（用于 Web API）"""
        if not self._provider_configs:
            self.load_config()

        result = []
        for name, config in self._provider_configs.items():
            result.append({
                "name": name,
                "type": config.provider_type,
                "enabled": config.enabled,
                "priority": config.priority,
                "cost_type": config.cost_type,
                "description": config.description,
                "capabilities": config.capability_scores,
            })
        return sorted(result, key=lambda x: x["priority"])


# 全局加载器实例
loader = ProviderLoader()
