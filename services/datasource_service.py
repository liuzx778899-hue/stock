"""
数据源管理服务

统一管理内置 Provider（通过 registry）和用户自定义数据源（JSON 持久化）。
取代旧的 datasource_manager.py 和 data_source.py 中的数据源管理逻辑。
"""
import json
import time
import uuid
from pathlib import Path
from typing import List, Optional, Dict, Any
from urllib.parse import urlparse

import requests
from pydantic import BaseModel
from requests.auth import HTTPBasicAuth

from utils import logger


class CustomDataSourceConfig(BaseModel):
    """用户自定义数据源"""
    id: Optional[str] = None
    name: str
    type: str = 'http'
    api_url: Optional[str] = None
    api_key: Optional[str] = None
    headers: Optional[dict] = None
    priority: int = 99
    enabled: bool = True
    description: Optional[str] = None
    auth_type: Optional[str] = None
    auth_header: Optional[str] = None
    request_method: str = 'GET'
    request_template: Optional[dict] = None
    response_parser: Optional[str] = None


# 内置 Provider 显示名称映射
PROVIDER_DISPLAY_NAMES = {
    'eastmoney': '东方财富（AkShare）',
    'sina': '新浪（AkShare）',
    'tencent': '腾讯（AkShare）',
    'biying': '必盈 API',
}

# 内置 Provider 默认优先级
BUILTIN_DEFAULT_PRIORITIES = {
    'eastmoney': 1,
    'sina': 2,
    'tencent': 3,
    'biying': 4,
}


