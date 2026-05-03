"""
数据源适配器 - 多数据源支持和自动降级
支持 AkShare 多数据源（东方财富、新浪、腾讯等）
自动在数据源失败时切换到备用数据源
"""
import akshare as ak
import pandas as pd
from typing import Optional, Callable, List
from functools import wraps

from config import config, DataSourceConfig
from utils import logger, retry, RateLimiter


class DataSourceAdapter:
    """数据源适配器 - 统一的数据获取接口"""

    def __init__(self):
        self.rate_limiter = RateLimiter(config.collector.request_delay)
        self.data_sources = config.get_enabled_data_sources()
        self.current_source_index = 0

    def get_current_source(self) -> DataSourceConfig:
        """获取当前数据源"""
        if self.current_source_index < len(self.data_sources):
            return self.data_sources[self.current_source_index]
        return None

    def switch_to_next_source(self) -> bool:
        """
        切换到下一个数据源

        Returns:
            是否成功切换
        """
        if self.current_source_index < len(self.data_sources) - 1:
            self.current_source_index += 1
            source = self.get_current_source()
            logger.warning(f"切换到备用数据源: {source.name}")
            return True
        logger.error("所有数据源都已失败，无法继续切换")
        return False

    def reset_source(self):
        """重置到主数据源"""
        self.current_source_index = 0
        logger.info("重置到主数据源")

    def with_fallback(self, func: Callable) -> Callable:
        """
        自动降级装饰器 - 当数据源失败时自动切换到备用数据源

        Args:
            func: 数据获取函数

        Returns:
            包装后的函数
        """
        @wraps(func)
        def wrapper(*args, **kwargs):
            max_attempts = len(self.data_sources)
            last_error = None

            for attempt in range(max_attempts):
                source = self.get_current_source()
                if source is None:
                    break

                try:
                    self.rate_limiter.wait()
                    kwargs['source_config'] = source
                    result = func(*args, **kwargs)
                    return result

                except Exception as e:
                    last_error = e
                    logger.warning(
                        f"数据源 {source.name} 失败: {e}，尝试切换备用数据源"
                    )
                    if not self.switch_to_next_source():
                        break

            # 所有数据源都失败后，重置并抛出异常
            self.reset_source()
            raise last_error or Exception("所有数据源都不可用")

        return wrapper


