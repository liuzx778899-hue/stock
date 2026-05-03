"""
测试 config.py - 配置文件模块
"""
import os
import pytest
from dataclasses import asdict

from config import (
    Config, DatabaseConfig, RetryConfig, CollectorConfig,
    DataSourceConfig, MultiDatabaseConfig, config as global_config
)


class TestDatabaseConfig:
    """测试数据库配置"""

    def test_default_values(self):
        db = DatabaseConfig()
        assert db.host == "192.168.2.32"
        assert db.port == 2881
        assert db.username == "root@hdw"
        assert db.pool_size == 10
        assert db.max_overflow == 20
        assert db.pool_timeout == 30

    def test_connection_url_format(self):
        db = DatabaseConfig(host="10.0.0.1", port=3306, username="user", password="pass", database="mydb")
        url = db.connection_url
        assert "mysql+pymysql://user:pass@10.0.0.1:3306/mydb" in url
        assert "charset=utf8mb4" in url

    def test_custom_values(self):
        db = DatabaseConfig(host="db.example.com", port=3307, pool_size=20)
        assert db.host == "db.example.com"
        assert db.port == 3307
        assert db.pool_size == 20

    def test_password_falls_back_to_env_or_default(self):
        """密码为空时回退到环境变量或默认值 - BUG-014 已修复"""
        db = DatabaseConfig(password="")
        # __post_init__ 自动从环境变量或默认值填充
        assert db.password != ""


class TestDataSourceConfig:
    """测试数据源配置"""

    def test_default_values(self):
        ds = DataSourceConfig(name="test", type="akshare")
        assert ds.name == "test"
        assert ds.priority == 1
        assert ds.enabled is True
        assert ds.api_key is None

    def test_disabled_source(self):
        ds = DataSourceConfig(name="disabled_source", type="akshare", enabled=False)
        assert ds.enabled is False

    def test_priority_ordering(self):
        sources = [
            DataSourceConfig(name="low", type="akshare", priority=3),
            DataSourceConfig(name="high", type="akshare", priority=1),
            DataSourceConfig(name="mid", type="akshare", priority=2),
        ]
        sources.sort(key=lambda x: x.priority)
        assert sources[0].name == "high"
        assert sources[1].name == "mid"
        assert sources[2].name == "low"


class TestConfig:
    """测试总配置"""

    def test_default_post_init(self):
        cfg = Config()
        assert cfg.database is not None
        assert cfg.retry is not None
        assert cfg.collector is not None
        assert cfg.data_sources is not None
        assert len(cfg.data_sources) == 3

    def test_get_enabled_data_sources(self):
        cfg = Config()
        sources = cfg.get_enabled_data_sources()
        assert len(sources) >= 1
        assert all(s.enabled for s in sources)
        # 验证按优先级排序
        priorities = [s.priority for s in sources]
        assert priorities == sorted(priorities)

    def test_get_enabled_data_sources_with_disabled(self):
        cfg = Config()
        cfg.data_sources[1].enabled = False  # disable sina
        sources = cfg.get_enabled_data_sources()
        assert len(sources) == 2
        assert sources[0].name == "akshare_em"
        assert sources[1].name == "akshare_tencent"

    def test_get_primary_data_source(self):
        cfg = Config()
        primary = cfg.get_primary_data_source()
        assert primary is not None
        assert primary.priority == 1

    def test_get_primary_data_source_all_disabled(self):
        cfg = Config()
        for ds in cfg.data_sources:
            ds.enabled = False
        primary = cfg.get_primary_data_source()
        assert primary is None  # 边界：没有可用数据源

    def test_default_data_sources_have_required_fields(self):
        cfg = Config()
        for ds in cfg.data_sources:
            assert ds.name
            assert ds.type
            assert ds.priority >= 1
            assert isinstance(ds.enabled, bool)


class TestMultiDatabaseConfig:
    """测试多数据库配置"""

    def test_default_post_init(self):
        multi = MultiDatabaseConfig()
        assert multi.master is not None
        assert len(multi.slaves) >= 1

    def test_get_slave(self):
        multi = MultiDatabaseConfig(slaves=[
            DatabaseConfig(host="slave1"),
            DatabaseConfig(host="slave2"),
        ])
        slave = multi.get_slave()
        assert slave.host in ("slave1", "slave2")

    def test_get_slave_empty_falls_back_to_master(self):
        multi = MultiDatabaseConfig(master=DatabaseConfig(host="master"), slaves=[DatabaseConfig(host="slave1")])
        # 清除 slaves 列表来模拟空列表情况
        multi.slaves = []
        slave = multi.get_slave()
        # 当 slaves 为空时回退到 master
        assert slave == multi.master


class TestRetryConfig:
    """测试重试配置"""

    def test_default_values(self):
        rc = RetryConfig()
        assert rc.max_retries == 3
        assert rc.base_delay == 1.0
        assert rc.max_delay == 60.0
        assert rc.exponential_base == 2.0


class TestCollectorConfig:
    """测试采集器配置"""

    def test_default_values(self):
        cc = CollectorConfig()
        assert cc.thread_pool_size == 10
        assert cc.batch_size == 50
        assert cc.request_delay == 0.1


class TestGlobalConfig:
    """测试全局配置实例"""

    def test_global_config_exists(self):
        assert global_config is not None
        assert isinstance(global_config, Config)

    def test_global_config_database_url(self):
        url = global_config.database.connection_url
        assert url.startswith("mysql+pymysql://")
        assert "192.168.2.32" in url
        assert "2881" in url
