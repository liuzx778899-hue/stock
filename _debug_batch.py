"""Debug: reproduce the mass collection error"""
import sys
sys.path.insert(0, '.')
import pandas as pd
from collectors.stock_daily import StockDailyKlineCollector
from utils import logger

try:
    collector = StockDailyKlineCollector()
    # Test with just 5 stocks
    symbols = ['000001.SZ', '000002.SZ', '000003.SZ', '000004.SZ', '000005.SZ']
    result = collector.collect(
        start_date='20260426',
        end_date='20260503',
        symbols=symbols
    )
    print(f'Result: {result}')
except Exception as e:
    import traceback
    print(f'Error: {e}')
    traceback.print_exc()
