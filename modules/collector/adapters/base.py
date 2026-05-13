"""
数据源适配器抽象基类

定义数据源提供者的统一接口契约。
所有数据源适配器必须实现此基类。

设计原则：
- 零硬编码：priority/quality_score/enabled 由 providers.yaml 注入
- 标准字段：每个 DataCategory 定义标准输出字段集（CATEGORY_STANDARD_FIELDS）
- 字段映射：每个 Provider 声明 field_mapping（API原始列名 → 标准列名）
- 依赖注入：set_config() 接收运行时配置，不依赖全局变量
"""
from __future__ import annotations

import pandas as pd
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict, Any


class DataCategory(Enum):
    """数据类别枚举"""
    STOCK_BASIC = "stock_basic"
    STOCK_INDUSTRY = "stock_industry"
    STOCK_AREA = "stock_area"
    KLINE_DAILY = "kline_daily"
    REALTIME_QUOTE = "realtime_quote"
    CONCEPT = "concept"
    # QMT 数据源新增类别
    DAILY_BASIC = "daily_basic"
    FINANCIAL_INCOME = "financial_income"
    FINANCIAL_BALANCE = "financial_balance"
    FINANCIAL_CASHFLOW = "financial_cashflow"
    FINANCIAL_PER_SHARE = "financial_per_share"
    SHAREHOLDER_TOP10 = "shareholder_top10"
    SHAREHOLDER_COUNT = "shareholder_count"
    ST_STATUS = "st_status"
    IPO_INFO = "ipo_info"
    TICK_DATA = "tick_data"
    LONGHUBANG = "longhubang"
    REALTIME_DEPTH = "realtime_depth"


# 每个数据类别的标准输出字段集（唯一的字段定义来源）
CATEGORY_STANDARD_FIELDS: Dict[DataCategory, List[str]] = {
    DataCategory.STOCK_BASIC: [
        "symbol", "name", "price", "open", "high", "low",
        "pre_close", "volume", "amount", "pct_chg", "turnover_rate",
        "industry", "area", "market", "list_date", "exchange"
    ],
    DataCategory.STOCK_INDUSTRY: [
        "symbol", "industry_name"
    ],
    DataCategory.STOCK_AREA: [
        "symbol", "area_name"
    ],
    DataCategory.KLINE_DAILY: [
        "trade_date", "open", "high", "low", "close",
        "pre_close", "volume", "amount", "turnover_rate", "pct_chg",
        "ma5", "ma10", "ma20"
    ],
    DataCategory.REALTIME_QUOTE: [
        "symbol", "name", "price", "open", "high", "low",
        "pre_close", "volume", "amount", "pct_chg", "turnover_rate",
        "bid_price", "ask_price", "bid_volume", "ask_volume"
    ],
    DataCategory.CONCEPT: [
        "concept_name", "symbol"
    ],
    # QMT 数据源新增类别标准字段
    DataCategory.DAILY_BASIC: [
        "ts_code", "trade_date", "total_share", "circ_share",
        "total_mv", "circ_mv", "turnover_rate", "pe", "pb"
    ],
    DataCategory.FINANCIAL_INCOME: [
        "ts_code", "ann_date", "f_ann_date", "end_date",
        "operating_revenue", "oper_cost", "oper_profit", "net_profit", "basic_eps"
    ],
    DataCategory.FINANCIAL_BALANCE: [
        "ts_code", "ann_date", "end_date",
        "total_assets", "fix_assets", "total_liabilities", "total_equity"
    ],
    DataCategory.FINANCIAL_CASHFLOW: [
        "ts_code", "ann_date", "end_date",
        "net_cash_flows_oper_act", "net_cash_flows_inv_act", "net_cash_flows_fin_act"
    ],
    DataCategory.FINANCIAL_PER_SHARE: [
        "ts_code", "ann_date", "end_date",
        "eps", "bvps", "revenue_per_share", "oper_profit_per_share"
    ],
    DataCategory.SHAREHOLDER_TOP10: [
        "ts_code", "ann_date", "holder_name", "hold_amount",
        "hold_ratio", "holder_rank", "holder_type"
    ],
    DataCategory.SHAREHOLDER_COUNT: [
        "ts_code", "ann_date", "holder_num"
    ],
    DataCategory.ST_STATUS: [
        "ts_code", "st_type", "is_st", "start_date", "end_date"
    ],
    DataCategory.IPO_INFO: [
        "ts_code", "ipo_date", "issue_price", "issue_amount", "raise_amount"
    ],
    DataCategory.TICK_DATA: [
        "ts_code", "trade_time", "price", "volume", "amount", "trade_type"
    ],
    DataCategory.LONGHUBANG: [
        "ts_code", "trade_date", "direction", "rank",
        "sales_department", "amount", "net_amount"
    ],
    DataCategory.REALTIME_DEPTH: [
        "symbol", "bid_price1", "bid_vol1", "bid_price2", "bid_vol2",
        "bid_price3", "bid_vol3", "bid_price4", "bid_vol4", "bid_price5", "bid_vol5",
        "ask_price1", "ask_vol1", "ask_price2", "ask_vol2",
        "ask_price3", "ask_vol3", "ask_price4", "ask_vol4", "ask_price5", "ask_vol5"
    ],
}


