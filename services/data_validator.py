"""
数据验证器

检查数据质量，计算字段覆盖率
"""
import pandas as pd
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

from utils import logger


@dataclass
class FieldCoverage:
    """字段覆盖率报告"""
    field_name: str
    total_count: int
    covered_count: int
    coverage_rate: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "field": self.field_name,
            "total": self.total_count,
            "covered": self.covered_count,
            "rate": round(self.coverage_rate, 4)
        }


class DataValidator:
    """数据验证器

    职责:
    - 检查必填字段是否存在
    - 计算字段覆盖率
    - 识别缺失字段
    - 生成数据质量报告
    """

    # 各数据类别的必填字段定义
    REQUIRED_FIELDS = {
        "stock_basic": ["symbol", "name"],
        "kline_daily": ["open", "high", "low", "close", "volume"],
        "realtime_quote": ["symbol", "price"],
    }

    # 建议字段（缺失则尝试补齐）
    RECOMMENDED_FIELDS = {
        "stock_basic": ["industry", "area", "pct_chg", "turnover_rate"],
        "kline_daily": ["pct_chg", "turnover_rate", "pre_close"],
        "realtime_quote": ["pct_chg", "turnover_rate", "pre_close"],
    }

    def __init__(self):
        self._last_report: List[FieldCoverage] = []

    def validate(self, df: pd.DataFrame, category: str) -> bool:
        """验证数据是否满足最低要求

        Args:
            df: 数据 DataFrame
            category: 数据类别

        Returns:
            是否通过验证
        """
        if df is None or df.empty:
            logger.warning(f"{category}: 数据为空，验证失败")
            return False

        required = self.REQUIRED_FIELDS.get(category, [])
        missing = [f for f in required if f not in df.columns]

        if missing:
            logger.error(f"{category}: 缺少必填字段 {missing}")
            return False

        return True

    def check_fields(self, df: pd.DataFrame, fields: List[str]) -> List[str]:
        """检查指定字段是否存在，返回缺失字段列表"""
        if df is None or df.empty:
            return fields

        missing = []
        for f in fields:
            if f not in df.columns:
                missing.append(f)
            elif df[f].isna().all():
                missing.append(f)

        return missing

    def calculate_coverage(self, df: pd.DataFrame, fields: List[str] = None) -> List[FieldCoverage]:
        """计算字段覆盖率

        Args:
            df: 数据 DataFrame
            fields: 要检查的字段列表，None 表示所有列

        Returns:
            字段覆盖率报告列表
        """
        if df is None or df.empty:
            return []

        check_fields = fields or list(df.columns)
        total = len(df)
        report = []

        for field_name in check_fields:
            if field_name not in df.columns:
                report.append(FieldCoverage(
                    field_name=field_name,
                    total_count=total,
                    covered_count=0,
                    coverage_rate=0.0
                ))
            else:
                covered = df[field_name].notna().sum()
                rate = covered / total if total > 0 else 0.0
                report.append(FieldCoverage(
                    field_name=field_name,
                    total_count=total,
                    covered_count=covered,
                    coverage_rate=rate
                ))

        self._last_report = report
        return report

    def get_last_report(self) -> List[FieldCoverage]:
        """获取最近一次覆盖率报告"""
        return self._last_report

    def get_report_dict(self) -> Dict[str, Any]:
        """获取报告的字典格式"""
        return {r.field_name: r.to_dict() for r in self._last_report}

    def find_missing_values(self, df: pd.DataFrame, field: str) -> pd.DataFrame:
        """找出指定字段值为空的行"""
        if df is None or field not in df.columns:
            return pd.DataFrame()
        return df[df[field].isna()]

    def get_quality_score(self, df: pd.DataFrame, category: str) -> float:
        """计算数据质量评分

        Args:
            df: 数据 DataFrame
            category: 数据类别

        Returns:
            质量评分 (0-1)
        """
        if df is None or df.empty:
            return 0.0

        required = self.REQUIRED_FIELDS.get(category, [])
        recommended = self.RECOMMENDED_FIELDS.get(category, [])

        # 计算必填字段覆盖率
        required_coverage = []
        for f in required:
            if f in df.columns:
                covered = df[f].notna().sum()
                rate = covered / len(df)
                required_coverage.append(rate)
            else:
                required_coverage.append(0.0)

        # 计算建议字段覆盖率
        recommended_coverage = []
        for f in recommended:
            if f in df.columns:
                covered = df[f].notna().sum()
                rate = covered / len(df)
                recommended_coverage.append(rate)
            else:
                recommended_coverage.append(0.0)

        # 综合评分：必填权重 0.7，建议权重 0.3
        if required_coverage:
            required_score = sum(required_coverage) / len(required_coverage)
        else:
            required_score = 1.0

        if recommended_coverage:
            recommended_score = sum(recommended_coverage) / len(recommended_coverage)
        else:
            recommended_score = 0.5

        return 0.7 * required_score + 0.3 * recommended_score