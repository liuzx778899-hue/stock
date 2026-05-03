"""
数据质量分析服务

提供三个质量维度检查：
- CompletenessChecker: 完整度（字段覆盖率）
- FreshnessChecker: 新鲜度（数据滞后天数）
- AnomalyDetector: 异常检测（价格/涨跌幅/成交量异常）
"""
from datetime import datetime, date
from decimal import Decimal
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field

from sqlalchemy import text
from sqlalchemy.orm import Session

from config import config
from models import StockBasic, StockDailyKline, StockRealtimeQuote, DataQualityReport
from utils import logger


@dataclass
class FieldCoverage:
    """字段覆盖率"""
    field_name: str
    total_count: int
    covered_count: int
    coverage_rate: float


@dataclass
class AnomalyInfo:
    """异常信息"""
    type: str
    count: int
    samples: List[str] = field(default_factory=list)


class CompletenessChecker:
    """完整度检查器"""

    # 各数据类别的关键字段
    CATEGORY_FIELDS = {
        'stock_basic': ['symbol', 'name', 'industry', 'area', 'market', 'list_status'],
        'kline_daily': ['ts_code', 'trade_date', 'open', 'high', 'low', 'close', 'volume'],
        'realtime_quote': ['symbol', 'price', 'open', 'high', 'low', 'volume', 'update_time']
    }

    def check(self, session: Session, category: str) -> Dict[str, Any]:
        """检查指定类别的字段覆盖率"""
        if category not in self.CATEGORY_FIELDS:
            return {'total_records': 0, 'fields': {}}

        fields = self.CATEGORY_FIELDS[category]
        table_map = {
            'stock_basic': 'stock_basic',
            'kline_daily': 'stock_daily_kline',
            'realtime_quote': 'stock_realtime_quote'
        }
        table_name = table_map.get(category)
        if not table_name:
            return {'total_records': 0, 'fields': {}}

        # 获取总记录数
        count_sql = f"SELECT COUNT(*) as cnt FROM {table_name}"
        result = session.execute(text(count_sql)).fetchone()
        total_count = result[0] if result else 0

        if total_count == 0:
            return {'total_records': 0, 'fields': {}}

        # 检查每个字段
        field_results = {}
        for field_name in fields:
            try:
                sql = f"SELECT COUNT(*) as cnt FROM {table_name} WHERE `{field_name}` IS NOT NULL AND `{field_name}` != ''"
                result = session.execute(text(sql)).fetchone()
                covered = result[0] if result else 0
                rate = covered / total_count if total_count > 0 else 0
                field_results[field_name] = {
                    'count': covered,
                    'rate': round(rate, 4)
                }
            except Exception as e:
                logger.warning(f"检查字段 {field_name} 失败: {e}")
                field_results[field_name] = {'count': 0, 'rate': 0}

        return {
            'total_records': total_count,
            'fields': field_results
        }

    def calculate_score(self, detail: Dict[str, Any]) -> float:
        """计算完整度分数"""
        fields = detail.get('fields', {})
        if not fields:
            return 0.0

        rates = [f['rate'] for f in fields.values()]
        avg_rate = sum(rates) / len(rates) if rates else 0
        return round(avg_rate * 100, 1)


class FreshnessChecker:
    """新鲜度检查器"""

    def check(self, session: Session, category: str) -> Dict[str, Any]:
        """检查数据新鲜度"""
        try:
            if category == 'stock_basic':
                # 检查股票基础信息的更新时间（从 collect_log）
                sql = """
                    SELECT MAX(end_time) as last_time
                    FROM collect_log
                    WHERE task_type = 'basic' AND status = 'success'
                """
                result = session.execute(text(sql)).fetchone()
                last_collection = result[0] if result and result[0] else None

                # 检查最新上市日期
                sql2 = "SELECT MAX(list_date) as latest FROM stock_basic WHERE list_date IS NOT NULL"
                result2 = session.execute(text(sql2)).fetchone()
                latest_data_date = result2[0] if result2 and result2[0] else None

            elif category == 'kline_daily':
                # 检查K线最新交易日
                sql = "SELECT MAX(trade_date) as latest FROM stock_daily_kline"
                result = session.execute(text(sql)).fetchone()
                latest_data_date = result[0] if result and result[0] else None

                sql2 = """
                    SELECT MAX(end_time) as last_time
                    FROM collect_log
                    WHERE task_type = 'kline' AND status = 'success'
                """
                result2 = session.execute(text(sql2)).fetchone()
                last_collection = result2[0] if result2 and result2[0] else None

            elif category == 'realtime_quote':
                # 检查实时行情更新时间
                sql = "SELECT MAX(update_time) as latest FROM stock_realtime_quote"
                result = session.execute(text(sql)).fetchone()
                latest_data_date = result[0] if result and result[0] else None
                last_collection = latest_data_date
            else:
                return {
                    'last_collection_time': None,
                    'latest_data_date': None,
                    'days_lag': 999,
                    'is_trading_day_aligned': False
                }

            # 计算滞后天数
            if isinstance(latest_data_date, date):
                days_lag = (date.today() - latest_data_date).days
            elif isinstance(latest_data_date, datetime):
                days_lag = (datetime.now() - latest_data_date).days
            else:
                days_lag = 999

            return {
                'last_collection_time': str(last_collection) if last_collection else None,
                'latest_data_date': str(latest_data_date) if latest_data_date else None,
                'days_lag': max(0, days_lag),
                'is_trading_day_aligned': days_lag <= 1
            }

        except Exception as e:
            logger.error(f"检查新鲜度失败: {e}")
            return {
                'last_collection_time': None,
                'latest_data_date': None,
                'days_lag': 999,
                'is_trading_day_aligned': False
            }

    def calculate_score(self, detail: Dict[str, Any]) -> float:
        """计算新鲜度分数"""
        days_lag = detail.get('days_lag', 999)

        # 每滞后1天扣5分
        score = max(0, 100 - days_lag * 5)

        # 非交易日且滞后不超过2天不扣分
        if days_lag <= 2 and detail.get('is_trading_day_aligned', False):
            score = 100

        return round(score, 1)