@dataclass
class ProviderCapability:
    """数据源能力声明

    fields: 该数据源对此类别能提供的标准字段列表（必须是 CATEGORY_STANDARD_FIELDS 的子集）
    quality_score: 默认质量评分，可被 providers.yaml 覆盖
    """
    category: DataCategory
    fields: List[str] = field(default_factory=list)
    quality_score: float = 0.5
    cost_type: str = "free"
    latency_ms: int = 100

    def __post_init__(self):
        standard = set(CATEGORY_STANDARD_FIELDS.get(self.category, []))
        declared = set(self.fields)
        unknown = declared - standard
        if unknown:
            raise ValueError(
                f"[{self.category.value}] 声明了非标准字段: {unknown}。"
                f"标准字段: {sorted(standard)}"
            )

    @property
    def field_coverage(self) -> float:
        """字段覆盖率 = 能提供的字段数 / 该类别标准字段总数"""
        standard = CATEGORY_STANDARD_FIELDS.get(self.category, [])
        if not standard:
            return 0.0
        return len(self.fields) / len(standard)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "category": self.category.value,
            "fields": self.fields,
            "quality_score": self.quality_score,
            "cost_type": self.cost_type,
            "latency_ms": self.latency_ms,
        }


class DataProvider(ABC):
    """数据源提供者抽象基类

    子类必须声明：
    - provider_name: 唯一标识符
    - capabilities: 能力列表（字段声明 + 默认质量评分）
    - field_mapping: 原始API列名 → 标准列名的映射（用于数据标准化）
    """

    # ---- 子类必须定义 ----

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """数据源唯一标识符，如 'eastmoney', 'sina', mootdx"""
        ...

    @property
    @abstractmethod
    def capabilities(self) -> List[ProviderCapability]:
        """声明此数据源能提供的数据类别及对应字段"""
        ...

    @property
    def field_mapping(self) -> Dict[DataCategory, Dict[str, str]]:
        """原始列名 → 标准列名的映射

        每个 Provider 重写此属性，例如:
            {DataCategory.STOCK_BASIC: {'代码': 'symbol', '名称': 'name', '最新价': 'price'}}
        """
        return {}

    # ---- 运行时配置（由 ProviderLoader.set_config() 注入）----

    _priority: int = 99
    _enabled: bool = True
    _capability_scores: Dict[str, float] = {}  # {category_name: quality_score}

    @property
    def priority(self) -> int:
        return self._priority

    @property
    def enabled(self) -> bool:
        return self._enabled

    def set_config(self, priority: int = None, quality_score: float = None,
                   cost_type: str = None, enabled: bool = None,
                   capability_scores: Dict[str, float] = None):
        """注入运行时配置（由 ProviderLoader 调用）"""
        if priority is not None:
            self._priority = priority
        if enabled is not None:
            self._enabled = enabled
        if capability_scores is not None:
            self._capability_scores = capability_scores

    def _get_quality_score(self, category: DataCategory) -> float:
        """获取指定类别的质量评分（优先用 YAML 配置，否则用代码默认值）"""
        override = self._capability_scores.get(category.value)
        if override is not None:
            return override
        cap = self.get_capability(category)
        return cap.quality_score if cap else 0.0

    # ---- 数据获取方法（子类按需重写）----

    def fetch_stock_basic(self) -> pd.DataFrame:
        raise NotImplementedError(f"{self.provider_name} 不支持 stock_basic")

    def fetch_industry_mapping(self, symbols: Optional[List[str]] = None) -> Dict[str, str]:
        raise NotImplementedError(f"{self.provider_name} 不支持 stock_industry")

    def fetch_area_mapping(self, symbols: Optional[List[str]] = None) -> Dict[str, str]:
        raise NotImplementedError(f"{self.provider_name} 不支持 stock_area")

    def fetch_kline(self, symbol: str, start_date: str, end_date: str,
                    adjust: str = "qfq") -> pd.DataFrame:
        raise NotImplementedError(f"{self.provider_name} 不支持 kline_daily")

    def fetch_realtime(self, symbol: Optional[str] = None) -> pd.DataFrame:
        raise NotImplementedError(f"{self.provider_name} 不支持 realtime_quote")

    # ---- QMT 数据源新增方法 ----

    def fetch_daily_basic(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        raise NotImplementedError(f"{self.provider_name} 不支持 daily_basic")

    def fetch_financial_income(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        raise NotImplementedError(f"{self.provider_name} 不支持 financial_income")

    def fetch_financial_balance(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        raise NotImplementedError(f"{self.provider_name} 不支持 financial_balance")

    def fetch_financial_cashflow(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        raise NotImplementedError(f"{self.provider_name} 不支持 financial_cashflow")

    def fetch_financial_per_share(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        raise NotImplementedError(f"{self.provider_name} 不支持 financial_per_share")

    def fetch_shareholder_top10(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        raise NotImplementedError(f"{self.provider_name} 不支持 shareholder_top10")

    def fetch_shareholder_count(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        raise NotImplementedError(f"{self.provider_name} 不支持 shareholder_count")

    def fetch_st_status(self, ts_code: str) -> pd.DataFrame:
        raise NotImplementedError(f"{self.provider_name} 不支持 st_status")

    def fetch_ipo_info(self, ts_code: str) -> pd.DataFrame:
        raise NotImplementedError(f"{self.provider_name} 不支持 ipo_info")

    def fetch_tick_data(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        raise NotImplementedError(f"{self.provider_name} 不支持 tick_data")

    def fetch_longhubang(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        raise NotImplementedError(f"{self.provider_name} 不支持 longhubang")

    def fetch_realtime_depth(self, symbol: str) -> pd.DataFrame:
        raise NotImplementedError(f"{self.provider_name} 不支持 realtime_depth")

    # ---- 工具方法 ----

    def supports(self, category: DataCategory) -> bool:
        return any(c.category == category for c in self.capabilities)

    def get_capability(self, category: DataCategory) -> Optional[ProviderCapability]:
        for c in self.capabilities:
            if c.category == category:
                return c
        return None

    def get_standard_fields(self, category: DataCategory) -> List[str]:
        """获取该类别当前 Provider 能提供的标准字段列表"""
        cap = self.get_capability(category)
        return cap.fields if cap else []

    def _normalize_dataframe(self, df: pd.DataFrame, category: DataCategory) -> pd.DataFrame:
        """将原始 DataFrame 的列名转换为标准列名，并只保留标准字段子集"""
        if df is None or df.empty:
            return df

        mapping = self.field_mapping.get(category, {})
        if mapping:
            # 只 rename 实际存在的列
            existing = {k: v for k, v in mapping.items() if k in df.columns}
            df = df.rename(columns=existing)

        # 只保留该 Provider 声明的标准字段 + 基础标识字段
        declared_fields = self.get_standard_fields(category)
        keep_cols = [c for c in declared_fields if c in df.columns]
        if keep_cols:
            df = df[keep_cols]

        return df

    def health_check(self) -> bool:
        """快速健康检查"""
        try:
            if self.supports(DataCategory.STOCK_BASIC):
                df = self.fetch_stock_basic()
                return df is not None and not df.empty
            return True
        except Exception:
            return False

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典（用于 API 返回）"""
        return {
            "name": self.provider_name,
            "priority": self._priority,
            "enabled": self._enabled,
            "capabilities": [
                {
                    **c.to_dict(),
                    "quality_score": self._get_quality_score(c.category),
                }
                for c in self.capabilities
            ],
        }

    def __repr__(self):
        return f"<{self.provider_name} p={self._priority} enabled={self._enabled}>"
