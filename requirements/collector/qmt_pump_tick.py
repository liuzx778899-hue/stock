#coding:gbk
"""
QMT 数据泵 - Tick明细数据（逐笔成交）
写入: stock_tick_data
"""
import pymysql
from datetime import datetime
import math

DB_CONFIG = {
    "host": "192.168.2.32",
    "port": 2881,
    "user": "root@hdw",
    "password": "Gongyue~@12345",
    "database": "astock",
    "charset": "utf8mb4",
}

START_DATE = "20250101"
END_DATE = "20251231"
COMMIT_INTERVAL = 5


def safe_float(val):
    if val is None: return None
    try:
        f = float(val)
        return None if math.isnan(f) else f
    except:
        return None


def safe_int(val):
    if val is None: return 0
    try:
        f = float(val)
        return 0 if math.isnan(f) else int(f)
    except:
        return 0


def get_checkpoint(db, pump_name):
    try:
        c = db.cursor()
        c.execute("SELECT current_index, total_count, last_code FROM qmt_pump_checkpoint WHERE pump_name = %s", (pump_name,))
        r = c.fetchone()
        if r:
            return {"current_index": r[0], "total_count": r[1], "last_code": r[2]}
    except:
        pass
    try:
        c = db.cursor()
        c.execute("SELECT config_value FROM system_config WHERE config_key = %s", (pump_name,))
        r = c.fetchone()
        if r:
            return {"current_index": int(r[0]), "total_count": 0, "last_code": ""}
    except:
        pass
    return {"current_index": 0, "total_count": 0, "last_code": ""}


def save_checkpoint(db, pump_name, current_index, total_count, last_code, status="running"):
    try:
        c = db.cursor()
        c.execute("""INSERT INTO qmt_pump_checkpoint (pump_name, current_index, total_count, last_code, status, updated_at)
            VALUES (%s,%s,%s,%s,%s,NOW())
            ON DUPLICATE KEY UPDATE current_index=%s, total_count=%s, last_code=%s, status=%s, updated_at=NOW()""",
            (pump_name, current_index, total_count, last_code, status, current_index, total_count, last_code, status))
        db.commit()
    except:
        c = db.cursor()
        c.execute("INSERT INTO system_config (config_key, config_value, updated_at) VALUES (%s,%s,NOW()) ON DUPLICATE KEY UPDATE config_value=%s, updated_at=NOW()",
            (pump_name, str(current_index), str(current_index)))
        db.commit()


def init(ContextInfo):
    print("=" * 60)
    print("QMT Tick数据泵（逐笔成交）")
    print("=" * 60)

    try:
        db = pymysql.connect(**DB_CONFIG)
        print("[OK] DB")
    except Exception as e:
        print("[FATAL] DB: " + str(e))
        return

    try:
        all_stocks = ContextInfo.get_stock_list_in_sector("沪深A股")
        total = len(all_stocks)
        print("[OK] " + str(total) + " stocks")
    except Exception as e:
        print("[FATAL]: " + str(e))
        db.close()
        return

    cp = get_checkpoint(db, "qmt_pump_tick")
    from_idx = cp["current_index"]
    print("[OK] resume from " + str(from_idx + 1))

    stocks = all_stocks[from_idx:]
    print("Processing " + str(len(stocks)) + " stocks (" + START_DATE + " ~ " + END_DATE + ")")
    print("-" * 40)

    ok = fail = skip = 0
    start = datetime.now()

    SQL_TICK = """INSERT INTO stock_tick_data
        (ts_code, trade_time, price, volume, amount, trade_type, created_at)
        VALUES (%s,%s,%s,%s,%s,%s,NOW())
        ON DUPLICATE KEY UPDATE
        price=VALUES(price),volume=VALUES(volume),amount=VALUES(amount),trade_type=VALUES(trade_type)"""

    for i, code in enumerate(stocks):
        real_idx = from_idx + i + 1
        pct = real_idx * 100 // total

        try:
            ret = ContextInfo.download_history_data(code, "tick", START_DATE, END_DATE)
            if ret != 0:
                skip += 1
                continue
        except:
            fail += 1
            continue

        try:
            tick_data = ContextInfo.get_market_data_ex(
                [], [code], period="tick",
                start_time=START_DATE, end_time=END_DATE,
                count=-1
            )
        except:
            skip += 1
            continue

        if tick_data is None or not isinstance(tick_data, dict) or len(tick_data) == 0:
            skip += 1
            continue

        df = list(tick_data.values())[0]
        if df is None or (hasattr(df, "empty") and df.empty):
            skip += 1
            continue

        cnt = 0
        cur = db.cursor()
        try:
            for idx_i, row in df.iterrows():
                trade_time = str(row.get("time", idx_i))
                if len(trade_time) > 8:
                    trade_time = trade_time[:8]
                cur.execute(SQL_TICK, (
                    code, trade_time,
                    safe_float(row.get("price")),
                    safe_int(row.get("volume")),
                    safe_float(row.get("amount")),
                    str(row.get("trade_type", ""))
                ))
                cnt += 1
        except Exception as e:
            fail += 1
            continue

        elapsed = (datetime.now() - start).total_seconds()
        avg = elapsed / (i + 1) if i > 0 else 0
        remain = int((len(stocks) - i - 1) * avg / 60)
        print("[" + str(pct) + "%] " + str(real_idx) + "/" + str(total) + " " + code + " T(" + str(cnt) + ") ETA" + str(remain) + "m")
        ok += 1

        if (i + 1) % COMMIT_INTERVAL == 0:
            db.commit()
            save_checkpoint(db, "qmt_pump_tick", real_idx, total, code)

    db.commit()
    save_checkpoint(db, "qmt_pump_tick", total, total, "", "completed")
    db.close()

    t = int((datetime.now() - start).total_seconds() / 60)
    print("=" * 60)
    print("DONE! OK=" + str(ok) + " SKIP=" + str(skip) + " FAIL=" + str(fail) + " TIME=" + str(t) + "m")
    print("=" * 60)


def handlebar(ContextInfo):
    pass