"""
数据编排器

核心调度：按质量优先级尝试各数据源，自动补齐缺失字段
"""
import pandas as pd
from typing import Dict, List, Optional, Callable, Any
from datetime import datetime

from adapters.registry import registry
from adapters.base import DataCategory, DataProvider
from services.data_validator import DataValidator
from services.field_merger import FieldMerger
from utils import logger


class DataOrchestrator:
    """数据编排器

    职责:
    - 调度多数据源采集
    - 按质量优先级尝试
    - 自动补齐缺失字段
    - 统一降级策略
    """

    def __init__(self):
        self.registry = registry
        self.validator = DataValidator()
        self.merger = FieldMerger()
        self._last_field_report: Dict[str, Any] = {}

    def get_providers(self, category: DataCategory) -> List[DataProvider]:
        """获取指定类别可用的数据源列表"""
        return self.registry.get_providers_for(category)

    def collect_stock_basic(
        self,
        progress_callback: Callable[[int, int, str], None] = None
    ) -> pd.DataFrame:
        """采集股票基础信息（含行业/地域补齐）

        Args:
            progress_callback: 进度回调函数 (current, total, stage)

        Returns:
            股票基础信息 DataFrame
        """
        logger.info("开始采集股票基础信息...")
        total_stages = 3
        current_stage = 0

        # Stage 1: 获取股票列表
        current_stage += 1
        if progress_callback:
            progress_callback(current_stage, total_stages, "获取股票列表")

        df = self._fetch_with_fallback(DataCategory.STOCK_BASIC)
        if df is None or df.empty:
            logger.error("所有数据源都无法获取股票列表")
            return pd.DataFrame()

        logger.info(f"获取到 {len(df)} 只股票")
        df = FieldMerger.normalize_columns(df)

        # Stage 2: 补齐行业字段
        current_stage += 1
        if progress_callback:
            progress_callback(current_stage, total_stages, "补齐行业字段")

        df = self._supplement_field(df, DataCategory.STOCK_INDUSTRY, "industry")

        # Stage 3: 补齐地域字段
        current_stage += 1
        if progress_callback:
            progress_callback(current_stage, total_stages, "补齐地域字段")

        df = self._supplement_field(df, DataCategory.STOCK_AREA, "area")

        # 计算字段覆盖率
        coverage = self.validator.calculate_coverage(df, ["symbol", "name", "industry", "area"])
        self._last_field_report = self.validator.get_report_dict()

        # 日志
        industry_covered = len([c for c in coverage if c.field_name == "industry" and c.coverage_rate > 0])
        area_covered = len([c for c in coverage if c.field_name == "area" and c.coverage_rate > 0])

        for c in coverage:
            logger.info(f"字段覆盖率: {c.field_name} = {c.coverage_rate:.2%} ({c.covered_count}/{c.total_count})")

        return df

    def collect_kline(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        adjust: str = "qfq",
        progress_callback: Callable[[int, int, str], None] = None
    ) -> pd.DataFrame:
        """采集单只股票的K线数据

        Args:
            symbol: 股票代码
            start_date: 开始日期
            end_date: 结束日期
            adjust: 复权类型
            progress_callback: 进度回调

        Returns:
            K线数据 DataFrame
        """
        logger.info(f"采集 {symbol} K线数据 ({start_date} ~ {end_date})...")

        providers = self.registry.get_providers_for(DataCategory.KLINE_DAILY)

        for provider in providers:
            try:
                df = provider.fetch_kline(symbol, start_date, end_date, adjust)
                if df is not None and not df.empty:
                    df = FieldMerger.normalize_columns(df)
                    # 验证必填字段
                    missing = self.validator.check_fields(df, ["open", "high", "low", "close"])
                    if not missing:
                        logger.info(f"从 {provider.provider_name} 获取 {len(df)} 条K线数据")
                        return df
                    else:
                        logger.warning(f"{provider.provider_name} K线缺少字段: {missing}")
            except Exception as e:
                logger.warning(f"{provider.provider_name} 获取K线失败: {e}")
                continue

        logger.error(f"所有数据源都无法获取 {symbol} 的K线数据")
        return pd.DataFrame()

    def collect_kline_batch(
        self,
        symbols: List[str],
        start_date: str,
        end_date: str,
        adjust: str = "qfq",
        progress_callback: Callable[[int, int, str], None] = None,
        stop_check: Callable[[], bool] = None
    ) -> Dict[str, pd.DataFrame]:
        """批量采集K线数据

        Args:
            symbols: 股票代码列表
            start_date: 开始日期
            end_date: 结束日期
            adjust: 复权类型
            progress_callback: 进度回调
            stop_check: 停止检查函数

        Returns:
            {symbol: DataFrame} 字典
        """
        results = {}
        total = len(symbols)

        for i, symbol in enumerate(symbols):
            if stop_check and stop_check():
                logger.info(f"收到停止信号，已完成 {i}/{total}")
                break

            df = self.collect_kline(symbol, start_date, end_date, adjust)
            if not df.empty:
                results[symbol] = df

            if progress_callback:
                progress_callback(i + 1, total, f"采集 {symbol}")

        return results

    def collect_realtime(
        self,
        symbol: Optional[str] = None,
        progress_callback: Callable[[int, int, str], None] = None
    ) -> pd.DataFrame:
        """采集实时行情

        Args:
            symbol: 股票代码，None 表示全量
            progress_callback: 进度回调

        Returns:
            实时行情 DataFrame
        """
        logger.info(f"采集实时行情 {'(全量)' if symbol is None else symbol}...")

        providers = self.registry.get_providers_for(DataCategory.REALTIME_QUOTE)

        for provider in providers:
            try:
                df = provider.fetch_realtime(symbol)
                if df is not None and not df.empty:
                    df = FieldMerger.normalize_columns(df)
                    logger.info(f"从 {provider.provider_name} 获取 {len(df)} 条实时行情")
                    return df
            except Exception as e:
                logger.warning(f"{provider.provider_name} 获取实时行情失败: {e}")
                continue

        logger.error("所有数据源都无法获取实时行情")
        return pd.DataFrame()

    def _fetch_with_fallback(self, category: DataCategory) -> Optional[pd.DataFrame]:
        """带降级的数据获取"""
        providers = self.registry.get_providers_for(category)

        for provider in providers:
            try:
                if category == DataCategory.STOCK_BASIC:
                    df = provider.fetch_stock_basic()
                elif category == DataCategory.KLINE_DAILY:
                    continue  # K线需要 symbol 参数，单独处理
                elif category == DataCategory.REALTIME_QUOTE:
                    df = provider.fetch_realtime()
                else:
                    continue

                if df is not None and not df.empty:
                    logger.info(f"从 {provider.provider_name} 获取数据成功")
                    return df

            except NotImplementedError:
                continue
            except Exception as e:
                logger.warning(f"{provider.provider_name} 获取数据失败: {e}")
                continue

        return None

    def _supplement_field(
        self,
        df: pd.DataFrame,
        category: DataCategory,
        field_name: str
    ) -> pd.DataFrame:
        """补充缺失字段

        Args:
            df: 主数据
            category: 数据类别
            field_name: 字段名

        Returns:
            补充后的 DataFrame
        """
        # 检查字段是否需要补充
        if field_name in df.columns:
            coverage = df[field_name].notna().sum() / len(df) if len(df) > 0 else 0
            if coverage > 0.9:  # 覆盖率超过 90%，不需要补充
                logger.info(f"{field_name} 字段覆盖率 {coverage:.2%}，无需补充")
                return df

        # 寻找能提供此字段的数据源
        providers = self.registry.get_providers_for(category)

        for provider in providers:
            try:
                if category == DataCategory.STOCK_INDUSTRY:
                    mapping = provider.fetch_industry_mapping()
                elif category == DataCategory.STOCK_AREA:
                    mapping = provider.fetch_area_mapping()
                else:
                    continue

                if mapping:
                    df = FieldMerger.apply_mapping(df, mapping, field_name)
                    coverage = df[field_name].notna().sum() / len(df) if len(df) > 0 else 0
                    logger.info(f"从 {provider.provider_name} 补充 {field_name}，覆盖率: {coverage:.2%}")

                    if coverage > 0.8:
                        break  # 覆盖率足够，停止尝试

            except NotImplementedError:
                continue
            except Exception as e:
                logger.warning(f"{provider.provider_name} 补充 {field_name} 失败: {e}")
                continue

        return df

    def get_field_report(self) -> Dict[str, Any]:
        """获取最近一次采集的字段覆盖率报告"""
        return self._last_field_report

    def get_registry(self) -> 'DataSourceRegistry':
        """获取注册中心实例"""
        return self.registry


# 全局编排器实例
orchestrator = DataOrchestrator()