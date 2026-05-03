"""
工具函数 - 日志、重试机制等
"""
import logging
import os
import time
import functools
from typing import Callable, Optional
from datetime import datetime

from config import config


class TaskStoppedException(Exception):
    """任务被用户停止的自定义异常"""
    pass

# 日志格式
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


def setup_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """创建并返回一个配置好的 logger"""
    logger = logging.getLogger(name)
    logger.setLevel(level)

    if not logger.handlers:
        # 控制台处理器
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_handler.setFormatter(logging.Formatter(LOG_FORMAT))
        logger.addHandler(console_handler)

        # 确保日志目录存在
        os.makedirs("logs", exist_ok=True)

        # 文件处理器
        file_handler = logging.FileHandler(
            f"logs/{name}_{datetime.now().strftime('%Y%m%d')}.log",
            encoding='utf-8'
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(logging.Formatter(LOG_FORMAT))
        logger.addHandler(file_handler)

    return logger


# 全局 logger
logger = setup_logger("stock_collector")


def retry(
    max_retries: Optional[int] = None,
    base_delay: Optional[float] = None,
    max_delay: Optional[float] = None,
    exceptions: tuple = (Exception,),
    on_retry: Optional[Callable] = None
):
    """
    重试装饰器 - 指数退避策略

    Args:
        max_retries: 最大重试次数
        base_delay: 基础延迟时间（秒）
        max_delay: 最大延迟时间（秒）
        exceptions: 需要重试的异常类型
        on_retry: 重试时的回调函数
    """
    retry_config = config.retry
    _max_retries = max_retries or retry_config.max_retries
    _base_delay = base_delay or retry_config.base_delay
    _max_delay = max_delay or retry_config.max_delay

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(_max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < _max_retries:
                        # 计算指数退避延迟
                        delay = min(
                            _base_delay * (retry_config.exponential_base ** attempt),
                            _max_delay
                        )
                        logger.warning(
                            f"第 {attempt + 1} 次重试 {func.__name__}，"
                            f"错误: {str(e)}，{delay:.2f} 秒后重试"
                        )
                        if on_retry:
                            on_retry(attempt, e)
                        time.sleep(delay)
                    else:
                        logger.error(
                            f"{func.__name__} 重试 {_max_retries} 次后仍然失败: {str(e)}"
                        )
            raise last_exception
        return wrapper
    return decorator


class RateLimiter:
    """速率限制器"""

    def __init__(self, delay: float = 0.1):
        self.delay = delay
        self.last_call_time = 0.0

    def wait(self):
        """等待直到可以进行下一次调用"""
        current_time = time.time()
        elapsed = current_time - self.last_call_time
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self.last_call_time = time.time()


def chunk_list(lst: list, chunk_size: int) -> list:
    """将列表分割成指定大小的块"""
    return [lst[i:i + chunk_size] for i in range(0, len(lst), chunk_size)]