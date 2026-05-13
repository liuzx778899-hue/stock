#coding:gbk
"""
QMT 数据泵 - 基础数据（ST状态/IPO信息/行业）
写入: stock_st_status, stock_ipo_info, 更新 stock_basic.industry
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

COMMIT_INTERVAL = 20


def safe_float(val):
    if val is None: return None
    try:
        f = float(val)
        return None if math.isnan(f) else f
    except:
        return None


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
    print("QMT 基础数据泵（ST/IPO/行业）")
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

    cp = get_checkpoint(db, "qmt_pump_basic")
    from_idx = cp["current_index"]
    print("[OK] resume from " + str(from_idx + 1))

    stocks = all_stocks[from_idx:]
    print("Processing " + str(len(stocks)) + " stocks")
    print("-" * 40)

    ok = fail = skip = 0
    start = datetime.now()

    SQL_ST = """INSERT INTO stock_st_status
        (ts_code, st_type, is_st, start_date, end_date, created_at, updated_at)
        VALUES (%s,%s,%s,%s,%s,NOW(),NOW())
        ON DUPLICATE KEY UPDATE
        st_type=VALUES(st_type),is_st=VALUES(is_st),
        start_date=VALUES(start_date),end_date=VALUES(end_date),updated_at=NOW()"""

    SQL_IPO = """INSERT INTO stock_ipo_info
        (ts_code, ipo_date, issue_price, issue_amount, raise_amount, created_at, updated_at)
        VALUES (%s,%s,%s,%s,%s,NOW(),NOW())
        ON DUPLICATE KEY UPDATE
        ipo_date=VALUES(ipo_date),issue_price=VALUES(issue_price),
        issue_amount=VALUES(issue_amount),raise_amount=VALUES(raise_amount),updated_at=NOW()"""

    SQL_BASIC = """UPDATE stock_basic SET industry = %s, updated_at = NOW() WHERE ts_code = %s"""

    for i, code in enumerate(stocks):
        real_idx = from_idx + i + 1
        pct = real_idx * 100 // total

        st_cnt = ipo_cnt = ind_cnt = 0
        cur = db.cursor()

        try:
            st_info = ContextInfo.get_st_status(code)
            if st_info and isinstance(st_info, dict):
                st_type = st_info.get("st_type", "")
                is_st = 1 if st_info.get("is_st", False) else 0
                start_date = st_info.get("start_date", None)
                end_date = st_info.get("end_date", None)
                cur.execute(SQL_ST, (code, st_type, is_st, start_date, end_date))
                st_cnt = 1
        except:
            pass

        try:
            ipo_info = ContextInfo.get_ipo_data(code)
            if ipo_info and isinstance(ipo_info, dict):
                ipo_date = ipo_info.get("ipo_date", None)
                issue_price = safe_float(ipo_info.get("issue_price"))
                issue_amount = safe_float(ipo_info.get("issue_amount"))
                raise_amount = safe_float(ipo_info.get("raise_amount"))
                cur.execute(SQL_IPO, (code, ipo_date, issue_price, issue_amount, raise_amount))
                ipo_cnt = 1
        except:
            pass

        try:
            industry = ContextInfo.get_stock_industry(code, "SW")
            if industry and isinstance(industry, str):
                cur.execute(SQL_BASIC, (industry, code))
                ind_cnt = 1
        except:
            pass

        if st_cnt == 0 and ipo_cnt == 0 and ind_cnt == 0:
            skip += 1
            continue

        elapsed = (datetime.now() - start).total_seconds()
        avg = elapsed / (i + 1) if i > 0 else 0
        remain = int((len(stocks) - i - 1) * avg / 60)
        print("[" + str(pct) + "%] " + str(real_idx) + "/" + str(total) + " " + code +
              " ST(" + str(st_cnt) + ")IPO(" + str(ipo_cnt) + ")IND(" + str(ind_cnt) + ") ETA" + str(remain) + "m")
        ok += 1

        if (i + 1) % COMMIT_INTERVAL == 0:
            db.commit()
            save_checkpoint(db, "qmt_pump_basic", real_idx, total, code)

    db.commit()
    save_checkpoint(db, "qmt_pump_basic", total, total, "", "completed")
    db.close()

    t = int((datetime.now() - start).total_seconds() / 60)
    print("=" * 60)
    print("DONE! OK=" + str(ok) + " SKIP=" + str(skip) + " FAIL=" + str(fail) + " TIME=" + str(t) + "m")
    print("=" * 60)


def handlebar(ContextInfo):
    pass