"""
主入口文件 - A股数据采集系统（重构版）

整合所有采集功能，提供统一调用接口
新架构：使用 collectors/ 模块的采集器
"""
import argparse
from datetime import datetime, timedelta
from typing import Callable, Optional, Dict, Any
from sqlalchemy import create_engine

from config import config
from models import Base
from utils import logger

# 新架构采集器
from modules.collector.collectors.stock_basic import StockBasicCollector
from modules.collector.collectors.stock_daily import StockDailyKlineCollector
from modules.collector.collectors.realtime_quote import RealtimeQuoteCollector


class StockDataCollector:
    """A股数据采集系统主类"""

    def __init__(self):
        """初始化采集系统（共享一个数据库引擎）"""
        self.engine = create_engine(
            config.database.connection_url,
            pool_size=config.database.pool_size,
            max_overflow=config.database.max_overflow,
            pool_timeout=config.database.pool_timeout,
            pool_pre_ping=True
        )
        # 所有采集器共享同一个引擎
        self.basic_collector = StockBasicCollector(engine=self.engine)
        self.kline_collector = StockDailyKlineCollector(engine=self.engine)
        self.realtime_collector = RealtimeQuoteCollector(engine=self.engine)

    def init_database(self):
        """初始化数据库，创建所有表"""
        logger.info("初始化数据库...")
        Base.metadata.create_all(self.engine)
        logger.info("数据库初始化完成")

    def collect_stock_basic(
        self,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
        stop_check: Optional[Callable[[], bool]] = None
    ) -> Dict[str, Any]:
        """
        采集股票基础信息

        Args:
            progress_callback: 进度回调 (current, total, stage)
            stop_check: 停止检查函数

        Returns:
            采集结果字典
        """
        logger.info("开始采集股票基础信息...")
        result = self.basic_collector.collect(
            progress_callback=progress_callback,
            stop_check=stop_check
        )
        logger.info(f"股票基础信息采集完成: {result}")
        return result

    def collect_history_kline(
        self,
        start_date: str,
        end_date: str,
        thread_pool_size: Optional[int] = None,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
        stop_check: Optional[Callable[[], bool]] = None
    ) -> Dict[str, Any]:
        """
        采集历史K线数据

        Args:
            start_date: 开始日期（如 20230101）
            end_date: 结束日期（如 20231231）
            thread_pool_size: 线程池大小
            progress_callback: 进度回调
            stop_check: 停止检查函数

        Returns:
            采集统计结果
        """
        logger.info(f"开始采集历史K线数据，时间范围: {start_date} - {end_date}")

        if thread_pool_size:
            self.kline_collector.thread_pool_size = thread_pool_size

        result = self.kline_collector.collect(
            start_date=start_date,
            end_date=end_date,
            progress_callback=progress_callback,
            stop_check=stop_check
        )
        logger.info(f"历史K线数据采集完成: {result}")
        return result

    def collect_incremental_kline(
        self,
        days: int = 30,
        progress_callback: Optional[Callable] = None,
        stop_check: Optional[Callable[[], bool]] = None
    ) -> Dict[str, Any]:
        """
        增量采集最近N天的K线数据

        Args:
            days: 采集最近多少天的数据
            progress_callback: 进度回调
            stop_check: 停止检查函数

        Returns:
            采集统计结果
        """
        logger.info(f"开始增量采集最近 {days} 天的K线数据...")
        result = self.kline_collector.collect_incremental(
            days=days,
            progress_callback=progress_callback,
            stop_check=stop_check
        )
        logger.info(f"增量K线数据采集完成: {result}")
        return result

    def collect_realtime_quote(
        self,
        symbol: Optional[str] = None,
        progress_callback: Optional[Callable] = None,
        stop_check: Optional[Callable[[], bool]] = None
    ) -> Dict[str, Any]:
        """
        采集实时行情数据

        Args:
            symbol: 股票代码，None 表示全量
            progress_callback: 进度回调
            stop_check: 停止检查函数

        Returns:
            采集结果
        """
        logger.info(f"开始采集实时行情数据{'('+symbol+')' if symbol else '(全量)'}...")
        result = self.realtime_collector.collect(
            symbol=symbol,
            progress_callback=progress_callback,
            stop_check=stop_check
        )
        logger.info(f"实时行情采集完成: {result}")
        return result

    def full_collect(
        self,
        start_date: str,
        end_date: str,
        progress_callback: Optional[Callable] = None,
        stop_check: Optional[Callable[[], bool]] = None
    ):
        """
        全量采集：基础信息 + 历史K线

        Args:
            start_date: K线开始日期
            end_date: K线结束日期
            progress_callback: 进度回调
            stop_check: 停止检查函数
        """
        logger.info("========== 开始全量采集 ==========")

        # 1. 初始化数据库
        self.init_database()

        # 2. 采集股票基础信息
        self.collect_stock_basic(
            progress_callback=lambda c, t, s: progress_callback(1, 3, f"基础信息: {s}") if progress_callback else None,
            stop_check=stop_check
        )

        if stop_check and stop_check():
            logger.info("用户停止任务")
            return

        # 3. 采集历史K线数据
        self.collect_history_kline(
            start_date, end_date,
            progress_callback=lambda c, t, s: progress_callback(2, 3, f"K线数据: {s}") if progress_callback else None,
            stop_check=stop_check
        )

        logger.info("========== 全量采集完成 ==========")


def main():
    """命令行入口"""
    parser = argparse.ArgumentParser(description='A股数据采集系统')
    parser.add_argument('command', choices=[
        'init', 'basic', 'kline', 'incremental', 'realtime', 'full', 'quote'
    ], help='执行命令')
    parser.add_argument('--start-date', type=str, help='开始日期（如 20230101）')
    parser.add_argument('--end-date', type=str, help='结束日期（如 20231231）')
    parser.add_argument('--days', type=int, default=30, help='增量采集天数')
    parser.add_argument('--symbol', type=str, help='股票代码（获取单只行情）')
    parser.add_argument('--threads', type=int, default=10, help='线程池大小')
    parser.add_argument('--source', type=str, default='em', help='数据源（em/sina）')

    args = parser.parse_args()

    collector = StockDataCollector()

    try:
        if args.command == 'init':
            collector.init_database()

        elif args.command == 'basic':
            result = collector.collect_stock_basic()
            print(f"采集完成: {result}")

        elif args.command == 'kline':
            if not args.start_date or not args.end_date:
                print("错误: kline 命令需要 --start-date 和 --end-date 参数")
                return
            result = collector.collect_history_kline(
                args.start_date,
                args.end_date,
                args.threads
            )
            print(f"采集完成: {result}")

        elif args.command == 'incremental':
            result = collector.collect_incremental_kline(args.days)
            print(f"采集完成: {result}")

        elif args.command == 'realtime':
            result = collector.collect_realtime_quote(args.source)
            print(f"采集完成: {result}")

        elif args.command == 'full':
            if not args.start_date or not args.end_date:
                print("错误: full 命令需要 --start-date 和 --end-date 参数")
                return
            collector.full_collect(args.start_date, args.end_date)

        elif args.command == 'quote':
            if not args.symbol:
                print("错误: quote 命令需要 --symbol 参数")
                return
            result = collector.collect_realtime_quote(args.symbol)
            print(f"行情数据: {result}")

    except Exception as e:
        logger.error(f"执行失败: {e}")
        raise


if __name__ == "__main__":
    main()