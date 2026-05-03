"""
腾讯数据源适配器

从 data_source.py 迁移，实现 DataProvider 接口
"""
import akshare as ak
import pandas as pd
from typing import Dict, Optional, List

from adapters.base import DataProvider, DataCategory, ProviderCapability
from utils import logger


class TencentProvider(DataProvider):
    """腾讯数据源提供者

    能力:
    - STOCK_BASIC: 股票基础信息（质量评分 0.6，字段最少）
    - KLINE_DAILY: 日K线数据（质量评分 0.6）

    注意: 腾讯不提供实时行情、行业/地域分类数据
    """

    @property
    def provider_name(self) -> str:
        return "tencent"

    @property
    def capabilities(self) -> List[ProviderCapability]:
        return [
            ProviderCapability(
                category=DataCategory.STOCK_BASIC,
                fields=["symbol", "name", "price"],
                quality_score=0.6,
                cost_type="free",
                latency_ms=150
            ),
            ProviderCapability(
                category=DataCategory.KLINE_DAILY,
                fields=["open", "high", "low", "close", "volume"],
                quality_score=0.6,
                cost_type="free",
                latency_ms=200
            ),
        ]

    def fetch_stock_basic(self) -> pd.DataFrame:
        """获取股票基础信息列表

        腾讯没有独立的股票列表接口，使用新浪作为备用
        """
        # 腾讯无独立股票列表接口，降级到新浪
        df = ak.stock_zh_a_spot()
        return df

    def fetch_kline(self, symbol: str, start_date: str, end_date: str,
                    adjust: str = "qfq") -> pd.DataFrame:
        """获取日K线数据

        BUG-103: stock_zh_a_hist_tx 每次只返回 4 条记录，优先使用 stock_zh_a_hist（全量数据）
        """
        from services.field_merger import FieldMerger

        # 优先使用通用接口（全量数据，无条数限制）
        try:
            df = ak.stock_zh_a_hist(
                symbol=symbol,
                period="daily",
                start_date=start_date,
                end_date=end_date,
                adjust=adjust
            )
            if df is not None and not df.empty:
                return FieldMerger.normalize_columns(df)
        except Exception as e:
            logger.warning(f"{symbol} stock_zh_a_hist 失败: {e}")

        # 降级到腾讯专用接口（有记录数限制）
        try:
            if hasattr(ak, 'stock_zh_a_hist_tx'):
                df = ak.stock_zh_a_hist_tx(
                    symbol=symbol,
                    start_date=start_date,
                    end_date=end_date,
                    adjust=adjust
                )
                return FieldMerger.normalize_columns(df)
        except Exception:
            pass

        return pd.DataFrame()

    def fetch_realtime(self, symbol: Optional[str] = None) -> pd.DataFrame:
        """腾讯不提供实时行情接口"""
        raise NotImplementedError("腾讯数据源不支持实时行情")

    def fetch_industry_mapping(self) -> Dict[str, str]:
        """腾讯不提供行业数据"""
        return {}

    def fetch_area_mapping(self) -> Dict[str, str]:
        """腾讯不提供地域数据"""
        return {}