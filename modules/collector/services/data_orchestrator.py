"""
数据编排器

核心调度：按质量优先级尝试各数据源，自动补齐缺失字段
"""
import pandas as pd
from typing import Dict, List, Optional, Callable, Any
from datetime import datetime, timedelta

from sqlalchemy import create_engine, text

from modules.collector.adapters.registry import registry
from modules.collector.adapters.base import DataCategory, DataProvider
from modules.collector.services.data_validator import DataValidator
from modules.collector.services.field_merger import FieldMerger
from modules.collector.services.datasource_service import datasource_service
from config import config
from utils import logger


class DataOrchestrator:
    """数据编排器

    职责:
    - 调度多数据源采集
    - 按质量优先级尝试
    - 自动补齐缺失字段
    - 统一降级策略
    - 支持强制数据源选择
    """

    def __init__(self):
        self.registry = registry
        self.validator = DataValidator()
        self.merger = FieldMerger()
        self.datasource_service = datasource_service
        self._last_field_report: Dict[str, Any] = {}

    def get_providers(self, category: DataCategory) -> List[DataProvider]:
        """获取指定类别可用的数据源列表（支持强制数据源）"""
        forced = self.datasource_service.get_forced_source()
        if forced:
            # 强制模式：只返回指定的 Provider
            provider = self.registry.get_provider(forced)
            if provider and provider.enabled and provider.supports(category):
                return [provider]
            # 强制 Provider 不支持当前类别时回退到自动选择
            logger.warning(f"强制数据源 {forced} 不支持 {category.value}，回退到自动选择")
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

        providers = self.get_providers(DataCategory.KLINE_DAILY)

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

        providers = self.get_providers(DataCategory.REALTIME_QUOTE)

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
        providers = self.get_providers(category)

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

        # 提取股票列表（用于传入 Provider，首次采集时 DB 为空）
        symbols = df['symbol'].tolist() if 'symbol' in df.columns else None

        # 寻找能提供此字段的数据源
        providers = self.get_providers(category)

        for provider in providers:
            try:
                if category == DataCategory.STOCK_INDUSTRY:
                    # 传入 symbols 参数，支持在首次采集（DB 为空）时直接使用数据框的股票列表
                    try:
                        mapping = provider.fetch_industry_mapping(symbols=symbols)
                    except TypeError:
                        mapping = provider.fetch_industry_mapping()
                elif category == DataCategory.STOCK_AREA:
                    try:
                        mapping = provider.fetch_area_mapping(symbols=symbols)
                    except TypeError:
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

    def collect_concept(
        self,
        progress_callback: Callable[[int, int, str], None] = None
    ) -> Dict[str, List[str]]:
        """采集概念板块映射数据

        Args:
            progress_callback: 进度回调函数 (current, total, stage)

        Returns:
            {concept_name: [symbol1, symbol2, ...]} 映射字典
        """
        logger.info("开始采集概念板块数据...")

        providers = self.get_providers(DataCategory.CONCEPT)

        for provider in providers:
            try:
                mapping = provider.fetch_concept_mapping()
                if mapping:
                    total_concepts = len(mapping)
                    total_relations = sum(len(v) for v in mapping.values())
                    logger.info(f"从 {provider.provider_name} 获取 {total_concepts} 个概念，{total_relations} 条映射")
                    return mapping
            except NotImplementedError:
                continue
            except Exception as e:
                logger.warning(f"{provider.provider_name} 获取概念板块失败: {e}")
                continue

        logger.error("所有数据源都无法获取概念板块数据")
        return {}

    def get_kline(
        self,
        symbol: str,
        period: str = "day",
        limit: int = 200,
        end_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """获取K线数据（支持周/月/年聚合）

        Args:
            symbol: 股票代码（6位数字）
            period: 周期 day|week|month|year
            limit: 返回条数（默认200，最大800）
            end_date: 截止日期（默认今天）

        Returns:
            {
                "symbol": "000001",
                "name": "平安银行",
                "period": "day",
                "data": [{trade_date, open, high, low, close, volume, ...}]
            }
        """
        # 参数校验
        if period not in ("day", "week", "month", "year"):
            period = "day"
        limit = min(max(limit, 1), 800)
        end_date = end_date or datetime.now().strftime("%Y-%m-%d")

        # 构建 ts_code（需要带后缀）
        ts_code = self._build_ts_code(symbol)

        # 查询日线数据
        try:
            engine = create_engine(config.database.connection_url)
            query = text("""
                SELECT trade_date, `open`, high, low, `close`, pre_close,
                       volume, amount, pct_chg, turnover_rate
                FROM stock_daily_kline
                WHERE ts_code = :ts_code AND trade_date <= :end_date
                ORDER BY trade_date DESC
                LIMIT :limit
            """)
            df = pd.read_sql(query, engine, params={
                "ts_code": ts_code,
                "end_date": end_date,
                "limit": limit * 4 if period != "day" else limit
            })
            engine.dispose()
        except Exception as e:
            logger.error(f"查询K线数据失败: {e}")
            return {"symbol": symbol, "name": "", "period": period, "data": []}

        if df.empty:
            return {"symbol": symbol, "name": "", "period": period, "data": []}

        # 按日期升序排列
        df = df.sort_values("trade_date").reset_index(drop=True)

        # 周期聚合
        if period != "day":
            df = self._aggregate_kline(df, period)

        # 计算均线
        df = self._calculate_ma(df)

        # 转换为列表（倒序，最新在前）
        data = df.tail(limit).to_dict("records")
        # 将日期类型转为字符串（JSON 序列化兼容）
        for row in data:
            if "trade_date" in row and hasattr(row["trade_date"], "strftime"):
                row["trade_date"] = row["trade_date"].strftime("%Y-%m-%d")
            # nan/inf 转 None（JSON 安全，Starlette 的 JSONResponse 使用 allow_nan=False）
            for k, v in row.items():
                if v is not None and isinstance(v, float):
                    if v != v or v == float("inf") or v == float("-inf"):
                        row[k] = None

        # 获取股票名称
        name = self._get_stock_name(symbol)

        return {
            "symbol": symbol,
            "name": name,
            "period": period,
            "data": data
        }

    def _build_ts_code(self, symbol: str) -> str:
        """构建 ts_code（带市场后缀）"""
        symbol = symbol.strip()
        if "." in symbol:
            return symbol
        if symbol.startswith('6'):
            return f"{symbol}.SH"
        elif symbol.startswith(('0', '3')):
            return f"{symbol}.SZ"
        elif symbol.startswith(('4', '8', '92', '93')):
            return f"{symbol}.BJ"
        return f"{symbol}.SZ"

    def _aggregate_kline(self, df: pd.DataFrame, period: str) -> pd.DataFrame:
        """聚合K线数据为周/月/年线"""
        df = df.copy()
        df["trade_date"] = pd.to_datetime(df["trade_date"])
        df = df.set_index("trade_date").sort_index()

        freq_map = {"week": "W", "month": "M", "year": "Y"}
        freq = freq_map.get(period, "W")

        agg_df = df.resample(freq).agg({
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
            "amount": "sum",
            "pct_chg": "sum",
        }).dropna()

        return agg_df.reset_index()

    def _calculate_ma(self, df: pd.DataFrame, periods: List[int] = None) -> pd.DataFrame:
        """计算均线"""
        if periods is None:
            periods = [5, 10, 20, 60]

        for p in periods:
            if len(df) >= p:
                df[f"ma{p}"] = df["close"].rolling(window=p).mean().round(2)
            else:
                df[f"ma{p}"] = None

        return df

    def _get_stock_name(self, symbol: str) -> str:
        """获取股票名称"""
        try:
            engine = create_engine(config.database.connection_url)
            query = text("SELECT name FROM stock_basic WHERE symbol = :symbol LIMIT 1")
            result = engine.connect().execute(query, {"symbol": symbol}).fetchone()
            engine.dispose()
            return result[0] if result else ""
        except Exception:
            return ""

    def get_registry(self) -> 'DataSourceRegistry':
        """获取注册中心实例"""
        return self.registry


# 全局编排器实例
orchestrator = DataOrchestrator()