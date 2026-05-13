"""
股东数据采集器

采集十大股东/流通股东/股东户数
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


class StockShareholderCollector(BaseCollector):
    """股东数据采集器

    采集：
    - 十大股东 (holder)
    - 十大流通股东 (flow_holder)
    - 股东户数 (holder_count)
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
        holder_type: str = "all",
        progress_callback: Callable[[int, int, str], None] = None,
        stop_check: Callable[[], bool] = None
    ) -> Dict[str, Any]:
        """
        执行股东数据采集

        Args:
            start_date: 开始日期
            end_date: 结束日期
            symbols: 股票代码列表
            holder_type: 股东类型 (holder/flow_holder/count/all)
            progress_callback: 进度回调
            stop_check: 停止检查函数

        Returns:
            采集结果字典
        """
        log_entry = self._create_log_entry("股东数据采集", "shareholder")

        try:
            if symbols is None:
                symbols = self._get_stock_list()

            if not symbols:
                raise Exception("股票列表为空")

            if end_date is None:
                end_date = datetime.now().strftime('%Y%m%d')
            if start_date is None:
                start_date = (datetime.now() - timedelta(days=365*3)).strftime('%Y%m%d')

            logger.info(f"开始采集 {len(symbols)} 只股票的股东数据 ({start_date} ~ {end_date})")

            results = self._collect_parallel(
                symbols, start_date, end_date, holder_type,
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
            logger.error(f"股东数据采集失败: {e}")
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
        holder_type: str,
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
                    symbol, start_date, end_date, holder_type, stop_check
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
                    logger.debug(f"{symbol} 股东数据采集失败: {e}")

                finally:
                    completed += 1
                    if progress_callback:
                        pct = int(completed / total * 100)
                        progress_callback(completed, total, f"采集股东数据 {pct}%")

        return results

    def _collect_single(
        self,
        ts_code: str,
        start_date: str,
        end_date: str,
        holder_type: str,
        stop_check: Callable
    ) -> Dict:
        """采集单只股票股东数据"""
        if stop_check and stop_check():
            raise TaskStoppedException()

        saved = 0
        data = {"ts_code": ts_code, "saved": 0}

        try:
            df = self.orchestrator.collect_shareholders(ts_code, start_date, end_date, holder_type)
            if df is not None and not df.empty:
                saved = self._save_shareholders(ts_code, df, holder_type)
                data["saved"] = saved
        except AttributeError:
            logger.warning(f"orchestrator.collect_shareholders 方法尚未实现（等待 develop1 Phase 3）")
        except Exception as e:
            logger.debug(f"{ts_code} 股东采集失败: {e}")

        return data

    def _save_shareholders(self, ts_code: str, df: pd.DataFrame, holder_type: str) -> int:
        """保存股东数据"""
        if df is None or df.empty:
            return 0

        df = FieldMerger.normalize_columns(df)
        saved = 0
        session = self.Session()

        try:
            records = df.to_dict('records')

            for record in records:
                report_date = record.get('report_date') or record.get('ann_date')
                if report_date is None:
                    continue

                if hasattr(report_date, 'strftime'):
                    report_date = report_date.strftime('%Y%m%d')
                elif isinstance(report_date, str):
                    report_date = report_date.replace('-', '')[:8]

                holder_name = record.get('holder_name', '')
                holder_type_val = record.get('holder_type', holder_type)

                if holder_name:
                    try:
                        from models import StockShareholderTop10
                        stmt = insert(StockShareholderTop10).values(
                            ts_code=ts_code,
                            report_date=report_date,
                            holder_name=holder_name[:100],
                            hold_amount=record.get('hold_amount'),
                            hold_ratio=record.get('hold_ratio'),
                            holder_rank=record.get('holder_rank', 0),
                            holder_type=holder_type_val
                        ).on_duplicate_key_update(
                            hold_amount=record.get('hold_amount'),
                            hold_ratio=record.get('hold_ratio')
                        )
                        session.execute(stmt)
                        saved += 1
                    except ImportError:
                        pass

                holder_num = record.get('holder_num') or record.get('holder_number')
                if holder_num:
                    try:
                        from models import StockShareholderCount
                        stmt = insert(StockShareholderCount).values(
                            ts_code=ts_code,
                            report_date=report_date,
                            holder_num=holder_num
                        ).on_duplicate_key_update(
                            holder_num=holder_num
                        )
                        session.execute(stmt)
                    except ImportError:
                        pass

            session.commit()

        except Exception as e:
            session.rollback()
            logger.debug(f"保存 {ts_code} 股东数据失败: {e}")

        finally:
            session.close()

        return saved