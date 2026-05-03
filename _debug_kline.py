"""Debug script to test K-line collection"""
import sys
sys.path.insert(0, '.')
from services.data_orchestrator import orchestrator
import pandas as pd

try:
    df = orchestrator.collect_kline('600141', '20260426', '20260503')
    print(f'Got DataFrame: type={type(df).__name__}')
    if isinstance(df, pd.DataFrame) and not df.empty:
        print(f'Columns: {list(df.columns)}')
        print(f'Rows: {len(df)}')
        print(df.head())

        # Try the save logic
        df2 = df.copy()
        if 'close' in df2.columns and 'pre_close' not in df2.columns:
            df2 = df2.sort_values('trade_date')
            df2['pre_close'] = df2['close'].shift(1)
            df2 = df2.sort_index()

        records = df2.to_dict('records')
        print(f'record type: {type(records[0]).__name__}')
        for r in records[:2]:
            print(f'  trade_date={r.get("trade_date")}, close={r.get("close")}, pre_close={r.get("pre_close")}')
        print('Save logic test passed!')
    elif isinstance(df, pd.DataFrame) and df.empty:
        print('Empty DataFrame returned')
    else:
        print(f'Unexpected return type: {type(df).__name__}')
except Exception as e:
    import traceback
    print(f'Error: {e}')
    traceback.print_exc()
