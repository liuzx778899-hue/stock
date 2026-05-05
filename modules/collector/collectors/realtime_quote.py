"""
实时行情采集器（重构版）

使用 DataOrchestrator 进行数据采集
"""
import pandas as pd
from datetime import datetime
from typing import Dict, Any, Optional, Callable, List

from sqlalchemy.dialects.mysql import insert

from modules.collector.collectors.base import BaseCollector
from modules.collector.services.data_orchestrator import orchestrator
from modules.collector.services.field_merger import FieldMerger
from models import StockRealtimeQuote
from config import config
from utils import logger, TaskStoppedException


class RealtimeQuoteCollector(BaseCollector):
    """实时行情采集器

    使用编排器自动调度数据源
    """

    def __init__(self, engine=None):
        super().__init__(engine)
        self.orchestrator = orchestrator

    def collect(
        self,
        symbol: Optional[str] = None,
        progress_callback: Callable[[int, int, str], None] = None,
        stop_check: Callable[[], bool] = None
    ) -> Dict[str, Any]:
        """
        执行实时行情采集

        Args:
            symbol: 股票代码，None 表示全量
            progress_callback: 进度回调
            stop_check: 停止检查函数

        Returns:
            采集结果字典
        """
        log_entry = self._create_log_entry(
            f"实时行情采集{'('+symbol+')' if symbol else '(全量)'}",
            "realtime"
        )

        try:
            # 使用编排器采集数据
            df = self.orchestrator.collect_realtime(symbol, progress_callback)

            if stop_check and stop_check():
                raise TaskStoppedException()

            if df is None or df.empty:
                raise Exception("实时行情数据为空")

            # 数据转换
            df = self._transform_data(df)

            # 保存到数据库
            saved_count = self._save_to_db(df)

            # 完成日志
            log_entry = self._finalize_log_entry(
                log_entry,
                success_count=saved_count,
                failed_count=len(df) - saved_count,
                status="success"
            )
            self._save_collect_log(**log_entry)

            return {
                "success": True,
                "total": len(df),
                "saved": saved_count
            }

        except TaskStoppedException:
            log_entry = self._finalize_log_entry(
                log_entry, 0, 0, "stopped", "用户停止任务"
            )
            self._save_collect_log(**log_entry)
            return {"success": False, "status": "stopped"}

        except Exception as e:
            logger.error(f"实时行情采集失败: {e}")
            log_entry = self._finalize_log_entry(
                log_entry, 0, 0, "failed", str(e)
            )
            self._save_collect_log(**log_entry)
            return {"success": False, "error": str(e)}

    def collect_top_gainers(self, limit: int = 10) -> pd.DataFrame:
        """采集涨幅榜 TOP N"""
        df = self.orchestrator.collect_realtime()
        if df is None or df.empty:
            return pd.DataFrame()

        df = FieldMerger.normalize_columns(df)

        if 'pct_chg' in df.columns:
            df = df.sort_values('pct_chg', ascending=False).head(limit)

        return df

    def collect_top_losers(self, limit: int = 10) -> pd.DataFrame:
        """采集跌幅榜 TOP N"""
        df = self.orchestrator.collect_realtime()
        if df is None or df.empty:
            return pd.DataFrame()

        df = FieldMerger.normalize_columns(df)

        if 'pct_chg' in df.columns:
            df = df.sort_values('pct_chg', ascending=True).head(limit)

        return df

    def collect_top_volume(self, limit: int = 10) -> pd.DataFrame:
        """采集成交量榜 TOP N"""
        df = self.orchestrator.collect_realtime()
        if df is None or df.empty:
            return pd.DataFrame()

        df = FieldMerger.normalize_columns(df)

        if 'volume' in df.columns:
            df = df.sort_values('volume', ascending=False).head(limit)

        return df

    def _transform_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """转换数据格式"""
        if df is None or df.empty:
            return df

        df = FieldMerger.normalize_columns(df)

        # 确保 symbol 列存在
        if 'symbol' not in df.columns:
            for col in ['代码', 'code', 'dm']:
                if col in df.columns:
                    df['symbol'] = df[col]
                    break

        # 构建 ts_code
        df['ts_code'] = df['symbol'].apply(self._build_ts_code)

        return df

    def _build_ts_code(self, symbol: str) -> str:
        """构建 ts_code"""
        if symbol is None:
            return None

        symbol = str(symbol).strip()

        if '.' in symbol:
            return symbol

        if symbol.startswith('6'):
            return f"{symbol}.SH"
        elif symbol.startswith(('0', '3')):
            return f"{symbol}.SZ"
        elif symbol.startswith(('4', '8', '92', '93')):
            return f"{symbol}.BJ"
        return f"{symbol}.SZ"

    def _save_to_db(self, df: pd.DataFrame) -> int:
        """保存到数据库（UPSERT）"""
        if df is None or df.empty:
            return 0

        session = self.Session()
        saved = 0

        try:
            records = df.to_dict('records')

            for record in records:
                ts_code = record.get('ts_code')
                if ts_code is None:
                    continue

                stmt = insert(StockRealtimeQuote).values(
                    ts_code=ts_code,
                    symbol=record.get('symbol'),
                    name=record.get('name', ''),
                    price=record.get('price', 0),
                    open=record.get('open', 0),
                    high=record.get('high', 0),
                    low=record.get('low', 0),
                    pre_close=record.get('pre_close', 0),
                    volume=record.get('volume', 0),
                    amount=record.get('amount', 0),
                    pct_chg=record.get('pct_chg', 0),
                    turnover_rate=record.get('turnover_rate', 0),
                    update_time=datetime.now()
                ).on_duplicate_key_update(
                    name=record.get('name', ''),
                    price=record.get('price', 0),
                    open=record.get('open', 0),
                    high=record.get('high', 0),
                    low=record.get('low', 0),
                    pre_close=record.get('pre_close', 0),
                    volume=record.get('volume', 0),
                    amount=record.get('amount', 0),
                    pct_chg=record.get('pct_chg', 0),
                    turnover_rate=record.get('turnover_rate', 0),
                    update_time=datetime.now()
                )
                session.execute(stmt)
                saved += 1

            session.commit()
            logger.info(f"保存 {saved} 条实时行情数据")

        except Exception as e:
            session.rollback()
            logger.error(f"保存实时行情失败: {e}")

        finally:
            session.close()

        return saved