"""
pytest fixtures - 共享测试资源
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from unittest.mock import MagicMock, patch
from sqlalchemy import create_engine

from config import Config, DatabaseConfig, RetryConfig, CollectorConfig, DataSourceConfig


@pytest.fixture
def test_config():
    """测试用配置"""
    config = Config()
    config.database = DatabaseConfig(
        host="localhost",
        port=3306,
        username="test_user",
        password="test_pass",
        database="test_db",
        pool_size=2,
        max_overflow=5,
        pool_timeout=10,
    )
    config.retry = RetryConfig(max_retries=2, base_delay=0.01, max_delay=0.1)
    config.collector = CollectorConfig(thread_pool_size=2, batch_size=10, request_delay=0)
    return config


@pytest.fixture
def mock_engine():
    """模拟数据库引擎"""
    engine = MagicMock()
    return engine


@pytest.fixture
def mock_session():
    """模拟数据库 session"""
    session = MagicMock()
    return session


@pytest.fixture
def sample_stock_df():
    """样本股票基础信息 DataFrame"""
    import pandas as pd
    return pd.DataFrame([
        {"代码": "000001", "名称": "平安银行", "market": "主板"},
        {"代码": "000002", "名称": "万科A", "market": "主板"},
        {"代码": "600000", "名称": "浦发银行", "market": "主板"},
        {"代码": "300750", "名称": "宁德时代", "market": "创业板"},
        {"代码": "688981", "名称": "中芯国际", "market": "科创板"},
    ])


@pytest.fixture
def sample_kline_df():
    """样本K线数据 DataFrame"""
    import pandas as pd
    return pd.DataFrame([
        {
            "日期": "2024-01-02", "开盘": 10.0, "最高": 10.5, "最低": 9.8,
            "收盘": 10.3, "昨收": 9.9, "成交量": 1000000,
            "成交额": 10200000.0, "换手率": 2.5, "涨跌幅": 4.04
        },
        {
            "日期": "2024-01-03", "开盘": 10.3, "最高": 10.8, "最低": 10.2,
            "收盘": 10.6, "昨收": 10.3, "成交量": 1200000,
            "成交额": 12600000.0, "换手率": 3.0, "涨跌幅": 2.91
        },
    ])


@pytest.fixture
def sample_realtime_df():
    """样本实时行情 DataFrame"""
    import pandas as pd
    return pd.DataFrame([
        {
            "代码": "000001", "名称": "平安银行", "最新价": 10.50, "今开": 10.20,
            "最高": 10.60, "最低": 10.15, "昨收": 10.30,
            "成交量": 5000000, "成交额": 52000000.0,
            "买一": 10.49, "卖一": 10.51,
            "涨跌额": 0.20, "涨跌幅": 1.94
        },
    ])
