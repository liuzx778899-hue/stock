"""
QMT 数据源适配器（只读）

QMT（国信iQuant）是券商直连交易所的数据源，API 测试已验证可覆盖 64 个数据接口。
核心约束：QMT 策略只能在 iQuant GUI 内运行，无法被外部 Python 调用。

架构：采用"数据库桥接"模式
- QMT GUI 内的数据泵脚本（qmt_pump_*.py）直写 OceanBase
- 本适配器只从 OB 表 SELECT 数据

特点：
- priority=0 最高优先级（券商直连，数据最实时准确）
- 覆盖 K线/财务/股本/股东/实时行情等 12 类数据
"""
from __future__ import annotations

from typing import Dict, List, Optional
import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from modules.collector.adapters.base import DataProvider, DataCategory, ProviderCapability
from utils import logger
from config import config


class QMTProvider(DataProvider):
    """QMT 数据源适配器（只读）

    从 OceanBase 数据库读取 QMT 数据泵写入的数据。
    """

    _engine: Optional[object] = None
    _session_factory: Optional[object] = None

    def __init__(self):
        """初始化 QMT Provider（只读数据库连接）"""
        try:
            db_url = config.database.connection_url
            self._engine = create_engine(db_url, pool_pre_ping=True, pool_recycle=3600)
            self._session_factory = sessionmaker(bind=self._engine)
            logger.info("[qmt] 数据库连接初始化成功")
        except Exception as e:
            logger.error(f"[qmt] 数据库连接初始化失败: {e}")

    @property
    def provider_name(self) -> str:
        return "qmt"

    @property
    def capabilities(self) -> List[ProviderCapability]:
        return [
            ProviderCapability(
                category=DataCategory.KLINE_DAILY,
                fields=["trade_date", "open", "high", "low", "close",
                        "pre_close", "volume", "amount", "turnover_rate", "pct_chg"],
                quality_score=0.98,
                cost_type="free",
                latency_ms=10,
            ),
            ProviderCapability(
                category=DataCategory.DAILY_BASIC,
                fields=["ts_code", "trade_date", "total_share", "circ_share",
                        "total_mv", "circ_mv", "turnover_rate", "pe", "pb"],
                quality_score=0.95,
                cost_type="free",
                latency_ms=10,
            ),
            ProviderCapability(
                category=DataCategory.FINANCIAL_INCOME,
                fields=["ts_code", "ann_date", "end_date", "operating_revenue",
                        "oper_profit", "net_profit", "basic_eps"],
                quality_score=0.95,
                cost_type="free",
                latency_ms=10,
            ),
            ProviderCapability(
                category=DataCategory.FINANCIAL_BALANCE,
                fields=["ts_code", "end_date", "total_assets", "fix_assets",
                        "total_liabilities", "total_equity"],
                quality_score=0.95,
                cost_type="free",
                latency_ms=10,
            ),
            ProviderCapability(
                category=DataCategory.FINANCIAL_CASHFLOW,
                fields=["ts_code", "end_date", "net_cash_flows_oper_act",
                        "net_cash_flows_inv_act", "net_cash_flows_fin_act"],
                quality_score=0.95,
                cost_type="free",
                latency_ms=10,
            ),
            ProviderCapability(
                category=DataCategory.FINANCIAL_PER_SHARE,
                fields=["ts_code", "end_date", "eps", "bvps",
                        "revenue_per_share", "oper_profit_per_share"],
                quality_score=0.95,
                cost_type="free",
                latency_ms=10,
            ),
            ProviderCapability(
                category=DataCategory.SHAREHOLDER_TOP10,
                fields=["ts_code", "ann_date", "holder_name", "hold_amount",
                        "hold_ratio", "holder_rank", "holder_type"],
                quality_score=0.95,
                cost_type="free",
                latency_ms=10,
            ),
            ProviderCapability(
                category=DataCategory.SHAREHOLDER_COUNT,
                fields=["ts_code", "ann_date", "holder_num"],
                quality_score=0.90,
                cost_type="free",
                latency_ms=10,
            ),
            ProviderCapability(
                category=DataCategory.ST_STATUS,
                fields=["ts_code", "st_type", "is_st", "start_date", "end_date"],
                quality_score=0.99,
                cost_type="free",
                latency_ms=10,
            ),
            ProviderCapability(
                category=DataCategory.IPO_INFO,
                fields=["ts_code", "ipo_date", "issue_price", "issue_amount", "raise_amount"],
                quality_score=0.99,
                cost_type="free",
                latency_ms=10,
            ),
            ProviderCapability(
                category=DataCategory.TICK_DATA,
                fields=["ts_code", "trade_time", "price", "volume", "amount", "trade_type"],
                quality_score=0.95,
                cost_type="free",
                latency_ms=10,
            ),
            ProviderCapability(
                category=DataCategory.LONGHUBANG,
                fields=["ts_code", "trade_date", "direction", "rank",
                        "sales_department", "amount", "net_amount"],
                quality_score=0.95,
                cost_type="free",
                latency_ms=10,
            ),
            ProviderCapability(
                category=DataCategory.REALTIME_DEPTH,
                fields=["symbol", "bid_price1", "bid_vol1", "bid_price2", "bid_vol2",
                        "bid_price3", "bid_vol3", "bid_price4", "bid_vol4", "bid_price5", "bid_vol5",
                        "ask_price1", "ask_vol1", "ask_price2", "ask_vol2",
                        "ask_price3", "ask_vol3", "ask_price4", "ask_vol4", "ask_price5", "ask_vol5"],
                quality_score=0.98,
                cost_type="free",
                latency_ms=10,
            ),
        ]

    @property
    def field_mapping(self) -> Dict[DataCategory, Dict[str, str]]:
        return {}  # QMT 数据已标准化，无需映射

    def _execute_query(self, sql: str) -> pd.DataFrame:
        """执行 SQL 查询"""
        if not self._engine:
            logger.warning("[qmt] 数据库连接未初始化")
            return pd.DataFrame()
        try:
            with self._engine.connect() as conn:
                df = pd.read_sql(text(sql), conn)
                return df
        except Exception as e:
            logger.error(f"[qmt] SQL 执行失败: {e}")
            return pd.DataFrame()

    def _normalize_code(self, symbol: str) -> str:
        """标准化股票代码为 ts_code 格式"""
        code = symbol.replace('.SZ', '').replace('.SH', '').replace('.BJ', '').zfill(6)
        if code.startswith('6'):
            return f"{code}.SH"
        elif code.startswith(('0', '3')):
            return f"{code}.SZ"
        elif code.startswith(('4', '8', '92')):
            return f"{code}.BJ"
        return f"{code}.SZ"

    # ========== K线数据 ==========

    def fetch_kline(self, symbol: str, start_date: str, end_date: str,
                    adjust: str = "qfq") -> pd.DataFrame:
        """获取 K 线数据（QMT 已在前复权模式下写入）"""
        ts_code = self._normalize_code(symbol)
        start = start_date.replace('-', '')
        end = end_date.replace('-', '')

        sql = f"""
            SELECT trade_date, open, high, low, close, pre_close,
                   volume, amount, turnover_rate, pct_chg
            FROM stock_daily_kline
            WHERE ts_code = '{ts_code}'
              AND trade_date >= '{start}'
              AND trade_date <= '{end}'
            ORDER BY trade_date
        """
        df = self._execute_query(sql)
        if not df.empty:
            logger.info(f"[qmt] 获取 {symbol} K线 {len(df)} 条")
        return df

    # ========== 每日基础指标 ==========

    def fetch_daily_basic(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """获取每日基础指标"""
        code = self._normalize_code(ts_code)
        start = start_date.replace('-', '')
        end = end_date.replace('-', '')

        sql = f"""
            SELECT ts_code, trade_date, total_share, circ_share,
                   total_mv, circ_mv, turnover_rate, pe, pb
            FROM stock_daily_basic
            WHERE ts_code = '{code}'
              AND trade_date >= '{start}'
              AND trade_date <= '{end}'
            ORDER BY trade_date
        """
        df = self._execute_query(sql)
        if not df.empty:
            logger.info(f"[qmt] 获取 {ts_code} 每日基础指标 {len(df)} 条")
        return df

    # ========== 财务数据 ==========

    def fetch_financial_income(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """获取利润表数据"""
        code = self._normalize_code(ts_code)
        sql = f"""
            SELECT ts_code, ann_date, f_ann_date, end_date,
                   operating_revenue, oper_cost, oper_profit, net_profit, basic_eps
            FROM stock_financial_income
            WHERE ts_code = '{code}'
            ORDER BY end_date DESC
            LIMIT 20
        """
        df = self._execute_query(sql)
        if not df.empty:
            logger.info(f"[qmt] 获取 {ts_code} 利润表 {len(df)} 条")
        return df

    def fetch_financial_balance(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """获取资产负债表数据"""
        code = self._normalize_code(ts_code)
        sql = f"""
            SELECT ts_code, ann_date, end_date,
                   total_assets, fix_assets, total_liabilities, total_equity
            FROM stock_financial_balance
            WHERE ts_code = '{code}'
            ORDER BY end_date DESC
            LIMIT 20
        """
        df = self._execute_query(sql)
        if not df.empty:
            logger.info(f"[qmt] 获取 {ts_code} 资产负债表 {len(df)} 条")
        return df

    def fetch_financial_cashflow(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """获取现金流量表数据"""
        code = self._normalize_code(ts_code)
        sql = f"""
            SELECT ts_code, ann_date, end_date,
                   net_cash_flows_oper_act, net_cash_flows_inv_act, net_cash_flows_fin_act
            FROM stock_financial_cashflow
            WHERE ts_code = '{code}'
            ORDER BY end_date DESC
            LIMIT 20
        """
        df = self._execute_query(sql)
        if not df.empty:
            logger.info(f"[qmt] 获取 {ts_code} 现金流量表 {len(df)} 条")
        return df

    def fetch_financial_per_share(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """获取每股指标数据"""
        code = self._normalize_code(ts_code)
        sql = f"""
            SELECT ts_code, ann_date, end_date,
                   eps, bvps, revenue_per_share, oper_profit_per_share
            FROM stock_financial_per_share
            WHERE ts_code = '{code}'
            ORDER BY end_date DESC
            LIMIT 20
        """
        df = self._execute_query(sql)
        if not df.empty:
            logger.info(f"[qmt] 获取 {ts_code} 每股指标 {len(df)} 条")
        return df

    # ========== 股东数据 ==========

    def fetch_shareholder_top10(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """获取十大股东数据"""
        code = self._normalize_code(ts_code)
        sql = f"""
            SELECT ts_code, ann_date, holder_name, hold_amount,
                   hold_ratio, holder_rank, holder_type
            FROM stock_shareholder_top10
            WHERE ts_code = '{code}'
            ORDER BY ann_date DESC, holder_rank
            LIMIT 40
        """
        df = self._execute_query(sql)
        if not df.empty:
            logger.info(f"[qmt] 获取 {ts_code} 十大股东 {len(df)} 条")
        return df

    def fetch_shareholder_count(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """获取股东户数数据"""
        code = self._normalize_code(ts_code)
        sql = f"""
            SELECT ts_code, ann_date, holder_num
            FROM stock_shareholder_count
            WHERE ts_code = '{code}'
            ORDER BY ann_date DESC
            LIMIT 20
        """
        df = self._execute_query(sql)
        if not df.empty:
            logger.info(f"[qmt] 获取 {ts_code} 股东户数 {len(df)} 条")
        return df

    # ========== ST/IPO ==========

    def fetch_st_status(self, ts_code: str) -> pd.DataFrame:
        """获取 ST 状态"""
        code = self._normalize_code(ts_code)
        sql = f"""
            SELECT ts_code, st_type, is_st, start_date, end_date
            FROM stock_st_status
            WHERE ts_code = '{code}'
        """
        df = self._execute_query(sql)
        if not df.empty:
            logger.info(f"[qmt] 获取 {ts_code} ST 状态")
        return df

    def fetch_ipo_info(self, ts_code: str) -> pd.DataFrame:
        """获取 IPO 信息"""
        code = self._normalize_code(ts_code)
        sql = f"""
            SELECT ts_code, ipo_date, issue_price, issue_amount, raise_amount
            FROM stock_ipo_info
            WHERE ts_code = '{code}'
        """
        df = self._execute_query(sql)
        if not df.empty:
            logger.info(f"[qmt] 获取 {ts_code} IPO 信息")
        return df

    # ========== Tick/龙虎榜 ==========

    def fetch_tick_data(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """获取 Tick 明细数据"""
        code = self._normalize_code(ts_code)
        start = start_date.replace('-', '')
        end = end_date.replace('-', '')

        sql = f"""
            SELECT ts_code, trade_time, price, volume, amount, trade_type
            FROM stock_tick_data
            WHERE ts_code = '{code}'
              AND DATE(trade_time) >= '{start}'
              AND DATE(trade_time) <= '{end}'
            ORDER BY trade_time
            LIMIT 10000
        """
        df = self._execute_query(sql)
        if not df.empty:
            logger.info(f"[qmt] 获取 {ts_code} Tick 数据 {len(df)} 条")
        return df

    def fetch_longhubang(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """获取龙虎榜数据"""
        code = self._normalize_code(ts_code)
        start = start_date.replace('-', '')
        end = end_date.replace('-', '')

        sql = f"""
            SELECT ts_code, trade_date, direction, rank,
                   sales_department, amount, net_amount
            FROM stock_longhubang
            WHERE ts_code = '{code}'
              AND trade_date >= '{start}'
              AND trade_date <= '{end}'
            ORDER BY trade_date DESC, rank
        """
        df = self._execute_query(sql)
        if not df.empty:
            logger.info(f"[qmt] 获取 {ts_code} 龙虎榜 {len(df)} 条")
        return df

    # ========== 五档盘口 ==========

    def fetch_realtime_depth(self, symbol: str) -> pd.DataFrame:
        """获取五档盘口数据"""
        code = symbol.replace('.SZ', '').replace('.SH', '').replace('.BJ', '').zfill(6)
        sql = f"""
            SELECT symbol, bid_price1, bid_vol1, bid_price2, bid_vol2,
                   bid_price3, bid_vol3, bid_price4, bid_vol4, bid_price5, bid_vol5,
                   ask_price1, ask_vol1, ask_price2, ask_vol2,
                   ask_price3, ask_vol3, ask_price4, ask_vol4, ask_price5, ask_vol5,
                   update_time
            FROM stock_realtime_depth
            WHERE symbol = '{code}'
            ORDER BY update_time DESC
            LIMIT 1
        """
        df = self._execute_query(sql)
        if not df.empty:
            logger.info(f"[qmt] 获取 {symbol} 五档盘口")
        return df

    def health_check(self) -> bool:
        """健康检查"""
        if not self._engine:
            return False
        try:
            sql = "SELECT COUNT(*) as cnt FROM stock_daily_kline LIMIT 1"
            df = self._execute_query(sql)
            return not df.empty
        except Exception:
            return False