class AnomalyDetector:
    """异常检测器"""

    def check(self, session: Session, category: str) -> Dict[str, Any]:
        """检测数据异常"""
        anomalies = []

        try:
            if category == 'stock_basic':
                # 检查重复记录
                sql = """
                    SELECT ts_code, COUNT(*) as cnt
                    FROM stock_basic
                    GROUP BY ts_code
                    HAVING cnt > 1
                    LIMIT 10
                """
                result = session.execute(text(sql)).fetchall()
                duplicates = [r[0] for r in result]
                anomalies.append(AnomalyInfo(
                    type='duplicate',
                    count=len(duplicates),
                    samples=duplicates[:5]
                ))

            elif category == 'kline_daily':
                # 检查价格为0
                sql = """
                    SELECT DISTINCT ts_code
                    FROM stock_daily_kline
                    WHERE (`open` = 0 OR `high` = 0 OR `low` = 0 OR `close` = 0)
                    AND trade_date >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
                    LIMIT 10
                """
                result = session.execute(text(sql)).fetchall()
                price_zeros = [r[0] for r in result]
                anomalies.append(AnomalyInfo(
                    type='price_zero',
                    count=len(price_zeros),
                    samples=price_zeros[:5]
                ))

                # 检查涨跌幅异常（>20%）
                sql = """
                    SELECT DISTINCT ts_code
                    FROM stock_daily_kline
                    WHERE ABS(pct_chg) > 20
                    AND trade_date >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
                    LIMIT 10
                """
                result = session.execute(text(sql)).fetchall()
                pct_extreme = [r[0] for r in result]
                anomalies.append(AnomalyInfo(
                    type='pct_chg_extreme',
                    count=len(pct_extreme),
                    samples=pct_extreme[:5]
                ))

                # 检查成交量为0（添加括号修复 OR/AND 优先级问题 BUG-084）
                sql = """
                    SELECT DISTINCT ts_code
                    FROM stock_daily_kline
                    WHERE (volume = 0 OR volume IS NULL)
                    AND trade_date >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
                    LIMIT 10
                """
                result = session.execute(text(sql)).fetchall()
                volume_zeros = [r[0] for r in result]
                anomalies.append(AnomalyInfo(
                    type='volume_zero',
                    count=len(volume_zeros),
                    samples=volume_zeros[:5]
                ))

            elif category == 'realtime_quote':
                # 检查实时行情异常
                sql = """
                    SELECT DISTINCT symbol
                    FROM stock_realtime_quote
                    WHERE price <= 0 OR price IS NULL
                    LIMIT 10
                """
                result = session.execute(text(sql)).fetchall()
                price_zeros = [r[0] for r in result]
                anomalies.append(AnomalyInfo(
                    type='price_zero',
                    count=len(price_zeros),
                    samples=price_zeros[:5]
                ))

                # 检查成交量为0
                sql = """
                    SELECT DISTINCT symbol
                    FROM stock_realtime_quote
                    WHERE volume = 0 OR volume IS NULL
                    LIMIT 10
                """
                result = session.execute(text(sql)).fetchall()
                volume_zeros = [r[0] for r in result]
                anomalies.append(AnomalyInfo(
                    type='volume_zero',
                    count=len(volume_zeros),
                    samples=volume_zeros[:5]
                ))

        except Exception as e:
            logger.error(f"检测异常失败: {e}")

        # 统计总检查数和异常数
        total_checked = 0
        try:
            table_map = {
                'stock_basic': 'stock_basic',
                'kline_daily': 'stock_daily_kline',
                'realtime_quote': 'stock_realtime_quote'
            }
            if category in table_map:
                sql = f"SELECT COUNT(*) FROM {table_map[category]}"
                result = session.execute(text(sql)).fetchone()
                total_checked = result[0] if result else 0
        except:
            pass

        return {
            'total_checked': total_checked,
            'anomalies': [
                {'type': a.type, 'count': a.count, 'samples': a.samples}
                for a in anomalies
            ]
        }

    def calculate_score(self, detail: Dict[str, Any]) -> float:
        """计算异常检测分数（100=无异常）"""
        anomalies = detail.get('anomalies', [])
        total_checked = detail.get('total_checked', 1)

        if total_checked == 0:
            return 100.0

        total_anomalies = sum(a['count'] for a in anomalies)
        anomaly_rate = total_anomalies / total_checked

        # 每1%异常扣10分
        score = max(0, 100 - anomaly_rate * 1000)
        return round(score, 1)


