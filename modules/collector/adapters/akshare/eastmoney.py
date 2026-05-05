"""
东方财富数据源适配器

从 data_source.py 迁移，实现 DataProvider 接口
"""
import akshare as ak
import pandas as pd
from typing import Dict, Optional, List

from modules.collector.adapters.base import DataProvider, DataCategory, ProviderCapability
from common.utils import retry


class EastmoneyProvider(DataProvider):
    """东方财富数据源提供者

    能力:
    - STOCK_BASIC: 股票基础信息（质量评分 0.8）
    - KLINE_DAILY: 日K线数据（质量评分 0.8）
    - REALTIME_QUOTE: 实时行情（质量评分 0.9）
    - STOCK_INDUSTRY: 行业分类（质量评分 0.3，数据不可靠）
    """

    @property
    def provider_name(self) -> str:
        return "eastmoney"

    @property
    def capabilities(self) -> List[ProviderCapability]:
        return [
            ProviderCapability(
                category=DataCategory.STOCK_BASIC,
                fields=["symbol", "name", "price", "open", "high", "low",
                        "pre_close", "volume", "amount", "pct_chg", "turnover_rate"],
                quality_score=0.8,
                cost_type="free",
                latency_ms=100
            ),
            ProviderCapability(
                category=DataCategory.KLINE_DAILY,
                fields=["open", "high", "low", "close", "volume", "amount",
                        "turnover_rate", "pct_chg"],
                quality_score=0.8,
                cost_type="free",
                latency_ms=150
            ),
            ProviderCapability(
                category=DataCategory.REALTIME_QUOTE,
                fields=["symbol", "name", "price", "open", "high", "low",
                        "pre_close", "volume", "amount", "pct_chg", "bid_price",
                        "ask_price", "turnover_rate"],
                quality_score=0.9,
                cost_type="free",
                latency_ms=50
            ),
            ProviderCapability(
                category=DataCategory.STOCK_INDUSTRY,
                fields=["symbol", "industry_name"],
                quality_score=0.3,  # 行业数据不完整，评分低
                cost_type="free",
                latency_ms=200
            ),
        ]

    def fetch_stock_basic(self) -> pd.DataFrame:
        """获取股票基础信息列表

        使用 ak.stock_zh_a_spot_em() 接口
        """
        df = ak.stock_zh_a_spot_em()
        return df

    @retry(max_retries=3, base_delay=5.0, exceptions=(ConnectionError, TimeoutError))
    def fetch_kline(self, symbol: str, start_date: str, end_date: str,
                    adjust: str = "qfq") -> pd.DataFrame:
        """获取日K线数据

        Args:
            symbol: 股票代码（如 "000001"）
            start_date: 开始日期（如 "20240101"）
            end_date: 结束日期（如 "20241231"）
            adjust: 复权类型 qfq/hfq/none
        """
        df = ak.stock_zh_a_hist(
            symbol=symbol,
            period="daily",
            start_date=start_date,
            end_date=end_date,
            adjust=adjust
        )
        return df

    def fetch_realtime(self, symbol: Optional[str] = None) -> pd.DataFrame:
        """获取实时行情

        Args:
            symbol: 股票代码，None 表示全量
        """
        df = ak.stock_zh_a_spot_em()
        if symbol:
            df = df[df['代码'] == symbol]
        return df

    def fetch_industry_mapping(self) -> Dict[str, str]:
        """获取行业映射

        东方财富的行业数据不完整，返回空字典
        实际行业数据应从必盈或深交所获取
        """
        return {}