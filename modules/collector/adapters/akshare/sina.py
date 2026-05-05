"""
新浪数据源适配器

从 data_source.py 迁移，实现 DataProvider 接口
"""
import akshare as ak
import pandas as pd
from typing import Dict, Optional, List

from modules.collector.adapters.base import DataProvider, DataCategory, ProviderCapability
from common.utils import retry


class SinaProvider(DataProvider):
    """新浪数据源提供者

    能力:
    - STOCK_BASIC: 股票基础信息（质量评分 0.7，字段较少）
    - KLINE_DAILY: 日K线数据（质量评分 0.7）
    - REALTIME_QUOTE: 实时行情（质量评分 0.7）

    注意: 新浪不提供行业/地域分类数据
    """

    @property
    def provider_name(self) -> str:
        return "sina"

    @property
    def capabilities(self) -> List[ProviderCapability]:
        return [
            ProviderCapability(
                category=DataCategory.STOCK_BASIC,
                fields=["symbol", "name", "price", "volume", "amount"],
                quality_score=0.7,
                cost_type="free",
                latency_ms=120
            ),
            ProviderCapability(
                category=DataCategory.KLINE_DAILY,
                fields=["open", "high", "low", "close", "volume"],
                quality_score=0.7,
                cost_type="free",
                latency_ms=180
            ),
            ProviderCapability(
                category=DataCategory.REALTIME_QUOTE,
                fields=["symbol", "name", "price", "open", "high", "low",
                        "volume", "amount"],
                quality_score=0.7,
                cost_type="free",
                latency_ms=80
            ),
        ]

    def fetch_stock_basic(self) -> pd.DataFrame:
        """获取股票基础信息列表

        使用 ak.stock_zh_a_spot() 接口
        """
        df = ak.stock_zh_a_spot()
        return df

    @retry(max_retries=3, base_delay=5.0, exceptions=(ConnectionError, TimeoutError))
    def fetch_kline(self, symbol: str, start_date: str, end_date: str,
                    adjust: str = "qfq") -> pd.DataFrame:
        """获取日K线数据

        优先使用 stock_zh_a_daily，不存在则降级到 stock_zh_a_hist
        """
        from modules.collector.services.field_merger import FieldMerger

        try:
            if hasattr(ak, 'stock_zh_a_daily'):
                df = ak.stock_zh_a_daily(
                    symbol=symbol,
                    start_date=start_date,
                    end_date=end_date,
                    adjust=adjust
                )
                return FieldMerger.normalize_columns(df)
        except Exception:
            pass

        # 降级到通用接口
        df = ak.stock_zh_a_hist(
            symbol=symbol,
            period="daily",
            start_date=start_date,
            end_date=end_date,
            adjust=adjust
        )
        return FieldMerger.normalize_columns(df)

    def fetch_realtime(self, symbol: Optional[str] = None) -> pd.DataFrame:
        """获取实时行情"""
        df = ak.stock_zh_a_spot()
        if symbol:
            df = df[df['代码'] == symbol]
        return df

    def fetch_industry_mapping(self) -> Dict[str, str]:
        """新浪不提供行业数据"""
        return {}

    def fetch_area_mapping(self) -> Dict[str, str]:
        """新浪不提供地域数据"""
        return {}