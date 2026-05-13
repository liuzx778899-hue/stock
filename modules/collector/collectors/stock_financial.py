"""
财务数据采集器

采集利润表/资产负债表/现金流量表/每股指标
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


class StockFinancialCollector(BaseCollector):
    """财务数据采集器

    采集四大财务表：
    - 利润表 (income)
    - 资产负债表 (balance)
    - 现金流量表 (cashflow)
    - 每股指标 (per_share)
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
        report_type: str = "all",
        progress_callback: Callable[[int, int, str], None] = None,
        stop_check: Callable[[], bool] = None
    ) -> Dict[str, Any]:
        """
        执行财务数据采集

        Args:
            start_date: 开始日期（报告期）
            end_date: 结束日期
            symbols: 票代码列表，None 则采集全部
            report_type: 报表类型 (income/balance/cashflow/per_share/all)
            progress_callback: 进度回调
            stop_check: 停止检查函数

        Returns:
            采集结果字典
        """
        log_entry = self._create_log_entry("财务数据采集", "financial")

        try:
            if symbols is None:
                symbols = self._get_stock_list()

            if not symbols:
                raise Exception("股票列表为空")

            if end_date is None:
                end_date = datetime.now().strftime('%Y%m%d')
            if start_date is None:
                start_date = (datetime.now() - timedelta(days=365*3)).strftime('%Y%m%d')

            logger.info(f"开始采集 {len(symbols)} 只股票的财务数据 ({start_date} ~ {end_date})")

            results = self._collect_parallel(
                symbols, start_date, end_date, report_type,
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
            logger.error(f"财务数据采集失败: {e}")
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
        report_type: str,
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
                    symbol, start_date, end_date, report_type, stop_check
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
                    logger.debug(f"{symbol} 财务数据采集失败: {e}")

                finally:
                    completed += 1
                    if progress_callback:
                        pct = int(completed / total * 100)
                        progress_callback(completed, total, f"采集财务数据 {pct}%")

        return results

    def _collect_single(
        self,
        ts_code: str,
        start_date: str,
        end_date: str,
        report_type: str,
        stop_check: Callable
    ) -> Dict:
        """采集单只股票财务数据"""
        if stop_check and stop_check():
            raise TaskStoppedException()

        saved = 0
        data = {"ts_code": ts_code, "saved": 0}

        try:
            df = self.orchestrator.collect_financial(ts_code, start_date, end_date, report_type)
            if df is not None and not df.empty:
                saved = self._save_financial(ts_code, df, report_type)
                data["saved"] = saved
        except AttributeError:
            logger.warning(f"orchestrator.collect_financial 方法尚未实现（等待 develop1 Phase 3）")
        except Exception as e:
            logger.debug(f"{ts_code} 财务采集失败: {e}")

        return data

    def _save_financial(self, ts_code: str, df: pd.DataFrame, report_type: str) -> int:
        """保存财务数据

        注意：需要 develop1 完成 Phase 1（创建表模型）后才能保存
        """
        if df is None or df.empty:
            return 0

        df = FieldMerger.normalize_columns(df)
        saved = 0

        try:
            session = self.Session()
            records = df.to_dict('records')

            for record in records:
                report_date = record.get('report_date') or record.get('ann_date')
                if report_date is None:
                    continue

                if hasattr(report_date, 'strftime'):
                    report_date = report_date.strftime('%Y%m%d')
                elif isinstance(report_date, str):
                    report_date = report_date.replace('-', '')[:8]

                # 尝试保存到对应的财务表
                # 这些表需要 develop1 在 Phase 1 创建
                try:
                    if report_type == "income" or report_type == "all":
                        from models import StockFinancialIncome
                        stmt = insert(StockFinancialIncome).values(
                            ts_code=ts_code,
                            report_date=report_date,
                            operating_revenue=record.get('operating_revenue'),
                            operating_cost=record.get('operating_cost'),
                            oper_profit=record.get('oper_profit'),
                            net_profit=record.get('net_profit'),
                            basic_eps=record.get('basic_eps')
                        ).on_duplicate_key_update(
                            operating_revenue=record.get('operating_revenue'),
                            operating_cost=record.get('operating_cost'),
                            oper_profit=record.get('oper_profit'),
                            net_profit=record.get('net_profit'),
                            basic_eps=record.get('basic_eps')
                        )
                        session.execute(stmt)
                        saved += 1
                except ImportError:
                    pass

                try:
                    if report_type == "balance" or report_type == "all":
                        from models import StockFinancialBalance
                        stmt = insert(StockFinancialBalance).values(
                            ts_code=ts_code,
                            report_date=report_date,
                            total_assets=record.get('total_assets'),
                            total_liabilities=record.get('total_liabilities'),
                            total_equity=record.get('total_equity')
                        ).on_duplicate_key_update(
                            total_assets=record.get('total_assets'),
                            total_liabilities=record.get('total_liabilities'),
                            total_equity=record.get('total_equity')
                        )
                        session.execute(stmt)
                except ImportError:
                    pass

                try:
                    if report_type == "cashflow" or report_type == "all":
                        from models import StockFinancialCashflow
                        stmt = insert(StockFinancialCashflow).values(
                            ts_code=ts_code,
                            report_date=report_date,
                            net_cash_oper=record.get('net_cash_flows_oper_act'),
                            net_cash_inv=record.get('net_cash_flows_inv_act'),
                            net_cash_fin=record.get('net_cash_flows_fin_act')
                        ).on_duplicate_key_update(
                            net_cash_oper=record.get('net_cash_flows_oper_act'),
                            net_cash_inv=record.get('net_cash_flows_inv_act'),
                            net_cash_fin=record.get('net_cash_flows_fin_act')
                        )
                        session.execute(stmt)
                except ImportError:
                    pass

            session.commit()
        except Exception as e:
            logger.debug(f"保存 {ts_code} 财务数据失败: {e}")
            if 'session' in dir():
                session.rollback()

        return saved