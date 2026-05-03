"""
股票日K线数据采集器（重构版）

使用 DataOrchestrator 进行数据采集，自动降级和补齐字段
"""
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Callable, List

from concurrent.futures import ThreadPoolExecutor, as_completed
from sqlalchemy.dialects.mysql import insert

from collectors.base import BaseCollector
from services.data_orchestrator import orchestrator
from services.field_merger import FieldMerger
from models import StockDailyKline, StockBasic
from config import config
from utils import logger, chunk_list, TaskStoppedException


class StockDailyKlineCollector(BaseCollector):
    """股票日K线数据采集器

    使用编排器自动调度数据源
    """

    def __init__(self, engine=None, thread_pool_size: int = None):
        super().__init__(engine)
        self.orchestrator = orchestrator
        self.thread_pool_size = thread_pool_size or config.collector.thread_pool_size

    def collect(
        self,
        start_date: str = None,
        end_date: str = None,
        symbols: List[str] = None,
        progress_callback: Callable[[int, int, str], None] = None,
        stop_check: Callable[[], bool] = None
    ) -> Dict[str, Any]:
        """
        执行K线数据采集

        Args:
            start_date: 开始日期（如 20240101）
            end_date: 结束日期（如 20241231）
            symbols: 股票代码列表，None 则采集全部
            progress_callback: 进度回调
            stop_check: 停止检查函数

        Returns:
            采集结果字典
        """
        log_entry = self._create_log_entry("K线数据采集", "kline")

        try:
            # 获取股票列表
            if symbols is None:
                symbols = self._get_stock_list()

            if not symbols:
                raise Exception("股票列表为空")

            # 设置默认日期范围
            if end_date is None:
                end_date = datetime.now().strftime('%Y%m%d')
            if start_date is None:
                start_date = (datetime.now() - timedelta(days=30)).strftime('%Y%m%d')

            logger.info(f"开始采集 {len(symbols)} 只股票的K线数据 ({start_date} ~ {end_date})")

            # 多线程采集
            results = self._collect_parallel(
                symbols, start_date, end_date,
                progress_callback, stop_check
            )

            # 统计结果
            success_count = sum(1 for r in results.values() if not r.empty)
            failed_count = len(symbols) - success_count

            # 完成日志
            status = "success" if failed_count == 0 else "partial"
            if stop_check and stop_check():
                status = "stopped"

            log_entry = self._finalize_log_entry(
                log_entry,
                success_count=success_count,
                failed_count=failed_count,
                status=status
            )
            self._save_collect_log(**log_entry)

            return {
                "success": True,
                "total": len(symbols),
                "success_count": success_count,
                "failed_count": failed_count,
                "status": status
            }

        except TaskStoppedException:
            log_entry = self._finalize_log_entry(
                log_entry, 0, 0, "stopped", "用户停止任务"
            )
            self._save_collect_log(**log_entry)
            return {"success": False, "status": "stopped"}

        except Exception as e:
            logger.error(f"K线采集失败: {e}")
            log_entry = self._finalize_log_entry(
                log_entry, 0, 0, "failed", str(e)
            )
            self._save_collect_log(**log_entry)
            return {"success": False, "error": str(e)}

    def collect_incremental(
        self,
        days: int = 30,
        progress_callback: Callable[[int, int, str], None] = None,
        stop_check: Callable[[], bool] = None
    ) -> Dict[str, Any]:
        """
        增量采集最近 N 天的K线数据

        Args:
            days: 天数
            progress_callback: 进度回调
            stop_check: 停止检查函数

        Returns:
            采集结果字典
        """
        end_date = datetime.now().strftime('%Y%m%d')
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y%m%d')

        return self.collect(
            start_date=start_date,
            end_date=end_date,
            progress_callback=progress_callback,
            stop_check=stop_check
        )

    def _get_stock_list(self) -> List[str]:
        """获取股票代码列表"""
        session = self.Session()
        try:
            stocks = session.query(StockBasic.ts_code).filter(
                StockBasic.list_status == 'L'
            ).all()
            return [s[0] for s in stocks]
        finally:
            session.close()

    def _collect_parallel(
        self,
        symbols: List[str],
        start_date: str,
        end_date: str,
        progress_callback: Callable,
        stop_check: Callable
    ) -> Dict[str, pd.DataFrame]:
        """多线程并行采集"""
        results = {}
        total = len(symbols)
        completed = 0

        with ThreadPoolExecutor(max_workers=self.thread_pool_size) as executor:
            # 提交任务
            future_to_symbol = {
                executor.submit(
                    self._collect_single,
                    symbol, start_date, end_date, stop_check
                ): symbol
                for symbol in symbols
            }

            # 处理结果
            for future in as_completed(future_to_symbol):
                symbol = future_to_symbol[future]

                try:
                    df = future.result()
                    if df is not None and not df.empty:
                        results[symbol] = df
                        self._save_single_kline(symbol, df)

                except TaskStoppedException:
                    break

                except Exception as e:
                    logger.debug(f"{symbol} K线采集失败: {e}")

                finally:
                    completed += 1
                    if progress_callback:
                        pct = int(completed / total * 100)
                        progress_callback(completed, total, f"采集K线 {pct}%")

        return results

    def _collect_single(
        self,
        ts_code: str,
        start_date: str,
        end_date: str,
        stop_check: Callable
    ) -> pd.DataFrame:
        """采集单只股票K线"""
        if stop_check and stop_check():
            raise TaskStoppedException()

        symbol = ts_code.split('.')[0]
        df = self.orchestrator.collect_kline(symbol, start_date, end_date)

        return df

    def _save_single_kline(self, ts_code: str, df: pd.DataFrame) -> int:
        """保存单只股票K线数据"""
        if df is None or df.empty:
            return 0

        df = FieldMerger.normalize_columns(df)
        symbol = ts_code.split('.')[0]

        # 计算 pre_close（昨收 = 上一条记录的 close）
        if 'close' in df.columns and 'pre_close' not in df.columns:
            df = df.sort_values('trade_date')
            df['pre_close'] = df['close'].shift(1)
            df = df.sort_index()  # 恢复原始顺序

        session = self.Session()
        saved = 0

        try:
            records = df.to_dict('records')

            for record in records:
                # MySQL 不支持 NaN，转为 None
                for key, value in list(record.items()):
                    if value is not None and isinstance(value, float) and pd.isna(value):
                        record[key] = None
                # 构建日期
                trade_date = record.get('日期') or record.get('date') or record.get('trade_date')
                if trade_date is None:
                    continue

                # 格式化日期
                if isinstance(trade_date, str):
                    trade_date = trade_date.replace('-', '')
                elif hasattr(trade_date, 'strftime'):
                    trade_date = trade_date.strftime('%Y%m%d')

                stmt = insert(StockDailyKline).values(
                    ts_code=ts_code,
                    trade_date=trade_date,
                    open=record.get('open', 0),
                    high=record.get('high', 0),
                    low=record.get('low', 0),
                    close=record.get('close', 0),
                    pre_close=record.get('pre_close'),
                    volume=record.get('volume', 0),
                    amount=record.get('amount', 0),
                    pct_chg=record.get('pct_chg', 0),
                    turnover_rate=record.get('turnover_rate', 0)
                ).on_duplicate_key_update(
                    open=record.get('open', 0),
                    high=record.get('high', 0),
                    low=record.get('low', 0),
                    close=record.get('close', 0),
                    pre_close=record.get('pre_close'),
                    volume=record.get('volume', 0),
                    amount=record.get('amount', 0),
                    pct_chg=record.get('pct_chg', 0),
                    turnover_rate=record.get('turnover_rate', 0)
                )
                session.execute(stmt)
                saved += 1

            session.commit()

        except Exception as e:
            session.rollback()
            logger.debug(f"保存 {ts_code} K线失败: {e}")

        finally:
            session.close()

        return saved