"""
字段合并器

将多个数据源的数据按股票代码合并，补齐缺失字段
"""
import pandas as pd
from typing import Dict, List, Optional, Any
from utils import logger


class FieldMerger:
    """字段合并器

    职责:
    - 按股票代码合并多个数据源的数据
    - 补齐缺失字段
    - 处理字段冲突（优先使用高质量数据）
    """

    # 标准字段名映射（不同数据源可能使用不同的列名）
    FIELD_ALIASES = {
        "symbol": ["代码", "code", "dm", "股票代码", "symbol", "股票代码", "代码"],
        "name": ["名称", "name", "mc", "股票名称", "名称"],
        "price": ["现价", "price", "最新价"],
        "open": ["开盘", "open", "开盘价", "Open", "open"],
        "high": ["最高", "high", "最高价", "High", "high"],
        "low": ["最低", "low", "最低价", "Low", "low"],
        "close": ["收盘", "close", "收盘价", "最新价", "Close", "close"],
        "volume": ["成交量", "volume", "vol", "成交股数", "Volume", "volume", "成交量"],
        "amount": ["成交额", "amount", "成交金额", "Amount", "amount"],
        "pct_chg": ["涨跌幅", "pct_chg", "涨跌%", "change_pct", "涨跌幅%", "涨跌幅"],
        "turnover_rate": ["换手率", "turnover_rate", "换手"],
        "industry": ["行业", "industry", "所属行业"],
        "area": ["地区", "area", "地域", "所属地区"],
        "pre_close": ["昨收", "pre_close", "昨收盘"],
        "trade_date": ["日期", "date", "trade_date", "Date", "日期"],
    }

    @staticmethod
    def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
        """标准化列名

        将各种中文/英文列名统一为英文标准名
        """
        if df is None or df.empty:
            return df

        df = df.copy()
        rename_map = {}

        for standard_name, aliases in FieldMerger.FIELD_ALIASES.items():
            for alias in aliases:
                if alias in df.columns and standard_name not in df.columns:
                    rename_map[alias] = standard_name
                    break

        if rename_map:
            df = df.rename(columns=rename_map)

        return df

    @staticmethod
    def get_symbol_column(df: pd.DataFrame) -> Optional[str]:
        """找出 DataFrame 中的股票代码列"""
        for col in ["symbol", "代码", "code", "dm", "股票代码"]:
            if col in df.columns:
                return col
        return None

    @staticmethod
    def merge_by_symbol(
        main_df: pd.DataFrame,
        supplement_df: pd.DataFrame,
        fields: List[str] = None,
        overwrite: bool = False
    ) -> pd.DataFrame:
        """按股票代码合并两个 DataFrame

        Args:
            main_df: 主数据（包含完整股票列表）
            supplement_df: 补充数据（包含额外字段）
            fields: 要补充的字段列表，None 表示补充所有缺失字段
            overwrite: 是否覆盖主数据中已有的非空值

        Returns:
            合并后的 DataFrame
        """
        if main_df is None or main_df.empty:
            return supplement_df

        if supplement_df is None or supplement_df.empty:
            return main_df

        # 标准化列名
        main_df = FieldMerger.normalize_columns(main_df)
        supplement_df = FieldMerger.normalize_columns(supplement_df)

        # 找出股票代码列
        main_symbol_col = FieldMerger.get_symbol_column(main_df)
        supp_symbol_col = FieldMerger.get_symbol_column(supplement_df)

        if main_symbol_col is None or supp_symbol_col is None:
            logger.warning("无法找到股票代码列，跳过合并")
            return main_df

        # 统一代码格式（去除后缀）
        main_df["_symbol_key"] = main_df[main_symbol_col].astype(str).str.replace(r"\.\w+$", "", regex=True)
        supplement_df["_symbol_key"] = supplement_df[supp_symbol_col].astype(str).str.replace(r"\.\w+$", "", regex=True)

        # 确定要补充的字段
        if fields is None:
            # 补充主数据中缺失的列
            fields = [c for c in supplement_df.columns
                      if c not in main_df.columns and c != "_symbol_key" and c != supp_symbol_col]

        # 创建补充数据的字典映射
        for field in fields:
            if field not in supplement_df.columns:
                continue

            # 创建映射字典
            field_map = dict(zip(supplement_df["_symbol_key"], supplement_df[field]))

            # 只填充空值，不覆盖已有值（除非 overwrite=True）
            if field in main_df.columns:
                if overwrite:
                    main_df[field] = main_df["_symbol_key"].map(field_map)
                else:
                    # 只填充空值
                    mask = main_df[field].isna()
                    main_df.loc[mask, field] = main_df.loc[mask, "_symbol_key"].map(field_map)
            else:
                # 新增列
                main_df[field] = main_df["_symbol_key"].map(field_map)

        # 清理临时列
        main_df = main_df.drop(columns=["_symbol_key"], errors="ignore")

        return main_df

    @staticmethod
    def apply_mapping(
        df: pd.DataFrame,
        mapping: Dict[str, str],
        field_name: str,
        symbol_col: str = "symbol"
    ) -> pd.DataFrame:
        """应用字段映射（如行业/地域映射）

        Args:
            df: 目标 DataFrame
            mapping: 映射字典 {symbol: value}
            field_name: 目标字段名
            symbol_col: 股票代码列名

        Returns:
            更新后的 DataFrame
        """
        if df is None or df.empty or not mapping:
            return df

        df = df.copy()

        # 找出股票代码列
        if symbol_col not in df.columns:
            symbol_col = FieldMerger.get_symbol_column(df)

        if symbol_col is None:
            logger.warning("无法找到股票代码列，跳过映射")
            return df

        # 统一代码格式
        df["_symbol_key"] = df[symbol_col].astype(str).str.replace(r"\.\w+$", "", regex=True)

        # 应用映射
        if field_name in df.columns:
            # 只更新空值
            mask = df[field_name].isna()
            df.loc[mask, field_name] = df.loc[mask, "_symbol_key"].map(mapping)
        else:
            # 新增字段
            df[field_name] = df["_symbol_key"].map(mapping)

        # 清理临时列
        df = df.drop(columns=["_symbol_key"], errors="ignore")

        return df