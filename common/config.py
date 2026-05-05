"""
配置文件 - 数据库连接、采集参数等配置
支持多数据源、多数据库配置
支持 .env 配置文件（优先级：环境变量 > .env 文件 > 默认值）
"""
import os
import urllib.parse
from dataclasses import dataclass, field
from typing import List, Optional
import random
from pathlib import Path

# 项目根目录
BASE_DIR = Path(__file__).resolve().parent.parent

# 尝试加载 .env 文件
try:
    from dotenv import load_dotenv
    env_file = BASE_DIR / ".env"
    if env_file.exists():
        load_dotenv(env_file)
except ImportError:
    pass  # python-dotenv 未安装，使用环境变量或默认值


@dataclass
class DatabaseConfig:
    """数据库配置"""
    host: str = "192.168.2.32"
    port: int = 2881
    username: str = "root@hdw"
    password: str = ""  # 从环境变量读取
    database: str = "astock"
    pool_size: int = 10
    max_overflow: int = 20
    pool_timeout: int = 30

    def __post_init__(self):
        if not self.password:
            _pw = os.getenv("DB_PASSWORD")
            self.password = _pw or ""  # 必须设置 DB_PASSWORD 环境变量

    @property
    def connection_url(self) -> str:
        """生成 SQLAlchemy 连接 URL（密码中的特殊字符会被 URL 编码）"""
        encoded_password = urllib.parse.quote(self.password, safe='')
        return (
            f"mysql+pymysql://{self.username}:{encoded_password}"
            f"@{self.host}:{self.port}/{self.database}"
            f"?charset=utf8mb4"
        )


@dataclass
class DataSourceConfig:
    """数据源配置"""
    name: str
    type: str  # 'akshare', 'tushare', 'efinance' 等
    priority: int = 1  # 优先级，数字越小优先级越高
    enabled: bool = True
    api_key: Optional[str] = None
    api_url: Optional[str] = None
    extra_params: dict = field(default_factory=dict)


@dataclass
class MultiDatabaseConfig:
    """多数据库配置（主从/读写分离）"""
    master: DatabaseConfig = None
    slaves: List[DatabaseConfig] = field(default_factory=list)

    def __post_init__(self):
        if self.master is None:
            self.master = DatabaseConfig()
        if not self.slaves:
            self.slaves = [DatabaseConfig()]

    def get_slave(self) -> DatabaseConfig:
        """随机获取一个从库配置"""
        return random.choice(self.slaves) if self.slaves else self.master


@dataclass
class RetryConfig:
    """重试配置"""
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0


@dataclass
class CollectorConfig:
    """采集器配置"""
    thread_pool_size: int = 10
    batch_size: int = 50
    request_delay: float = 0.1  # 请求间隔（秒），防止被封


@dataclass
class TradingHoursConfig:
    """交易时间配置"""
    morning_start: str = "09:30"
    morning_end: str = "11:30"
    afternoon_start: str = "13:00"
    afternoon_end: str = "15:00"
    trading_days: List[int] = None  # 0=周一, 6=周日

    def __post_init__(self):
        if self.trading_days is None:
            self.trading_days = [0, 1, 2, 3, 4]  # 周一到周五


@dataclass
class Config:
    """总配置"""
    database: DatabaseConfig = None
    multi_database: MultiDatabaseConfig = None
    retry: RetryConfig = None
    collector: CollectorConfig = None
    trading_hours: TradingHoursConfig = None

    def __post_init__(self):
        # 清除代理环境变量，防止代理阻塞东方财富数据源连接
        os.environ.pop('HTTP_PROXY', None)
        os.environ.pop('HTTPS_PROXY', None)
        os.environ.pop('http_proxy', None)
        os.environ.pop('https_proxy', None)

        if self.database is None:
            self.database = DatabaseConfig()
        if self.multi_database is None:
            self.multi_database = MultiDatabaseConfig()
        if self.retry is None:
            self.retry = RetryConfig()
        if self.collector is None:
            self.collector = CollectorConfig()
        if self.trading_hours is None:
            self.trading_hours = TradingHoursConfig()


# 全局配置实例
config = Config()