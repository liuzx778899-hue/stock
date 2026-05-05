"""
采集器基类

提供公共功能：DB连接管理、建表、日志持久化、进度回调、速率限制
"""
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional, Callable, Any, Dict

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from config import config
from models import Base, CollectLog
from utils import logger, RateLimiter


class BaseCollector(ABC):
    """采集器抽象基类

    提供公共功能:
    - 数据库连接管理
    - 表创建
    - 采集日志持久化
    - 速率限制
    """

    def __init__(self, engine=None):
        """
        初始化采集器

        Args:
            engine: SQLAlchemy 引擎，如果为 None 则自动创建
        """
        if engine is None:
            self.engine = create_engine(
                config.database.connection_url,
                pool_size=config.database.pool_size,
                max_overflow=config.database.max_overflow,
                pool_timeout=config.database.pool_timeout,
                pool_pre_ping=True
            )
        else:
            self.engine = engine

        self.Session = sessionmaker(bind=self.engine)
        self.rate_limiter = RateLimiter(config.collector.request_delay)
        self._collect_start_time: Optional[datetime] = None

    def create_table(self):
        """创建数据表（调用子类实现的 get_table_model）"""
        Base.metadata.create_all(self.engine)
        logger.info("数据表创建/检查完成")

    @abstractmethod
    def collect(self, **kwargs) -> Dict[str, Any]:
        """
        执行采集（子类实现）

        Returns:
            采集结果字典，包含 success_count, failed_count 等
        """
        pass

    def _save_collect_log(
        self,
        task_name: str,
        task_type: str,
        start_time: datetime,
        end_time: datetime,
        success_count: int,
        failed_count: int,
        status: str,
        error_msg: str = None,
        extra_info: Dict = None
    ) -> Optional[int]:
        """
        保存采集日志到数据库

        Args:
            task_name: 任务名称
            task_type: 任务类型（basic/kline/realtime/incremental）
            start_time: 开始时间
            end_time: 结束时间
            success_count: 成功数量
            failed_count: 失败数量
            status: 状态（success/failed/partial/stopped）
            error_msg: 错误信息
            extra_info: 额外信息

        Returns:
            日志 ID
        """
        session = self.Session()
        try:
            log = CollectLog(
                task_name=task_name,
                task_type=task_type,
                start_time=start_time,
                end_time=end_time,
                success_count=success_count,
                failed_count=failed_count,
                status=status,
                error_msg=error_msg,
                extra_info=str(extra_info) if extra_info else None
            )
            session.add(log)
            session.commit()
            logger.info(f"采集日志已保存: {task_name} - {status}")
            return log.id
        except Exception as e:
            session.rollback()
            logger.error(f"保存采集日志失败: {e}")
            return None
        finally:
            session.close()

    def _create_log_entry(
        self,
        task_name: str,
        task_type: str
    ) -> Dict:
        """创建日志条目（用于后续填充）"""
        return {
            "task_name": task_name,
            "task_type": task_type,
            "start_time": datetime.now(),
            "end_time": None,
            "success_count": 0,
            "failed_count": 0,
            "status": "running",
            "error_msg": None
        }

    def _finalize_log_entry(
        self,
        log_entry: Dict,
        success_count: int,
        failed_count: int,
        status: str,
        error_msg: str = None
    ) -> Dict:
        """完成日志条目"""
        log_entry["end_time"] = datetime.now()
        log_entry["success_count"] = success_count
        log_entry["failed_count"] = failed_count
        log_entry["status"] = status
        log_entry["error_msg"] = error_msg
        return log_entry

    def get_engine(self):
        """获取数据库引擎"""
        return self.engine

    def close(self):
        """关闭数据库连接"""
        if self.engine:
            self.engine.dispose()