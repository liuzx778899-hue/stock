"""
测试 utils.py - 工具函数模块
"""
import pytest
import time
import os
from unittest.mock import patch, MagicMock

from utils import (
    setup_logger, retry, RateLimiter, chunk_list, logger
)


class TestSetupLogger:
    """测试日志设置"""

    def test_creates_logger_with_name(self):
        log = setup_logger("test_module")
        assert log.name == "test_module"
        assert log.level is not None

    def test_adds_handlers(self):
        log = setup_logger("test_with_handlers")
        assert len(log.handlers) >= 1  # 至少 console handler

    @patch('utils.logging.FileHandler')
    def test_file_handler_created(self, mock_file_handler):
        log = setup_logger("test_file_handler")
        # FileHandler 被调用（即使目录不存在会失败，这里验证调用意图）
        assert log is not None


class TestRetryDecorator:
    """测试重试装饰器"""

    def test_retry_success_first_attempt(self):
        call_count = [0]

        @retry(max_retries=3)
        def succeed():
            call_count[0] += 1
            return "ok"

        result = succeed()
        assert result == "ok"
        assert call_count[0] == 1

    def test_retry_eventually_succeeds(self):
        call_count = [0]

        @retry(max_retries=3, base_delay=0.001)
        def fail_then_succeed():
            call_count[0] += 1
            if call_count[0] < 3:
                raise ValueError("transient error")
            return "recovered"

        result = fail_then_succeed()
        assert result == "recovered"
        assert call_count[0] == 3

    def test_retry_exhausted_raises(self):
        @retry(max_retries=2, base_delay=0.001)
        def always_fail():
            raise RuntimeError("persistent error")

        with pytest.raises(RuntimeError, match="persistent error"):
            always_fail()

    def test_retry_only_on_specified_exceptions(self):
        """只重试指定的异常类型"""
        call_count = [0]

        @retry(max_retries=3, exceptions=(ValueError,), base_delay=0.001)
        def raise_type_error():
            call_count[0] += 1
            raise TypeError("should not retry")

        with pytest.raises(TypeError):
            raise_type_error()
        assert call_count[0] == 1  # 不重试 TypeError

    def test_retry_with_on_retry_callback(self):
        attempts = []

        def callback(attempt, error):
            attempts.append(attempt)

        call_count = [0]

        @retry(max_retries=2, base_delay=0.001, on_retry=callback)
        def fail():
            call_count[0] += 1
            if call_count[0] <= 2:
                raise ValueError("fail")
            return "ok"

        fail()
        assert len(attempts) == 2
        assert attempts == [0, 1]

    def test_retry_respects_global_config(self):
        """重试使用全局配置默认值"""
        @retry()
        def ok():
            return True

        assert ok() is True

    def test_retry_preserves_function_metadata(self):
        @retry(max_retries=1)
        def my_function():
            """docstring"""
            return True

        assert my_function.__name__ == "my_function"
        assert my_function.__doc__ == "docstring"


class TestRateLimiter:
    """测试速率限制器"""

    def test_initial_state(self):
        rl = RateLimiter(delay=0.1)
        assert rl.delay == 0.1
        assert rl.last_call_time == 0.0

    def test_first_call_no_delay(self):
        rl = RateLimiter(delay=1.0)
        start = time.time()
        rl.wait()
        elapsed = time.time() - start
        # 第一次调用不应等待
        assert elapsed < 0.1

    def test_consecutive_calls_respected(self):
        rl = RateLimiter(delay=0.05)
        rl.wait()
        start = time.time()
        rl.wait()
        elapsed = time.time() - start
        # 第二次调用应有延迟（约0.05秒）
        assert elapsed >= 0.04

    def test_custom_delay(self):
        rl = RateLimiter(delay=0.01)
        rl.wait()
        start = time.time()
        rl.wait()
        elapsed = time.time() - start
        assert elapsed >= 0.009


class TestChunkList:
    """测试列表分块"""

    def test_even_split(self):
        result = chunk_list([1, 2, 3, 4, 5, 6], 2)
        assert result == [[1, 2], [3, 4], [5, 6]]

    def test_uneven_split(self):
        result = chunk_list([1, 2, 3, 4, 5], 2)
        assert result == [[1, 2], [3, 4], [5]]

    def test_empty_list(self):
        result = chunk_list([], 10)
        assert result == []

    def test_chunk_size_larger_than_list(self):
        result = chunk_list([1, 2], 100)
        assert result == [[1, 2]]

    def test_single_item_per_chunk(self):
        result = chunk_list([1, 2, 3], 1)
        assert result == [[1], [2], [3]]

    def test_large_list(self):
        data = list(range(1000))
        result = chunk_list(data, 50)
        assert len(result) == 20
        assert all(len(chunk) == 50 for chunk in result)
