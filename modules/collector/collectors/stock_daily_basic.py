"""
每日基础指标采集器

采集总股本/流通股本/总市值/流通市值/换手率
使用 DataOrchestrator 进行数据采集
"""
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Callable, List

from concurrent.futures import ThreadPoolExecutor, as_completed
from sqlalchemy.dialects.mysql import insert

from modules.collector.collectors.base import BaseCollector
from modules.collector.services.data_orchestrator import orchestrator
from modules.collector.services.field_merger import FieldMerger
from models import StockBasic
from config import config
from utils import logger, TaskStoppedException


class StockDailyBasicCollector(BaseCollector):
    """每日基础指标采集器

    采集：
    - 总股本 (total_share)
    - 流通股本 (circ_share)
    - 总市值 (total_mv)
    - 流通市值 (circ_mv)
    - 换手率 (turnover_rate)
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
        执行每日基础指标采集

        Args:
            start_date: 开始日期
            end_date: 结束日期
            symbols: 股票代码列表
            progress_callback: 进度回调
            stop_check: 停止检查函数

        Returns:
            采集结果字典
        """
        log_entry = self._create_log_entry("每日基础指标采集", "daily_basic")

        try:
            if symbols is None:
                symbols = self._get_stock_list()

            if not symbols:
                raise Exception("股票列表为空")

            if end_date is None:
                end_date = datetime.now().strftime('%Y%m%d')
            if start_date is None:
                start_date = (datetime.now() - timedelta(days=30)).strftime('%Y%m%d')

            logger.info(f"开始采集 {len(symbols)} 只股票的每日基础指标 ({start_date} ~ {end_date})")

            results = self._collect_parallel(
                symbols, start_date, end_date,
                progress_callback, stop_check
            )

            success_count = sum(1 for r in results.values() if r.get("saved", 0) > 0)
            failed_count = len(symbols) - success_count

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
            logger.error(f"每日基础指标采集失败: {e}")
            log_entry = self._finalize_log_entry(
                log_entry, 0, 0, "failed", str(e)
            )
            self._save_collect_log(**log_entry)
            return {"success": False, "error": str(e)}

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
    ) -> Dict[str, Dict]:
        """多线程并行采集"""
        results = {}
        total = len(symbols)
        completed = 0

        with ThreadPoolExecutor(max_workers=self.thread_pool_size) as executor:
            future_to_symbol = {
                executor.submit(
                    self._collect_single,
                    symbol, start_date, end_date, stop_check
                ): symbol
                for symbol in symbols
            }

            for future in as_completed(future_to_symbol):
                symbol = future_to_symbol[future]

                try:
                    data = future.result()
                    if data and data.get("saved", 0) > 0:
                        results[symbol] = data

                except TaskStoppedException:
                    break

                except Exception as e:
                    logger.debug(f"{symbol} 每日基础指标采集失败: {e}")

                finally:
                    completed += 1
                    if progress_callback:
                        pct = int(completed / total * 100)
                        progress_callback(completed, total, f"采集每日基础指标 {pct}%")

        return results

    def _collect_single(
        self,
        ts_code: str,
        start_date: str,
        end_date: str,
        stop_check: Callable
    ) -> Dict:
        """采集单只股票每日基础指标"""
        if stop_check and stop_check():
            raise TaskStoppedException()

        saved = 0
        data = {"ts_code": ts_code, "saved": 0}

        try:
            df = self.orchestrator.collect_daily_basic(ts_code, start_date, end_date)
            if df is not None and not df.empty:
                saved = self._save_daily_basic(ts_code, df)
                data["saved"] = saved
        except AttributeError:
            logger.warning(f"orchestrator.collect_daily_basic 方法尚未实现（等待 develop1 Phase 3）")
        except Exception as e:
            logger.debug(f"{ts_code} 每日基础指标采集失败: {e}")

        return data

    def _save_daily_basic(self, ts_code: str, df: pd.DataFrame) -> int:
        """保存每日基础指标数据"""
        if df is None or df.empty:
            return 0

        df = FieldMerger.normalize_columns(df)
        saved = 0
        session = self.Session()

        try:
            records = df.to_dict('records')

            for record in records:
                trade_date = record.get('trade_date')
                if trade_date is None:
                    continue

                if hasattr(trade_date, 'strftime'):
                    trade_date = trade_date.strftime('%Y%m%d')
                elif isinstance(trade_date, str):
                    trade_date = trade_date.replace('-', '')[:8]

                try:
                    from models import StockDailyBasic
                    stmt = insert(StockDailyBasic).values(
                        ts_code=ts_code,
                        trade_date=trade_date,
                        total_share=record.get('total_share'),
                        circ_share=record.get('circ_share'),
                        total_mv=record.get('total_mv'),
                        circ_mv=record.get('circ_mv'),
                        turnover_rate=record.get('turnover_rate')
                    ).on_duplicate_key_update(
                        total_share=record.get('total_share'),
                        circ_share=record.get('circ_share'),
                        total_mv=record.get('total_mv'),
                        circ_mv=record.get('circ_mv'),
                        turnover_rate=record.get('turnover_rate')
                    )
                    session.execute(stmt)
                    saved += 1
                except ImportError:
                    pass

            session.commit()

        except Exception as e:
            session.rollback()
            logger.debug(f"保存 {ts_code} 每日基础指标失败: {e}")

        finally:
            session.close()

        return saved
