#coding:gbk
"""
QMT 数据泵 - 股东数据（十大股东/流通股东/股东户数）
写入: stock_shareholder_top10, stock_shareholder_count
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
COMMIT_INTERVAL = 10


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
    print("QMT 股东数据泵")
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

    cp = get_checkpoint(db, "qmt_pump_shareholder")
    from_idx = cp["current_index"]
    print("[OK] resume from " + str(from_idx + 1))

    stocks = all_stocks[from_idx:]
    print("Processing " + str(len(stocks)) + " stocks (" + START_DATE + " ~ " + END_DATE + ")")
    print("-" * 40)

    ok = fail = skip = 0
    start = datetime.now()

    SQL_TOP10 = """INSERT INTO stock_shareholder_top10
        (ts_code, report_date, holder_name, hold_amount, hold_ratio, holder_rank, holder_type, created_at, updated_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,NOW(),NOW())
        ON DUPLICATE KEY UPDATE
        hold_amount=VALUES(hold_amount),hold_ratio=VALUES(hold_ratio),updated_at=NOW()"""

    SQL_COUNT = """INSERT INTO stock_shareholder_count
        (ts_code, report_date, holder_num, created_at, updated_at)
        VALUES (%s,%s,%s,NOW(),NOW())
        ON DUPLICATE KEY UPDATE holder_num=VALUES(holder_num),updated_at=NOW()"""

    for i, code in enumerate(stocks):
        real_idx = from_idx + i + 1
        pct = real_idx * 100 // total

        top10_cnt = flow_cnt = count_cnt = 0
        cur = db.cursor()

        try:
            top10_df = ContextInfo.get_top10_share_holder([code], "holder", START_DATE, END_DATE)
            if top10_df is not None and hasattr(top10_df, "iterrows"):
                for idx_i, row in top10_df.iterrows():
                    try:
                        report_date = str(row.get("report_date", ""))[:10]
                    except:
                        continue
                    if not report_date:
                        continue
                    cur.execute(SQL_TOP10, (
                        code, report_date,
                        str(row.get("holder_name", ""))[:100],
                        safe_float(row.get("hold_amount")),
                        safe_float(row.get("hold_ratio")),
                        safe_int(row.get("holder_rank", idx_i + 1)),
                        "holder"
                    ))
                    top10_cnt += 1
        except:
            pass

        try:
            flow_df = ContextInfo.get_top10_share_holder([code], "flow_holder", START_DATE, END_DATE)
            if flow_df is not None and hasattr(flow_df, "iterrows"):
                for idx_i, row in flow_df.iterrows():
                    try:
                        report_date = str(row.get("report_date", ""))[:10]
                    except:
                        continue
                    if not report_date:
                        continue
                    cur.execute(SQL_TOP10, (
                        code, report_date,
                        str(row.get("holder_name", ""))[:100],
                        safe_float(row.get("hold_amount")),
                        safe_float(row.get("hold_ratio")),
                        safe_int(row.get("holder_rank", idx_i + 1)),
                        "flow_holder"
                    ))
                    flow_cnt += 1
        except:
            pass

        try:
            count_df = ContextInfo.get_holder_num([code], START_DATE, END_DATE)
            if count_df is not None and hasattr(count_df, "iterrows"):
                for idx_i, row in count_df.iterrows():
                    try:
                        report_date = str(row.get("report_date", row.get("ann_date", "")))[:10]
                    except:
                        continue
                    if not report_date:
                        continue
                    cur.execute(SQL_COUNT, (
                        code, report_date,
                        safe_int(row.get("holder_num", row.get("holder_number", 0)))
                    ))
                    count_cnt += 1
        except:
            pass

        if top10_cnt == 0 and flow_cnt == 0 and count_cnt == 0:
            skip += 1
            continue

        elapsed = (datetime.now() - start).total_seconds()
        avg = elapsed / (i + 1) if i > 0 else 0
        remain = int((len(stocks) - i - 1) * avg / 60)
        print("[" + str(pct) + "%] " + str(real_idx) + "/" + str(total) + " " + code +
              " T(" + str(top10_cnt) + ")F(" + str(flow_cnt) + ")C(" + str(count_cnt) + ") ETA" + str(remain) + "m")
        ok += 1

        if (i + 1) % COMMIT_INTERVAL == 0:
            db.commit()
            save_checkpoint(db, "qmt_pump_shareholder", real_idx, total, code)

    db.commit()
    save_checkpoint(db, "qmt_pump_shareholder", total, total, "", "completed")
    db.close()

    t = int((datetime.now() - start).total_seconds() / 60)
    print("=" * 60)
    print("DONE! OK=" + str(ok) + " SKIP=" + str(skip) + " FAIL=" + str(fail) + " TIME=" + str(t) + "m")
    print("=" * 60)


def handlebar(ContextInfo):
    pass
