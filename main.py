"""
主入口文件 - A股数据采集系统
整合所有采集功能，提供统一调用接口
"""
import argparse
from datetime import datetime, timedelta
from typing import Callable, Optional
from sqlalchemy import create_engine

from config import config
from models import Base
from utils import logger

# 采集器
from stock_basic import StockBasicCollector
from stock_daily import StockDailyKlineCollector
from realtime_quote import RealtimeQuoteCollector


class StockDataCollector:
    """A股数据采集系统主类"""

    def __init__(self):
        """初始化采集系统（共享一个数据库引擎）"""
        # 统一创建一个数据库引擎，避免资源浪费
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
        Base.metadata.create_all(self.basic_collector.engine)
        logger.info("数据库初始化完成")

    def collect_stock_basic(self, use_extended: bool = True, stop_check: Optional[Callable[[], bool]] = None) -> int:
        """
        采集股票基础信息

        Args:
            use_extended: 是否使用扩展接口获取详细信息
            stop_check: 停止检查回调函数，返回 True 表示应停止

        Returns:
            采集记录数
        """
        logger.info("开始采集股票基础信息...")
        count = self.basic_collector.collect(use_extended=use_extended, stop_check=stop_check)
        logger.info(f"股票基础信息采集完成，共 {count} 条")
        return count

    def collect_history_kline(
        self,
        start_date: str,
        end_date: str,
        thread_pool_size: Optional[int] = None
    ) -> dict:
        """
        采集历史K线数据

        Args:
            start_date: 开始日期（如 20230101）
            end_date: 结束日期（如 20231231）
            thread_pool_size: 线程池大小

        Returns:
            采集统计结果
        """
        logger.info(f"开始采集历史K线数据，时间范围: {start_date} - {end_date}")

        if thread_pool_size:
            self.kline_collector.thread_pool_size = thread_pool_size

        stats = self.kline_collector.collect(start_date, end_date)
        logger.info(f"历史K线数据采集完成: {stats}")
        return stats

    def collect_incremental_kline(self, days: int = 30) -> dict:
        """
        增量采集最近N天的K线数据

        Args:
            days: 采集最近多少天的数据

        Returns:
            采集统计结果
        """
        logger.info(f"开始增量采集最近 {days} 天的K线数据...")
        stats = self.kline_collector.collect_incremental(days=days)
        logger.info(f"增量K线数据采集完成: {stats}")
        return stats

    def collect_realtime_quote(self, source: str = 'em') -> dict:
        """
        采集实时行情数据

        Args:
            source: 数据源 'em'-东方财富 'sina'-新浪

        Returns:
            采集结果
        """
        logger.info(f"开始采集实时行情数据，数据源: {source}")
        stats = self.realtime_collector.collect(source=source)
        logger.info(f"实时行情采集完成: {stats}")
        return stats

    def get_realtime_quote(self, symbol: str) -> Optional[dict]:
        """
        获取单只股票实时行情

        Args:
            symbol: 股票代码

        Returns:
            实时行情字典
        """
        return self.realtime_collector.get_realtime_quote(symbol)

    def full_collect(self, start_date: str, end_date: str):
        """
        全量采集：基础信息 + 历史K线

        Args:
            start_date: K线开始日期
            end_date: K线结束日期
        """
        logger.info("========== 开始全量采集 ==========")

        # 1. 初始化数据库
        self.init_database()

        # 2. 采集股票基础信息
        self.collect_stock_basic()

        # 3. 采集历史K线数据
        self.collect_history_kline(start_date, end_date)

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
            collector.collect_stock_basic()

        elif args.command == 'kline':
            if not args.start_date or not args.end_date:
                print("错误: kline 命令需要 --start-date 和 --end-date 参数")
                return
            collector.collect_history_kline(
                args.start_date,
                args.end_date,
                args.threads
            )

        elif args.command == 'incremental':
            collector.collect_incremental_kline(args.days)

        elif args.command == 'realtime':
            collector.collect_realtime_quote(args.source)

        elif args.command == 'full':
            if not args.start_date or not args.end_date:
                print("错误: full 命令需要 --start-date 和 --end-date 参数")
                return
            collector.full_collect(args.start_date, args.end_date)

        elif args.command == 'quote':
            if not args.symbol:
                print("错误: quote 命令需要 --symbol 参数")
                return
            quote = collector.get_realtime_quote(args.symbol)
            if quote:
                print(f"\n股票: {quote['name']} ({quote['symbol']})")
                print(f"当前价: {quote['price']}")
                print(f"今开: {quote['open']}")
                print(f"最高: {quote['high']}")
                print(f"最低: {quote['low']}")
                print(f"昨收: {quote['pre_close']}")
                print(f"涨跌幅: {quote['pct_chg']}%")
                print(f"更新时间: {quote['update_time']}")
            else:
                print(f"未找到股票 {args.symbol} 的行情数据")

    except Exception as e:
        logger.error(f"执行失败: {e}")
        raise


if __name__ == "__main__":
    main()