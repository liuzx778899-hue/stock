"""
股票历史日K线数据下载模块
支持多线程加速、增量更新、多数据源自动降级
"""
import pandas as pd
from datetime import datetime, date, timedelta
from typing import List, Optional, Tuple, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.dialects.mysql import insert

from config import config
from models import Base, StockDailyKline, StockBasic, CollectLog
from utils import logger, retry, RateLimiter, chunk_list, TaskStoppedException
from data_source import data_source_adapter


class StockDailyKlineCollector:
    """股票历史日K线数据采集器"""

    def __init__(self, engine=None, thread_pool_size: int = None):
        """
        初始化采集器

        Args:
            engine: SQLAlchemy 引擎
            thread_pool_size: 线程池大小
        """
        if engine is None:
            self.engine = create_engine(
                config.database.connection_url,
                pool_size=config.database.pool_size,
                max_overflow=config.database.max_overflow,
                pool_timeout=config.database.pool_timeout,
                pool_pre_ping=True
            )
        else:
            self.engine = engine

        self.Session = sessionmaker(bind=self.engine)
        self.thread_pool_size = thread_pool_size or config.collector.thread_pool_size
        self.rate_limiter = RateLimiter(config.collector.request_delay)

    def create_table(self):
        """创建数据表"""
        Base.metadata.create_all(self.engine)
        logger.info("K线数据表创建/检查完成")

    def get_stock_list(self) -> List[str]:
        """
        从数据库获取所有股票代码列表

        Returns:
            股票代码列表（ts_code格式）
        """
        session = self.Session()
        try:
            stocks = session.query(StockBasic.ts_code).filter(
                StockBasic.list_status == 'L'
            ).all()
            return [s[0] for s in stocks]
        finally:
            session.close()

    @retry(max_retries=3, exceptions=(Exception,))
    def fetch_single_stock_kline(
        self,
        ts_code: str,
        start_date: str,
        end_date: str,
        adjust: str = 'qfq'
    ) -> Optional[pd.DataFrame]:
        """
        获取单只股票的历史K线数据（支持多数据源自动降级）

        Args:
            ts_code: 股票代码（如 000001.SZ）
            start_date: 开始日期（如 20230101）
            end_date: 结束日期（如 20231231）
            adjust: 复权类型 qfq-前复权 hfq-后复权 空-不复权

        Returns:
            K线数据 DataFrame
        """
        # 解析股票代码
        symbol = ts_code.split('.')[0]

        self.rate_limiter.wait()

        # 使用数据源适配器获取数据（自动降级）
        df = data_source_adapter.fetch_kline_with_fallback(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            adjust=adjust
        )

        if df is None or df.empty:
            logger.warning(f"股票 {ts_code} 在 {start_date}-{end_date} 期间无数据")
            return None

        df['ts_code'] = ts_code
        return df

    def transform_kline_data(self, df: pd.DataFrame, ts_code: str) -> List[dict]:
        """
        转换K线数据格式

        Args:
            df: 原始K线数据
            ts_code: 股票代码

        Returns:
            转换后的数据列表
        """
        if df is None or df.empty:
            return []

        records = []

        for _, row in df.iterrows():
            record = {
                'ts_code': ts_code,
                'trade_date': self._parse_date(row.get('日期', row.get('date', None))),
                'open': row.get('开盘', row.get('open', None)),
                'high': row.get('最高', row.get('high', None)),
                'low': row.get('最低', row.get('low', None)),
                'close': row.get('收盘', row.get('close', None)),
                'pre_close': row.get('昨收', row.get('pre_close', None)),
                'volume': row.get('成交量', row.get('volume', None)),
                'amount': row.get('成交额', row.get('amount', None)),
                'turnover_rate': row.get('换手率', row.get('turnover', None)),
                'pct_chg': row.get('涨跌幅', row.get('pct_chg', None)),
            }

            # 处理 None 值
            if record['trade_date'] is not None:
                records.append(record)

        return records

    def _parse_date(self, date_val) -> Optional[date]:
        """解析日期"""
        if pd.isna(date_val) or date_val is None:
            return None
        try:
            if isinstance(date_val, str):
                # 尝试多种格式
                for fmt in ['%Y-%m-%d', '%Y%m%d']:
                    try:
                        return datetime.strptime(date_val, fmt).date()
                    except:
                        continue
            elif isinstance(date_val, datetime):
                return date_val.date()
            elif isinstance(date_val, date):
                return date_val
        except:
            pass
        return None

    def save_kline_batch(self, records: List[dict], batch_size: int = 500) -> int:
        """
        批量保存K线数据（UPSERT）

        Args:
            records: K线数据列表
            batch_size: 批量提交大小

        Returns:
            保存的记录数
        """
        if not records:
            return 0

        total_saved = 0
        session = self.Session()
        try:
            # 按 batch_size 分批提交
            for i in range(0, len(records), batch_size):
                batch = records[i:i + batch_size]

                stmt = insert(StockDailyKline).values(batch)
                update_dict = {
                    'open': stmt.inserted.open,
                    'high': stmt.inserted.high,
                    'low': stmt.inserted.low,
                    'close': stmt.inserted.close,
                    'pre_close': stmt.inserted.pre_close,
                    'volume': stmt.inserted.volume,
                    'amount': stmt.inserted.amount,
                    'turnover_rate': stmt.inserted.turnover_rate,
                    'pct_chg': stmt.inserted.pct_chg,
                    'updated_at': datetime.now(),
                }
                stmt = stmt.on_duplicate_key_update(**update_dict)

                session.execute(stmt)
                session.commit()
                total_saved += len(batch)

            return total_saved

        except Exception as e:
            session.rollback()
            logger.error(f"保存K线数据失败: {e}")
            raise
        finally:
            session.close()

    def collect_single_stock(
        self,
        ts_code: str,
        start_date: str,
        end_date: str
    ) -> Tuple[str, int, str]:
        """
        采集单只股票的K线数据

        Args:
            ts_code: 股票代码
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            (股票代码, 采集数量, 错��信息)
        """
        try:
            df = self.fetch_single_stock_kline(ts_code, start_date, end_date)
            if df is None or df.empty:
                return (ts_code, 0, "无数据")

            records = self.transform_kline_data(df, ts_code)
            count = self.save_kline_batch(records)

            return (ts_code, count, "")

        except Exception as e:
            return (ts_code, 0, str(e))

    def collect(
        self,
        start_date: str,
        end_date: str,
        stock_list: List[str] = None,
        batch_size: int = 50,
        show_progress: bool = True,
        progress_callback: Callable = None
    ) -> dict:
        """
        多线程采集所有股票的历史K线数据

        Args:
            start_date: 开始日期（如 20230101）
            end_date: 结束日期（如 20231231）
            stock_list: 股票代码列表，如果为 None 则从数据库获取
            batch_size: 批量保存大小
            show_progress: 是否显示进度
            progress_callback: 进度回调函数，签名 callback(completed, total, stats)

        Returns:
            采集结果统计
        """
        from datetime import datetime
        start_time = datetime.now()
        task_name = f"kline_{start_date}_{end_date}_{start_time.strftime('%H%M%S')}"

        # 确保表存在
        self.create_table()

        # 获取股票列表
        if stock_list is None:
            stock_list = self.get_stock_list()

        total_stocks = len(stock_list)
        logger.info(f"开始采集 {total_stocks} 只股票的K线数据，时间范围: {start_date} - {end_date}")

        # 结果统计
        stats = {
            'total': total_stocks,
            'success': 0,
            'failed': 0,
            'no_data': 0,
            'total_records': 0,
            'errors': []
        }

        try:
            completed = 0

            # 多线程采集
            with ThreadPoolExecutor(max_workers=self.thread_pool_size) as executor:
                futures = {
                    executor.submit(
                        self.collect_single_stock,
                        ts_code,
                        start_date,
                        end_date
                    ): ts_code for ts_code in stock_list
                }

                for future in as_completed(futures):
                    ts_code, count, error = future.result()
                    completed += 1

                    if error:
                        if error == "无数据":
                            stats['no_data'] += 1
                        else:
                            stats['failed'] += 1
                            stats['errors'].append((ts_code, error))
                            logger.warning(f"股票 {ts_code} 采集失败: {error}")
                    else:
                        stats['success'] += 1
                        stats['total_records'] += count

                    # 显示进度
                    if show_progress and completed % 100 == 0:
                        logger.info(f"进度: {completed}/{total_stocks} "
                                    f"({completed*100/total_stocks:.1f}%), "
                                    f"已采集 {stats['total_records']} 条记录")

                    # 调用进度回调
                    if progress_callback:
                        try:
                            progress_callback(completed, total_stocks, stats)
                        except TaskStoppedException:
                            raise  # 不吞掉停止信号，向上传播
                        except Exception as e:
                            logger.warning(f"进度回调失败: {e}")

            logger.info(f"K线数据采集完成 - 成功: {stats['success']}, "
                        f"失败: {stats['failed']}, 无数据: {stats['no_data']}, "
                        f"总记录数: {stats['total_records']}")

            # 记录采集日志
            self._save_collect_log(
                task_name, 'kline', start_time,
                stats['success'] + stats['no_data'],
                stats['failed'],
                'success'
            )

        except Exception as e:
            # 记录失败日志
            self._save_collect_log(
                task_name, 'kline', start_time,
                0, 0, 'failed', str(e)
            )
            raise

        return stats

    def _save_collect_log(self, task_name: str, task_type: str,
                          start_time, success_count: int, failed_count: int,
                          status: str, error_msg: str = None):
        """保存采集日志到 collect_log 表"""
        from datetime import datetime
        try:
            session = self.Session()
            try:
                log = CollectLog(
                    task_name=task_name,
                    task_type=task_type,
                    start_time=start_time,
                    end_time=datetime.now(),
                    total_count=success_count + failed_count,
                    success_count=success_count,
                    failed_count=failed_count,
                    status=status,
                    error_msg=error_msg
                )
                session.add(log)
                session.commit()
                logger.info(f"采集日志已保存: {task_name} ({status})")
            except Exception as e:
                session.rollback()
                logger.warning(f"保存采集日志失败: {e}")
            finally:
                session.close()
        except Exception as e:
            logger.warning(f"保存采集日志失败(连接异常): {e}")

    def collect_incremental(self, days: int = 30, progress_callback: Callable = None) -> dict:
        """
        增量采集最近N天的数据

        Args:
            days: 采集最近多少天的数据
            progress_callback: 进度回调函数

        Returns:
            采集结果统计
        """
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        return self.collect(
            start_date=start_date.strftime('%Y%m%d'),
            end_date=end_date.strftime('%Y%m%d'),
            progress_callback=progress_callback
        )


if __name__ == "__main__":
    # 单独运行测试
    collector = StockDailyKlineCollector(thread_pool_size=10)

    # 采集2023年全年数据
    stats = collector.collect(
        start_date='20230101',
        end_date='20231231'
    )

    print(f"采集完成: {stats}")