class AkShareAdapter(DataSourceAdapter):
    """AkShare 数据源适配器"""

    # 数据源健康缓存 {source_name: consecutive_failures}
    _source_health: dict = {}
    # 最大连续失败次数，超过后临时标记为不可用
    MAX_CONSECUTIVE_FAILURES: int = 10

    # ===============================
    # 股票基础信息接口
    # ===============================

    def fetch_stock_list_em(self) -> pd.DataFrame:
        """东方财富 - 获取A股股票列表"""
        logger.info("使用东方财富数据源获取股票列表...")
        df = ak.stock_zh_a_spot_em()
        return df

    def fetch_stock_list_sina(self) -> pd.DataFrame:
        """新浪 - 获取A股股票列表"""
        logger.info("使用新浪数据源获取股票列表...")
        df = ak.stock_zh_a_spot()
        return df

    def fetch_stock_basic(self, source_config: DataSourceConfig = None) -> pd.DataFrame:
        """
        获取股票基础信息（多数据源）

        Args:
            source_config: 数据源配置

        Returns:
            股票列表 DataFrame
        """
        source_name = source_config.name if source_config else "akshare_em"

        try:
            if "em" in source_name:
                return self.fetch_stock_list_em()
            elif "sina" in source_name:
                return self.fetch_stock_list_sina()
            else:
                # 默认使用东方财富
                return self.fetch_stock_list_em()

        except Exception as e:
            logger.error(f"数据源 {source_name} 获取股票列表失败: {e}")
            raise

    # ===============================
    # 历史K线数据接口
    # ===============================

    def fetch_kline_em(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        adjust: str = "qfq"
    ) -> Optional[pd.DataFrame]:
        """
        东方财富 - 获取历史K线数据

        Args:
            symbol: 股票代码
            start_date: 开始日期
            end_date: 结束日期
            adjust: 复权类型

        Returns:
            K线数据 DataFrame
        """
        logger.debug(f"东方财富获取 {symbol} K线数据...")
        df = ak.stock_zh_a_hist(
            symbol=symbol,
            period="daily",
            start_date=start_date,
            end_date=end_date,
            adjust=adjust
        )
        return df

    def fetch_kline_sina(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        adjust: str = "qfq"
    ) -> Optional[pd.DataFrame]:
        """
        新浪 - 获取历史K线数据（备用接口）
        如果 stock_zh_a_daily 不存在，自动降级到 stock_zh_a_hist
        """
        logger.debug(f"新浪获取 {symbol} K线数据...")
        try:
            # 优先使用新浪专用接口
            if hasattr(ak, 'stock_zh_a_daily'):
                df = ak.stock_zh_a_daily(
                    symbol=symbol,
                    start_date=start_date,
                    end_date=end_date,
                    adjust=adjust
                )
                return df

            # 新浪接口不存在，降级到 stock_zh_a_hist（通用接口）
            logger.debug(f"stock_zh_a_daily 不存在，使用 stock_zh_a_hist 作为新浪数据源")
            df = ak.stock_zh_a_hist(
                symbol=symbol,
                period="daily",
                start_date=start_date,
                end_date=end_date,
                adjust=adjust
            )
            return df
        except Exception as e:
            logger.warning(f"新浪K线接口失败: {e}")
            return None

    def fetch_kline_tencent(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        adjust: str = "qfq"
    ) -> Optional[pd.DataFrame]:
        """
        腾讯 - 获取历史K线数据
        如果 stock_zh_a_hist_tx 不存在，自动降级到 stock_zh_a_hist
        """
        logger.debug(f"腾讯获取 {symbol} K线数据...")
        try:
            # 优先使用腾讯专用接口
            if hasattr(ak, 'stock_zh_a_hist_tx'):
                df = ak.stock_zh_a_hist_tx(
                    symbol=symbol,
                    start_date=start_date,
                    end_date=end_date,
                    adjust=adjust
                )
                return df

            # 腾讯接口不存在，降级到 stock_zh_a_hist（通用接口）
            logger.debug(f"stock_zh_a_hist_tx 不存在，使用 stock_zh_a_hist 作为腾讯数据源")
            df = ak.stock_zh_a_hist(
                symbol=symbol,
                period="daily",
                start_date=start_date,
                end_date=end_date,
                adjust=adjust
            )
            return df
        except Exception as e:
            logger.warning(f"腾讯K线接口失败: {e}")
            return None

    def fetch_kline_with_fallback(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        adjust: str = "qfq"
    ) -> Optional[pd.DataFrame]:
        """
        获取K线数据，自动降级（多数据源尝试）
        包含数据源健康缓存：连续失败超过阈值后临时跳过

        Args:
            symbol: 股票代码
            start_date: 开始日期
            end_date: 结束日期
            adjust: 复权类型

        Returns:
            K线数据 DataFrame
        """
        # 按优先级尝试各数据源
        for source in self.data_sources:
            # 检查数据源健康状态
            source_name = source.name
            fail_count = self._source_health.get(source_name, 0)
            if fail_count >= self.MAX_CONSECUTIVE_FAILURES:
                logger.warning(f"数据源 {source_name} 连续失败 {fail_count} 次，临时跳过")
                continue

            try:
                self.rate_limiter.wait()

                if "em" in source.name:
                    df = self.fetch_kline_em(symbol, start_date, end_date, adjust)
                elif "sina" in source.name:
                    df = self.fetch_kline_sina(symbol, start_date, end_date, adjust)
                elif "tencent" in source.name:
                    df = self.fetch_kline_tencent(symbol, start_date, end_date, adjust)
                else:
                    df = self.fetch_kline_em(symbol, start_date, end_date, adjust)

                if df is not None and not df.empty:
                    # 成功：重置该数据源的失败计数
                    self._source_health[source_name] = 0
                    return df

                # 返回空数据也算一次失败
                self._source_health[source_name] = fail_count + 1

            except Exception as e:
                # 记录连续失败次数
                self._source_health[source_name] = fail_count + 1
                logger.warning(f"数据源 {source.name} 获取 {symbol} K线失败 ({self._source_health[source_name]}/{self.MAX_CONSECUTIVE_FAILURES}): {e}")
                continue

        logger.error(f"所有数据源都无法获取 {symbol} 的K线数据")
        return None

    # ===============================
    # 实时行情接口
    # ===============================

    def fetch_realtime_em(self) -> pd.DataFrame:
        """东方财富 - 获取实时行情"""
        logger.info("东方财富获取实时行情...")
        df = ak.stock_zh_a_spot_em()
        return df

    def fetch_realtime_sina(self) -> pd.DataFrame:
        """新浪 - 获取实时行情"""
        logger.info("新浪获取实时行情...")
        df = ak.stock_zh_a_spot()
        return df

    def fetch_realtime_with_fallback(self) -> pd.DataFrame:
        """
        获取实时行情，自动降级

        Returns:
            实时行情 DataFrame
        """
        for source in self.data_sources:
            try:
                self.rate_limiter.wait()

                if "em" in source.name:
                    df = self.fetch_realtime_em()
                elif "sina" in source.name:
                    df = self.fetch_realtime_sina()
                else:
                    df = self.fetch_realtime_em()

                if df is not None and not df.empty:
                    return df

            except Exception as e:
                logger.warning(f"数据源 {source.name} 获取实时行情失败: {e}")
                continue

        raise Exception("所有数据源都无法获取实时行情数据")


# 全局数据源适配器实例
data_source_adapter = AkShareAdapter()


if __name__ == "__main__":
    # 测试数据源适配器
    adapter = AkShareAdapter()

    # 测试股票列表获取
    print("测试获取股票列表...")
    df = adapter.fetch_stock_basic(adapter.get_current_source())
    print(f"获取到 {len(df)} 条股票信息")

    # 测试K线数据获取
    print("\n测试获取K线数据...")
    df_kline = adapter.fetch_kline_with_fallback(
        symbol="000001",
        start_date="20240101",
        end_date="20240131"
    )
    if df_kline:
        print(f"获取到 {len(df_kline)} 条K线数据")
    else:
        print("K线数据获取失败")