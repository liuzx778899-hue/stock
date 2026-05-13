#coding:gbk
"""
QMT 数据泵 - 财务数据（利润表/资产负债表/现金流量表/每股指标）
写入: stock_financial_income, stock_financial_balance, stock_financial_cashflow, stock_financial_per_share
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

FINANCIAL_FIELDS = {
    "income": [
        "income.operating_revenue", "income.operating_cost", "income.oper_profit",
        "income.total_profit", "income.net_profit", "income.net_profit_incl_min_int_income",
        "income.basic_eps", "income.diluted_eps"
    ],
    "balance": [
        "balance.total_assets", "balance.fix_assets", "balance.total_liabilities",
        "balance.total_equity"
    ],
    "cashflow": [
        "cashflow.net_cash_flows_oper_act", "cashflow.net_cash_flows_inv_act",
        "cashflow.net_cash_flows_fin_act"
    ],
    "per_share": [
        "per_share.eps", "per_share.bvps", "per_share.revenue_per_share",
        "per_share.oper_profit_per_share"
    ]
}


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
    print("QMT 财务数据泵")
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

    cp = get_checkpoint(db, "qmt_pump_financial")
    from_idx = cp["current_index"]
    print("[OK] resume from " + str(from_idx + 1))

    stocks = all_stocks[from_idx:]
    print("Processing " + str(len(stocks)) + " stocks (" + START_DATE + " ~ " + END_DATE + ")")
    print("-" * 40)

    ok = fail = skip = 0
    start = datetime.now()

    SQL_INCOME = """INSERT INTO stock_financial_income
        (ts_code, report_date, operating_revenue, operating_cost, oper_profit,
         total_profit, net_profit, net_profit_incl_min, basic_eps, diluted_eps, created_at, updated_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW(),NOW())
        ON DUPLICATE KEY UPDATE
        operating_revenue=VALUES(operating_revenue),operating_cost=VALUES(operating_cost),
        oper_profit=VALUES(oper_profit),total_profit=VALUES(total_profit),
        net_profit=VALUES(net_profit),net_profit_incl_min=VALUES(net_profit_incl_min),
        basic_eps=VALUES(basic_eps),diluted_eps=VALUES(diluted_eps),updated_at=NOW()"""

    SQL_BALANCE = """INSERT INTO stock_financial_balance
        (ts_code, report_date, total_assets, fix_assets, total_liabilities, total_equity, created_at, updated_at)
        VALUES (%s,%s,%s,%s,%s,%s,NOW(),NOW())
        ON DUPLICATE KEY UPDATE
        total_assets=VALUES(total_assets),fix_assets=VALUES(fix_assets),
        total_liabilities=VALUES(total_liabilities),total_equity=VALUES(total_equity),updated_at=NOW()"""

    SQL_CASHFLOW = """INSERT INTO stock_financial_cashflow
        (ts_code, report_date, net_cash_oper, net_cash_inv, net_cash_fin, created_at, updated_at)
        VALUES (%s,%s,%s,%s,%s,NOW(),NOW())
        ON DUPLICATE KEY UPDATE
        net_cash_oper=VALUES(net_cash_oper),net_cash_inv=VALUES(net_cash_inv),
        net_cash_fin=VALUES(net_cash_fin),updated_at=NOW()"""

    SQL_PER_SHARE = """INSERT INTO stock_financial_per_share
        (ts_code, report_date, eps, bvps, revenue_per_share, oper_profit_per_share, created_at, updated_at)
        VALUES (%s,%s,%s,%s,%s,%s,NOW(),NOW())
        ON DUPLICATE KEY UPDATE
        eps=VALUES(eps),bvps=VALUES(bvps),
        revenue_per_share=VALUES(revenue_per_share),
        oper_profit_per_share=VALUES(oper_profit_per_share),updated_at=NOW()"""

    for i, code in enumerate(stocks):
        real_idx = from_idx + i + 1
        pct = real_idx * 100 // total

        try:
            fin_data = ContextInfo.get_financial_data(
                FINANCIAL_FIELDS["income"] + FINANCIAL_FIELDS["balance"] +
                FINANCIAL_FIELDS["cashflow"] + FINANCIAL_FIELDS["per_share"],
                [code], START_DATE, END_DATE
            )
        except Exception as e:
            fail += 1
            continue

        if fin_data is None or (hasattr(fin_data, "empty") and fin_data.empty):
            skip += 1
            continue

        cnt_income = cnt_balance = cnt_cashflow = cnt_per_share = 0
        cur = db.cursor()
        try:
            for idx_i, row in fin_data.iterrows():
                try:
                    report_date = str(row.get("report_date", row.get("pub_date", "")))[:10]
                except:
                    continue
                if not report_date:
                    continue

                cur.execute(SQL_INCOME, (
                    code, report_date,
                    safe_float(row.get("income.operating_revenue")),
                    safe_float(row.get("income.operating_cost")),
                    safe_float(row.get("income.oper_profit")),
                    safe_float(row.get("income.total_profit")),
                    safe_float(row.get("income.net_profit")),
                    safe_float(row.get("income.net_profit_incl_min_int_income")),
                    safe_float(row.get("income.basic_eps")),
                    safe_float(row.get("income.diluted_eps"))
                ))
                cnt_income += 1

                cur.execute(SQL_BALANCE, (
                    code, report_date,
                    safe_float(row.get("balance.total_assets")),
                    safe_float(row.get("balance.fix_assets")),
                    safe_float(row.get("balance.total_liabilities")),
                    safe_float(row.get("balance.total_equity"))
                ))
                cnt_balance += 1

                cur.execute(SQL_CASHFLOW, (
                    code, report_date,
                    safe_float(row.get("cashflow.net_cash_flows_oper_act")),
                    safe_float(row.get("cashflow.net_cash_flows_inv_act")),
                    safe_float(row.get("cashflow.net_cash_flows_fin_act"))
                ))
                cnt_cashflow += 1

                cur.execute(SQL_PER_SHARE, (
                    code, report_date,
                    safe_float(row.get("per_share.eps")),
                    safe_float(row.get("per_share.bvps")),
                    safe_float(row.get("per_share.revenue_per_share")),
                    safe_float(row.get("per_share.oper_profit_per_share"))
                ))
                cnt_per_share += 1

        except Exception as e:
            fail += 1
            continue

        elapsed = (datetime.now() - start).total_seconds()
        avg = elapsed / (i + 1) if i > 0 else 0
        remain = int((len(stocks) - i - 1) * avg / 60)
        print("[" + str(pct) + "%] " + str(real_idx) + "/" + str(total) + " " + code +
              " I(" + str(cnt_income) + ")B(" + str(cnt_balance) + ")C(" + str(cnt_cashflow) + ")P(" + str(cnt_per_share) + ") ETA" + str(remain) + "m")
        ok += 1

        if (i + 1) % COMMIT_INTERVAL == 0:
            db.commit()
            save_checkpoint(db, "qmt_pump_financial", real_idx, total, code)

    db.commit()
    save_checkpoint(db, "qmt_pump_financial", total, total, "", "completed")
    db.close()

    t = int((datetime.now() - start).total_seconds() / 60)
    print("=" * 60)
    print("DONE! OK=" + str(ok) + " SKIP=" + str(skip) + " FAIL=" + str(fail) + " TIME=" + str(t) + "m")
    print("=" * 60)


def handlebar(ContextInfo):
    pass
