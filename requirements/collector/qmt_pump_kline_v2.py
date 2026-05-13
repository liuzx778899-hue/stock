#coding:gbk
"""
QMT 数据泵 v2 - K线+换手率+股本+市值
写入: stock_daily_kline (已有) + stock_daily_basic (新表)
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

START_DATE = "20200101"
END_DATE = "20251231"
COMMIT_INTERVAL = 20

QMT_FIELDS = ["open", "high", "low", "close", "volume", "amount", "preClose"]


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
    print("QMT K线+换手率+股本 数据泵 v2")
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

    cp = get_checkpoint(db, "qmt_pump_kline_v2")
    from_idx = cp["current_index"]
    print("[OK] resume from " + str(from_idx + 1))

    stocks = all_stocks[from_idx:]
    print("Processing " + str(len(stocks)) + " stocks (" + START_DATE + " ~ " + END_DATE + ")")
    print("-" * 40)

    ok = fail = skip = 0
    start = datetime.now()

    SQL_KLINE = """INSERT INTO stock_daily_kline
        (ts_code, trade_date, open, high, low, close, pre_close,
         volume, amount, pct_chg, turnover_rate, created_at, updated_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW(),NOW())
        ON DUPLICATE KEY UPDATE
        open=VALUES(open),high=VALUES(high),low=VALUES(low),
        close=VALUES(close),pre_close=VALUES(pre_close),
        volume=VALUES(volume),amount=VALUES(amount),
        pct_chg=VALUES(pct_chg),turnover_rate=VALUES(turnover_rate),
        updated_at=NOW()"""

    SQL_BASIC = """INSERT INTO stock_daily_basic
        (ts_code, trade_date, total_share, circ_share, total_mv, circ_mv, turnover_rate, created_at, updated_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,NOW(),NOW())
        ON DUPLICATE KEY UPDATE
        total_share=VALUES(total_share),circ_share=VALUES(circ_share),
        total_mv=VALUES(total_mv),circ_mv=VALUES(circ_mv),
        turnover_rate=VALUES(turnover_rate),updated_at=NOW()"""

    for i, code in enumerate(stocks):
        real_idx = from_idx + i + 1
        pct = real_idx * 100 // total

        try:
            data = ContextInfo.get_market_data_ex(
                QMT_FIELDS, [code], period="1d",
                start_time=START_DATE, end_time=END_DATE,
                dividend_type="front", count=-1,
            )
        except:
            fail += 1
            continue

        if data is None or not isinstance(data, dict) or len(data) == 0:
            skip += 1
            continue

        df = list(data.values())[0]
        if df is None or (hasattr(df, "empty") and df.empty):
            skip += 1
            continue

        try:
            total_share = ContextInfo.get_total_share(code)
        except:
            total_share = 0
        try:
            circ_share = ContextInfo.get_last_volume(code)
        except:
            circ_share = 0

        try:
            turnover_df = ContextInfo.get_turnover_rate([code], START_DATE, END_DATE)
            turnover_map = {}
            if turnover_df is not None and hasattr(turnover_df, "index"):
                for idx_i, dt in enumerate(turnover_df.index):
                    ts = str(dt)
                    if len(ts) >= 8:
                        td = ts[:4] + "-" + ts[4:6] + "-" + ts[6:8]
                        try:
                            turnover_map[td] = safe_float(turnover_df.iloc[idx_i].get("TURNOVERRATE", turnover_df.iloc[idx_i].get("turnover_rate", None)))
                        except:
                            pass
        except:
            turnover_map = {}

        cnt_kline = cnt_basic = 0
        cur = db.cursor()
        try:
            for idx_i, dt in enumerate(df.index):
                ts = str(dt)
                if len(ts) >= 8:
                    td = ts[:4] + "-" + ts[6:8] + "-" + ts[4:6]
                else:
                    continue
                o = safe_float(df.iloc[idx_i]["open"])
                h = safe_float(df.iloc[idx_i]["high"])
                l = safe_float(df.iloc[idx_i]["low"])
                c = safe_float(df.iloc[idx_i]["close"])
                pc = safe_float(df.iloc[idx_i]["preClose"])
                v = safe_int(df.iloc[idx_i]["volume"])
                a = safe_float(df.iloc[idx_i]["amount"])
                pct_chg = round((c - pc) / pc * 100, 4) if c and pc and pc != 0 else None

                tr = turnover_map.get(td, None)

                cur.execute(SQL_KLINE, (code, td, o, h, l, c, pc, v, a, pct_chg, tr))
                cnt_kline += 1

                if total_share > 0 and c:
                    total_mv = total_share * c / 100000000
                    circ_mv = circ_share * c / 100000000 if circ_share > 0 else None
                    cur.execute(SQL_BASIC, (code, td, total_share, circ_share, total_mv, circ_mv, tr))
                    cnt_basic += 1

        except Exception as e:
            fail += 1
            continue

        elapsed = (datetime.now() - start).total_seconds()
        avg = elapsed / (i + 1) if i > 0 else 0
        remain = int((len(stocks) - i - 1) * avg / 60)
        print("[" + str(pct) + "%] " + str(real_idx) + "/" + str(total) + " " + code + " K(" + str(cnt_kline) + ")B(" + str(cnt_basic) + ") ETA" + str(remain) + "m")
        ok += 1

        if (i + 1) % COMMIT_INTERVAL == 0:
            db.commit()
            save_checkpoint(db, "qmt_pump_kline_v2", real_idx, total, code)

    db.commit()
    save_checkpoint(db, "qmt_pump_kline_v2", total, total, "", "completed")
    db.close()

    t = int((datetime.now() - start).total_seconds() / 60)
    print("=" * 60)
    print("DONE! OK=" + str(ok) + " SKIP=" + str(skip) + " FAIL=" + str(fail) + " TIME=" + str(t) + "m")
    print("=" * 60)


def handlebar(ContextInfo):
    pass