class QualityService:
    """质量分析服务"""

    CATEGORIES = ['stock_basic', 'kline_daily', 'realtime_quote']

    def __init__(self, session: Session):
        self.session = session
        self.completeness_checker = CompletenessChecker()
        self.freshness_checker = FreshnessChecker()
        self.anomaly_detector = AnomalyDetector()

    def check_all(self) -> List[Dict[str, Any]]:
        """检查所有数据类别"""
        results = []
        for category in self.CATEGORIES:
            result = self.check_category(category)
            results.append(result)
        return results

    def check_category(self, category: str) -> Dict[str, Any]:
        """检查指定类别"""
        # 完整度检查
        completeness_detail = self.completeness_checker.check(self.session, category)
        completeness_score = self.completeness_checker.calculate_score(completeness_detail)

        # 新鲜度检查
        freshness_detail = self.freshness_checker.check(self.session, category)
        freshness_score = self.freshness_checker.calculate_score(freshness_detail)

        # 异常检测
        anomaly_detail = self.anomaly_detector.check(self.session, category)
        anomaly_score = self.anomaly_detector.calculate_score(anomaly_detail)

        # 总分 = 完整度×0.4 + 新鲜度×0.3 + 异常×0.3
        total_score = (
            completeness_score * 0.4 +
            freshness_score * 0.3 +
            anomaly_score * 0.3
        )

        # 确定状态
        if total_score >= 80:
            status = 'ok'
        elif total_score >= 60:
            status = 'warning'
        else:
            status = 'critical'

        return {
            'data_category': category,
            'total_score': round(total_score, 1),
            'completeness_score': completeness_score,
            'freshness_score': freshness_score,
            'anomaly_score': anomaly_score,
            'completeness_detail': completeness_detail,
            'freshness_detail': freshness_detail,
            'anomaly_detail': anomaly_detail,
            'status': status
        }

    def save_report(self, results: List[Dict[str, Any]]) -> None:
        """保存检查报告到数据库"""
        check_time = datetime.now()
        for result in results:
            report = DataQualityReport(
                check_time=check_time,
                data_category=result['data_category'],
                total_score=Decimal(str(result['total_score'])),
                completeness_score=Decimal(str(result['completeness_score'])),
                freshness_score=Decimal(str(result['freshness_score'])),
                anomaly_score=Decimal(str(result['anomaly_score'])),
                completeness_detail=result['completeness_detail'],
                freshness_detail=result['freshness_detail'],
                anomaly_detail=result['anomaly_detail'],
                status=result['status']
            )
            self.session.add(report)
        self.session.commit()

    def get_latest_report(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """获取最近一次检查报告"""
        results = []
        for cat in self.CATEGORIES:
            if category and cat != category:
                continue
            # 每个类别独立创建 query，避免 filter 条件叠加 (BUG-085)
            report = self.session.query(DataQualityReport) \
                .filter(DataQualityReport.data_category == cat) \
                .order_by(DataQualityReport.check_time.desc()) \
                .first()
            if report:
                results.append({
                    'data_category': report.data_category,
                    'total_score': float(report.total_score),
                    'completeness_score': float(report.completeness_score),
                    'freshness_score': float(report.freshness_score),
                    'anomaly_score': float(report.anomaly_score),
                    'completeness_detail': report.completeness_detail,
                    'freshness_detail': report.freshness_detail,
                    'anomaly_detail': report.anomaly_detail,
                    'status': report.status,
                    'check_time': str(report.check_time)
                })
        return results

    def get_history(self, category: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
        """获取历史检查记录"""
        query = self.session.query(DataQualityReport)
        if category:
            query = query.filter(DataQualityReport.data_category == category)

        reports = query.order_by(DataQualityReport.check_time.desc()).limit(limit).all()
        return [
            {
                'data_category': r.data_category,
                'total_score': float(r.total_score),
                'check_time': str(r.check_time),
                'status': r.status
            }
            for r in reports
        ]
