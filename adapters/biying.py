"""
必盈 API 数据源适配器

从 biying_adapter.py 迁移，实现 DataProvider 接口
文档: https://www.biyingapi.com/doc_hs
"""
import pandas as pd
from typing import Dict, Optional, List, Any
import time

from adapters.base import DataProvider, DataCategory, ProviderCapability
from utils import logger

# 延迟导入避免循环依赖
_biying_adapter = None


def _get_biying_adapter():
    """获取必盈适配器实例（延迟导入）"""
    global _biying_adapter
    if _biying_adapter is None:
        from biying_adapter import get_biying_adapter, init_biying_adapter
        _biying_adapter = get_biying_adapter()
        if _biying_adapter is None:
            _biying_adapter = init_biying_adapter()
    return _biying_adapter


class BiyingProvider(DataProvider):
    """必盈数据源提供者

    能力:
    - STOCK_BASIC: 股票基础信息（质量评分 0.85）
    - STOCK_INDUSTRY: 行业分类（质量评分 0.9，核心能力）
    - STOCK_AREA: 地域分类（质量评分 0.9，核心能力）
    - KLINE_DAILY: 日K线数据（质量评分 0.9）
    - REALTIME_QUOTE: 实时行情（质量评分 0.85，付费服务）

    注意: 必盈是付费 API，需要有效的 Licence
    """

    @property
    def provider_name(self) -> str:
        return "biying"

    @property
    def capabilities(self) -> List[ProviderCapability]:
        return [
            ProviderCapability(
                category=DataCategory.STOCK_BASIC,
                fields=["symbol", "name", "exchange"],
                quality_score=0.85,
                cost_type="paid",
                latency_ms=200
            ),
            ProviderCapability(
                category=DataCategory.STOCK_INDUSTRY,
                fields=["symbol", "industry_name"],
                quality_score=0.9,  # 核心能力
                cost_type="paid",
                latency_ms=100
            ),
            ProviderCapability(
                category=DataCategory.STOCK_AREA,
                fields=["symbol", "area_name"],
                quality_score=0.9,  # 核心能力
                cost_type="paid",
                latency_ms=100
            ),
            ProviderCapability(
                category=DataCategory.KLINE_DAILY,
                fields=["open", "high", "low", "close", "volume", "amount",
                        "pct_chg", "turnover_rate"],
                quality_score=0.9,
                cost_type="paid",
                latency_ms=150
            ),
            ProviderCapability(
                category=DataCategory.REALTIME_QUOTE,
                fields=["symbol", "name", "price", "open", "high", "low",
                        "pre_close", "volume", "amount", "pct_chg", "turnover_rate"],
                quality_score=0.85,
                cost_type="paid",
                latency_ms=80
            ),
        ]

    def _get_adapter(self):
        """获取适配器实例"""
        return _get_biying_adapter()

    def fetch_stock_basic(self) -> pd.DataFrame:
        """获取股票基础信息列表

        使用 hslt/list 接口
        """
        adapter = self._get_adapter()
        if adapter is None:
            logger.warning("必盈 API 适配器未初始化")
            return pd.DataFrame()

        try:
            df = adapter.get_stock_list()
            return df
        except Exception as e:
            logger.error(f"必盈 API 获取股票列表失败: {e}")
            return pd.DataFrame()

    def fetch_industry_mapping(self) -> Dict[str, str]:
        """获取行业映射

        通过逐个获取公司简介提取行业信息
        """
        adapter = self._get_adapter()
        if adapter is None:
            return {}

        try:
            industry_map, _ = adapter.get_industry_area_mapping()
            return industry_map
        except Exception as e:
            logger.error(f"必盈 API 获取行业映射失败: {e}")
            return {}

    def fetch_area_mapping(self) -> Dict[str, str]:
        """获取地域映射

        通过逐个获取公司简介提取地区信息
        """
        adapter = self._get_adapter()
        if adapter is None:
            return {}

        try:
            _, area_map = adapter.get_industry_area_mapping()
            return area_map
        except Exception as e:
            logger.error(f"必盈 API 获取地域映射失败: {e}")
            return {}

    def fetch_kline(self, symbol: str, start_date: str, end_date: str,
                    adjust: str = "qfq") -> pd.DataFrame:
        """获取日K线数据

        Args:
            symbol: 股票代码
            start_date: 开始日期（如 "20240101"）
            end_date: 结束日期（如 "20241231"）
            adjust: 复权类型 qfq/hfq/n
        """
        adapter = self._get_adapter()
        if adapter is None:
            return pd.DataFrame()

        try:
            # 必盈的 adjust 参数: n=不复权, qfq=前复权, hfq=后复权
            biying_adjust = adjust if adjust in ['qfq', 'hfq', 'n'] else 'n'
            df = adapter.get_history_kline(symbol, start_date, end_date,
                                            period='d', adjust=biying_adjust)
            return df
        except Exception as e:
            logger.error(f"必盈 API 获取K线失败: {e}")
            return pd.DataFrame()

    def fetch_realtime(self, symbol: Optional[str] = None) -> pd.DataFrame:
        """获取实时行情

        Args:
            symbol: 股票代码，None 表示全量（全量较慢）
        """
        adapter = self._get_adapter()
        if adapter is None:
            return pd.DataFrame()

        try:
            if symbol:
                data = adapter.get_stock_realtime(symbol)
                if data:
                    return pd.DataFrame([data])
                return pd.DataFrame()
            else:
                # 全量获取：先获取列表，再逐个获取行情
                df_list = adapter.get_stock_list()
                if df_list.empty:
                    return pd.DataFrame()

                results = []
                for _, row in df_list.iterrows():
                    code = row['代码']
                    rt = adapter.get_stock_realtime(code)
                    if rt:
                        results.append(rt)
                    time.sleep(0.02)  # 避免请求过快

                if results:
                    return pd.DataFrame(results)
                return pd.DataFrame()
        except Exception as e:
            logger.error(f"必盈 API 获取实时行情失败: {e}")
            return pd.DataFrame()

    def health_check(self) -> bool:
        """检查必盈 API 是否可用"""
        adapter = self._get_adapter()
        if adapter is None:
            return False

        try:
            status = adapter.get_licence_status()
            return len(status) > 0
        except Exception:
            return False

    def get_licence_status(self) -> List[Dict]:
        """获取 Licence 池状态"""
        adapter = self._get_adapter()
        if adapter is None:
            return []
        return adapter.get_licence_status()
