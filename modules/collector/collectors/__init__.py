"""
采集器模块

包含 BaseCollector 基类和具体采集器实现
"""
from modules.collector.collectors.base import BaseCollector
from modules.collector.collectors.stock_basic import StockBasicCollector
from modules.collector.collectors.stock_daily import StockDailyKlineCollector
from modules.collector.collectors.realtime_quote import RealtimeQuoteCollector
from modules.collector.collectors.stock_financial import StockFinancialCollector
from modules.collector.collectors.stock_shareholder import StockShareholderCollector
from modules.collector.collectors.stock_daily_basic import StockDailyBasicCollector

__all__ = [
    'BaseCollector',
    'StockBasicCollector',
    'StockDailyKlineCollector',
    'RealtimeQuoteCollector',
    'StockFinancialCollector',
    'StockShareholderCollector',
    'StockDailyBasicCollector',
]