class DataSourceService:
    """数据源管理服务

    职责:
    - 列出所有数据源（内置 Provider + 自定义，按优先级排序）
    - 管理自定义数据源（CRUD + 连通性测试）
    - 管理内置数据源优先级
    - 运行时强制数据源选择
    - SSRF 防护（域名白名单 / IP 黑名单）
    """

    # SSRF 防护：允许测试的域名白名单
    ALLOWED_DOMAINS = [
        'eastmoney.com',
        'sina.com.cn',
        'qq.com',
        'tushare.pro',
        'akshare',
        'biyingapi.com',
        'localhost',
        '127.0.0.1',
        '192.168.',
        '10.',
    ]

    # 禁止访问的敏感 IP
    BLOCKED_IPS = [
        '169.254.169.254',  # 云元数据接口
        '0.0.0.0',
    ]

    def __init__(self, registry=None):
        from adapters.registry import registry as _registry
        self.registry = registry or _registry
        self.config_file = Path(__file__).parent.parent / "datasources.json"
        self.custom_sources: List[CustomDataSourceConfig] = []
        self.builtin_priorities: Dict[str, int] = {}
        self._forced_source: Optional[str] = None
        self._load()

    # ==================== 持久化 ====================

    def _load(self):
        """从 JSON 文件加载自定义数据源配置"""
        if not self.config_file.exists():
            return
        try:
            data = json.loads(self.config_file.read_text(encoding='utf-8'))
            self.custom_sources = [CustomDataSourceConfig(**s) for s in data.get('custom_sources', [])]
            self.builtin_priorities = data.get('builtin_priorities', {})
            # 同步已保存的优先级到 registry
            for name, priority in self.builtin_priorities.items():
                self.registry.set_priority(name, priority)
            logger.info(f"加载 {len(self.custom_sources)} 个自定义数据源, {len(self.builtin_priorities)} 个优先级覆盖")
        except Exception as e:
            logger.warning(f"加载数据源配置失败: {e}")

    def _save(self):
        """保存自定义数据源配置到 JSON 文件"""
        try:
            data = {
                'custom_sources': [s.model_dump() for s in self.custom_sources],
                'builtin_priorities': self.builtin_priorities,
            }
            self.config_file.write_text(
                json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8'
            )
        except Exception as e:
            logger.error(f"保存数据源配置失败: {e}")

    # ==================== 列表/展示 ====================

    @staticmethod
    def get_display_name(name: str) -> str:
        """获取数据源显示名称"""
        return PROVIDER_DISPLAY_NAMES.get(name, name)

    def list_all(self) -> List[dict]:
        """获取所有数据源（内置 + 自定义），按优先级排序"""
        builtin = []
        for p in self.registry.get_all_providers(include_disabled=True):
            default_priority = BUILTIN_DEFAULT_PRIORITIES.get(p.provider_name, p.priority)
            effective_priority = self.builtin_priorities.get(p.provider_name, p.priority)
            builtin.append({
                'id': p.provider_name,
                'name': self.get_display_name(p.provider_name),
                'type': p.capabilities[0].cost_type if p.capabilities else 'unknown',
                'priority': effective_priority,
                'default_priority': default_priority,
                'enabled': p.enabled,
                'builtin': True,
                'description': f"内置 Provider，当前优先级 {effective_priority}（默认 {default_priority}）",
            })

        # 自定义数据源（排除 api_key）
        custom = [
            {
                'id': s.id or f'custom_{i}',
                'name': s.name,
                'type': s.type,
                'priority': s.priority,
                'enabled': s.enabled,
                'builtin': False,
                'api_url': s.api_url,
                'description': s.description,
                'auth_type': s.auth_type,
            }
            for i, s in enumerate(self.custom_sources)
        ]

        all_sources = builtin + custom
        return sorted(all_sources, key=lambda x: (x['priority'], x['id']))

    # ==================== 自定义数据源 CRUD ====================

    def add_custom(self, source: CustomDataSourceConfig) -> CustomDataSourceConfig:
        """添加自定义数据源"""
        if not source.id:
            source.id = f"custom_{uuid.uuid4().hex[:8]}"
        self.custom_sources.append(source)
        self._save()
        return source

    def update_custom(self, source_id: str, updates: dict) -> Optional[CustomDataSourceConfig]:
        """更新自定义数据源"""
        for i, s in enumerate(self.custom_sources):
            if s.id == source_id:
                updated = CustomDataSourceConfig(**{**s.model_dump(), **updates})
                self.custom_sources[i] = updated
                self._save()
                return updated
        return None

    def remove_custom(self, source_id: str) -> bool:
        """删除自定义数据源"""
        for i, s in enumerate(self.custom_sources):
            if s.id == source_id:
                self.custom_sources.pop(i)
                self._save()
                return True
        return False

    def get_custom(self, source_id: str) -> Optional[CustomDataSourceConfig]:
        """获取指定自定义数据源"""
        for s in self.custom_sources:
            if s.id == source_id:
                return s
        return None

    # ==================== 内置数据源优先级管理 ====================

    def update_builtin_priority(self, name: str, priority: int) -> bool:
        """更新内置数据源优先级"""
        if name not in BUILTIN_DEFAULT_PRIORITIES:
            return False
        self.builtin_priorities[name] = priority
        self.registry.set_priority(name, priority)
        self._save()
        logger.info(f"更新内置数据源 {name} 优先级为 {priority}")
        return True

    def reset_builtin_priority(self, name: str) -> bool:
        """重置内置数据源优先级为默认值"""
        if name not in BUILTIN_DEFAULT_PRIORITIES:
            return False
        if name in self.builtin_priorities:
            del self.builtin_priorities[name]
        # 恢复到默认优先级而非 99
        default_priority = BUILTIN_DEFAULT_PRIORITIES[name]
        self.registry.set_priority(name, default_priority)
        self._save()
        logger.info(f"重置内置数据源 {name} 优先级为默认值 {default_priority}")
        return True

    # ==================== 连通性测试（含 SSRF 防护） ====================

    def test_connection(self, source: CustomDataSourceConfig) -> dict:
        """测试数据源连通性（含 SSRF 防护）"""
        result = {
            'success': False,
            'message': '',
            'latency_ms': 0,
            'warning': None,
        }

        if not source.api_url:
            result['message'] = 'API URL 未配置'
            return result

        # SSRF 防护
        try:
            parsed = urlparse(source.api_url)
            hostname = parsed.hostname or ''
            if hostname in self.BLOCKED_IPS:
                result['message'] = '禁止访问该地址'
                return result

            is_allowed = any(
                hostname.endswith(domain) or hostname == domain
                for domain in self.ALLOWED_DOMAINS
            )
            if not is_allowed:
                result['warning'] = f'域名 {hostname} 不在推荐列表中，连接可能存在风险'
        except Exception as e:
            result['message'] = f'URL 解析失败: {str(e)}'
            return result

        # 发起测试请求
        try:
            start = time.time()
            headers = source.headers or {}
            if source.auth_type == 'bearer' and source.api_key:
                headers['Authorization'] = f'Bearer {source.api_key}'
            elif source.auth_type == 'api_key' and source.api_key:
                headers[source.auth_header or 'X-API-Key'] = source.api_key
            elif source.auth_type == 'basic' and source.api_key:
                username, _, password = source.api_key.partition(':')
                resp = requests.get(
                    source.api_url, auth=HTTPBasicAuth(username, password),
                    headers=headers, timeout=10,
                )
                latency = int((time.time() - start) * 1000)
                if resp.status_code == 200:
                    result['success'] = True
                    result['message'] = '连接成功'
                    result['latency_ms'] = latency
                else:
                    result['message'] = f'HTTP {resp.status_code}: {resp.reason}'
                return result

            resp = requests.get(source.api_url, headers=headers, timeout=10)
            latency = int((time.time() - start) * 1000)
            if resp.status_code == 200:
                result['success'] = True
                result['message'] = '连接成功'
                result['latency_ms'] = latency
            else:
                result['message'] = f'HTTP {resp.status_code}: {resp.reason}'
        except requests.exceptions.Timeout:
            result['message'] = '连接超时'
        except requests.exceptions.ConnectionError:
            result['message'] = '连接失败（网络错误）'
        except Exception as e:
            result['message'] = f'测试失败: {str(e)}'

        return result

    # ==================== 强制数据源 ====================

    def set_forced_source(self, name: Optional[str]):
        """设置强制数据源（None 表示自动选择）"""
        self._forced_source = name
        if name:
            logger.info(f"强制使用数据源: {name}")
        else:
            logger.info("恢复自动选择数据源")

    def get_forced_source(self) -> Optional[str]:
        """获取当前强制数据源"""
        return self._forced_source

    def get_current_source_name(self) -> str:
        """获取当前数据源显示名称"""
        if self._forced_source:
            return self.get_display_name(self._forced_source)
        return "自动选择"


# 全局数据源管理服务实例
datasource_service = DataSourceService()
