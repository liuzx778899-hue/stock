"""测试采集器基类"""
from datetime import datetime
from unittest.mock import patch, MagicMock, create_autospec
import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import Session

from collectors.base import BaseCollector
from models import Base as ModelBase, CollectLog


class SimpleCollector(BaseCollector):
    """简化采集器用于测试"""

    def collect(self, **kwargs):
        return {"success": True, "total": 10, "saved": 10}


@pytest.fixture
def memory_engine():
    """内存数据库引擎"""
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
    )
    ModelBase.metadata.create_all(engine)
    return engine


class TestBaseCollector:
    """测试 BaseCollector"""

    def test_init_with_engine(self, memory_engine):
        """测试使用外部引擎初始化"""
        collector = SimpleCollector(engine=memory_engine)
        assert collector.engine is memory_engine

    def test_close(self, memory_engine):
        """测试关闭连接"""
        collector = SimpleCollector(engine=memory_engine)
        collector.close()
        assert True

    def test_create_table(self, memory_engine):
        """测试创建表"""
        collector = SimpleCollector(engine=memory_engine)
        collector.create_table()
        assert True

    @patch('collectors.base.sessionmaker')
    def test_save_collect_log(self, mock_sessionmaker, memory_engine):
        """测试保存采集日志"""
        # 创建 mock session
        mock_session = MagicMock()
        mock_sessionmaker.return_value.return_value = mock_session

        # 模拟 log 对象有 id 属性
        mock_log = MagicMock()
        mock_log.id = 123
        mock_session.add = MagicMock()
        mock_session.commit = MagicMock()
        mock_session.close = MagicMock()

        # 使用 patch 替换 CollectLog 构造函数
        with patch('collectors.base.CollectLog', return_value=mock_log):
            collector = SimpleCollector(engine=memory_engine)
            log_id = collector._save_collect_log(
                task_name="测试任务",
                task_type="basic",
                start_time=datetime.now(),
                end_time=datetime.now(),
                success_count=10,
                failed_count=0,
                status="success"
            )
            assert log_id == 123
            mock_session.add.assert_called_once()
            mock_session.commit.assert_called_once()

    @patch('collectors.base.sessionmaker')
    def test_save_collect_log_with_error(self, mock_sessionmaker, memory_engine):
        """测试保存带错误的日志"""
        # 创建 mock session
        mock_session = MagicMock()
        mock_sessionmaker.return_value.return_value = mock_session

        # 模拟 log 对象有 id 属性
        mock_log = MagicMock()
        mock_log.id = 456
        mock_session.add = MagicMock()
        mock_session.commit = MagicMock()
        mock_session.close = MagicMock()

        # 使用 patch 替换 CollectLog 构造函数
        with patch('collectors.base.CollectLog', return_value=mock_log):
            collector = SimpleCollector(engine=memory_engine)
            log_id = collector._save_collect_log(
                task_name="失败任务",
                task_type="kline",
                start_time=datetime.now(),
                end_time=datetime.now(),
                success_count=0,
                failed_count=5,
                status="failed",
                error_msg="连接超时"
            )
            assert log_id == 456

    def test_create_log_entry(self, memory_engine):
        """测试创建日志条目"""
        collector = SimpleCollector(engine=memory_engine)
        entry = collector._create_log_entry("测试", "basic")
        assert entry["task_name"] == "测试"
        assert entry["task_type"] == "basic"
        assert entry["status"] == "running"
        assert entry["start_time"] is not None
        assert entry["end_time"] is None

    def test_finalize_log_entry(self, memory_engine):
        """测试完成日志条目"""
        collector = SimpleCollector(engine=memory_engine)
        entry = collector._create_log_entry("测试", "basic")
        result = collector._finalize_log_entry(entry, 10, 2, "success")
        assert result["success_count"] == 10
        assert result["failed_count"] == 2
        assert result["status"] == "success"
        assert result["end_time"] is not None

    def test_get_engine(self, memory_engine):
        """测试获取引擎"""
        collector = SimpleCollector(engine=memory_engine)
        assert collector.get_engine() is memory_engine

    def test_collect_abstract(self):
        """测试 collect 抽象方法"""
        collector = SimpleCollector()
        result = collector.collect()
        assert result["success"] is True

    def test_rate_limiter_initialized(self, memory_engine):
        """测试速率限制器初始化"""
        collector = SimpleCollector(engine=memory_engine)
        assert collector.rate_limiter is not None
