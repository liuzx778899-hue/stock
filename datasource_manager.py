"""
用户自定义数据源配置存储
"""
import json
import time
import uuid
import requests
from pathlib import Path
from typing import List, Optional, Literal
from urllib.parse import urlparse
from pydantic import BaseModel
from utils import logger
from requests.auth import HTTPBasicAuth
from config import config  # 移至顶部避免方法内重复导入

# 认证类型常量（修复 stringly-typed 问题）
AUTH_TYPE_NONE = "none"
AUTH_TYPE_BEARER = "bearer"
AUTH_TYPE_API_KEY = "api_key"
AUTH_TYPE_BASIC = "basic"
AUTH_TYPES = [AUTH_TYPE_NONE, AUTH_TYPE_BEARER, AUTH_TYPE_API_KEY, AUTH_TYPE_BASIC]


class CustomDataSource(BaseModel):
    """用户自定义数据源"""
    id: Optional[str] = None
    name: str
    type: str  # 'http', 'websocket', 'akshare', 'tushare', 'private'
    api_url: Optional[str] = None
    api_key: Optional[str] = None
    headers: Optional[dict] = None
    priority: int = 99  # 用户自定义默认低优先级
    enabled: bool = True
    description: Optional[str] = None

    # 私有接口配置
    auth_type: Optional[str] = None  # 'basic', 'bearer', 'api_key', 'custom'
    auth_header: Optional[str] = None
    request_method: Optional[str] = 'GET'
    request_template: Optional[dict] = None
    response_parser: Optional[str] = None  # JSONPath 或自定义解析器名称


class DataSourceManager:
    """数据源管理器"""

    # 允许测试的域名白名单（防止 SSRF）
    ALLOWED_DOMAINS = [
        'eastmoney.com',
        'sina.com.cn',
        'qq.com',
        'tushare.pro',
        'akshare',
        'localhost',
        '127.0.0.1',
        '192.168.',  # 内网测试
        '10.',  # 内网测试
    ]

    # 禁止访问的敏感 IP
    BLOCKED_IPS = [
        '169.254.169.254',  # 云元数据接口
        '0.0.0.0',
    ]

    def __init__(self):
        self.config_file = Path(__file__).parent / "datasources.json"
        self.custom_sources: List[CustomDataSource] = []
        self.load()

    def load(self):
        """加载用户自定义数据源"""
        if self.config_file.exists():
            try:
                data = json.loads(self.config_file.read_text(encoding='utf-8'))
                self.custom_sources = [CustomDataSource(**s) for s in data.get('custom_sources', [])]
                logger.info(f"加载 {len(self.custom_sources)} 个自定义数据源")
            except Exception as e:
                logger.warning(f"加载数据源配置失败: {e}")
                self.custom_sources = []

    def save(self):
        """保存数据源配置"""
        try:
            data = {
                'custom_sources': [s.model_dump() for s in self.custom_sources]
            }
            self.config_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
            logger.info(f"保存 {len(self.custom_sources)} 个自定义数据源")
        except Exception as e:
            logger.error(f"保存数据源配置失败: {e}")

    def list_all(self) -> List[dict]:
        """获取所有数据源（内置 + 自定义）"""
        # 从 config.data_sources 读取内置数据源
        builtin = [
            {
                'id': ds.name,
                'name': ds.name.replace('akshare_', '').upper() + '（AkShare）',
                'type': ds.type,
                'priority': ds.priority,
                'enabled': ds.enabled,
                'builtin': True,
                'description': f"内置数据源，优先级 {ds.priority}"
            }
            for ds in config.data_sources
        ]

        # 自定义数据源（排除 api_key 字段，修复 BUG-056）
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
                'auth_type': s.auth_type
            }
            for i, s in enumerate(self.custom_sources)
        ]

        return builtin + custom

    def add(self, source: CustomDataSource) -> CustomDataSource:
        """添加自定义数据源"""
        if not source.id:
            # 使用 UUID 避免删除后 ID 冲突（修复 BUG-060）
            source.id = f"custom_{uuid.uuid4().hex[:8]}"
        self.custom_sources.append(source)
        self.save()
        return source

    def update(self, source_id: str, updates: dict) -> Optional[CustomDataSource]:
        """更新数据源配置"""
        for i, s in enumerate(self.custom_sources):
            if s.id == source_id:
                updated = CustomDataSource(**{**s.model_dump(), **updates})
                self.custom_sources[i] = updated
                self.save()
                return updated
        return None

    def remove(self, source_id: str) -> bool:
        """删除自定义数据源"""
        for i, s in enumerate(self.custom_sources):
            if s.id == source_id:
                self.custom_sources.pop(i)
                self.save()
                return True
        return False

    def get(self, source_id: str) -> Optional[CustomDataSource]:
        """获取指定数据源"""
        for s in self.custom_sources:
            if s.id == source_id:
                return s
        return None

    def test_connection(self, source: CustomDataSource) -> dict:
        """测试数据源连通性（含 SSRF 防护）"""

        result = {
            'success': False,
            'message': '',
            'latency_ms': 0
        }

        if not source.api_url:
            result['message'] = 'API URL 未配置'
            return result

        # SSRF 防护：校验 URL（修复 BUG-055）
        try:
            parsed = urlparse(source.api_url)
            hostname = parsed.hostname or ''

            # 检查禁止访问的 IP
            if hostname in self.BLOCKED_IPS:
                result['message'] = '禁止访问该地址'
                return result

            # 检查域名白名单
            is_allowed = any(
                hostname.endswith(domain) or hostname == domain
                for domain in self.ALLOWED_DOMAINS
            )
            if not is_allowed:
                result['message'] = f'域名 {hostname} 不在允许列表中'
                return result
        except Exception as e:
            result['message'] = f'URL 解析失败: {str(e)}'
            return result

        try:
            start = time.time()

            headers = source.headers or {}
            if source.auth_type == 'bearer' and source.api_key:
                headers['Authorization'] = f'Bearer {source.api_key}'
            elif source.auth_type == 'api_key' and source.api_key:
                headers[source.auth_header or 'X-API-Key'] = source.api_key
            elif source.auth_type == 'basic' and source.api_key:
                username, _, password = source.api_key.partition(':')
                response = requests.get(source.api_url, auth=HTTPBasicAuth(username, password),
                                        headers=headers, timeout=10)
                latency = int((time.time() - start) * 1000)
                if response.status_code == 200:
                    result['success'] = True
                    result['message'] = '连接成功'
                    result['latency_ms'] = latency
                else:
                    result['message'] = f'HTTP {response.status_code}: {response.reason}'
                return result

            response = requests.get(source.api_url, headers=headers, timeout=10)
            latency = int((time.time() - start) * 1000)

            if response.status_code == 200:
                result['success'] = True
                result['message'] = '连接成功'
                result['latency_ms'] = latency
            else:
                result['message'] = f'HTTP {response.status_code}: {response.reason}'
        except requests.exceptions.Timeout:
            result['message'] = '连接超时'
        except requests.exceptions.ConnectionError:
            result['message'] = '连接失败（网络错误）'
        except Exception as e:
            result['message'] = f'测试失败: {str(e)}'

        return result


# 全局数据源管理器
datasource_manager = DataSourceManager()
