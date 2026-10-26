# -*- coding: utf-8 -*-
# 版本: v1.1 - 櫃買改新版 API（舊版不管日期都回最新一天）；
# 版本: v1.0 - 證交所(上市)+櫃買中心(上櫃) 全市場日收盤 → 累積日線 panel.csv（不用 FinMind、不吃額度）
# 改良自 Downloads\v1_爬證交所+櫃買中心：
#   1) 漲跌幅 = 跟「昨收」比（交易所漲跌價差），另保留 實體% =(收-開)/開
#   2) 只留一般股票：代號 4 碼且不是 0 開頭（排除 ETF / 權證 / ETN / 債券）
#   3) 可抓日期區間，自動累積成 data\panel.csv（重抓同日會覆蓋，不重複）
#   4) 假日自動跳過；篩選的「昨日」用 panel 裡前一個交易日，不是日期減 1
# 用法：
#   py -3.13 tw_daily_fetch.py                        → 抓最近 7 天（已抓過的日子跳過）
#   py -3.13 tw_daily_fetch.py --start 2026-09-01 --end 2026-10-16
#   py -3.13 tw_daily_fetch.py --screen 2026-10-16    → 只做篩選（量>1000張、漲>3%、量比>1.5）
#   加 --force 重抓已存在的日子
import os, re, sys, time, argparse
from datetime import datetime, timedelta
import requests
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
DAILY = os.path.join(DATA, "daily")
PANEL = os.path.join(DATA, "panel.csv")
SLEEP = 3.5          # 每次請求間隔秒數（證交所太快會暫時封 IP）
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
COLS = ["date", "code", "name", "market", "open", "high", "low", "close",
        "prev_close", "chg", "chg_pct", "body_pct", "volume_lots", "amount", "trades"]
STOCK_RE = re.compile(r"^[1-9]\d{3}$")   # 一般股票


def num(s):
    s = str(s).replace(",", "").replace(" ", "").strip()   # 舊版櫃買漲跌為 "+ 0.10"（符號後有空格）
    try:
        return float(s)
    except ValueError:
        return float("nan")


def get_json(url, params, headers=None, tries=3):
    for i in range(tries):
        try:
            r = requests.get(url, params=params, headers={**UA, **(headers or {})}, timeout=30)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            print(f"  連線失敗({i + 1}/{tries})：{str(e)[:100]}")
            time.sleep(10 * (i + 1))
    return None


def fetch_twse(d):
    p = get_json("https://www.twse.com.tw/exchangeReport/MI_INDEX",
                 {"response": "json", "date": d.strftime("%Y%m%d"), "type": "ALLBUT0999"})
    if not p or p.get("stat") != "OK":
        return None
    t = next((t for t in p.get("tables", []) if "證券代號" in (t.get("fields") or [])
              and "收盤" in (t.get("title") or "")), None)
    if t is None or not t.get("data"):
        return None
    df = pd.DataFrame(t["data"], columns=t["fields"])
    df["code"] = df["證券代號"].astype(str).str.strip()
    df = df[df["code"].str.match(STOCK_RE)].copy()
    sign = df["漲跌(+/-)"].astype(str).map(lambda s: -1 if "-" in s else (1 if "+" in s else (np.nan if "X" in s else 0)))
    out = pd.DataFrame({
        "code": df["code"], "name": df["證券名稱"].str.strip(), "market": "上市",
        "open": df["開盤價"].map(num), "high": df["最高價"].map(num), "low": df["最低價"].map(num),
        "close": df["收盤價"].map(num), "chg": sign * df["漲跌價差"].map(num),
        "volume_lots": (df["成交股數"].map(num) / 1000).round(0),
        "amount": df["成交金額"].map(num), "trades": df["成交筆數"].map(num)})
    return out


def fetch_tpex(d):
    # 新版 API：會照日期回傳並附回傳日期（舊版 stk_quote_result.php 不管日期都回最新一天，不能用）
    p = get_json("https://www.tpex.org.tw/www/zh-tw/afterTrading/otc",
                 {"date": d.strftime("%Y/%m/%d"), "type": "EW", "response": "json"})
    if not p or p.get("stat", "").lower() != "ok":
        return None
    if str(p.get("date")) != d.strftime("%Y%m%d"):
        print(f"  ⚠ 櫃買回傳日期 {p.get('date')} ≠ 要求 {d:%Y%m%d}，不採用")
        return None
    t = max(p.get("tables") or [{}], key=lambda t: len(t.get("data") or []))
    rows, fields = t.get("data") or [], [re.sub(r"\s+", "", f) for f in (t.get("fields") or [])]
    if not rows:
        return None
    df = pd.DataFrame(rows, columns=fields)
    need = ["代號", "名稱", "收盤", "漲跌", "開盤", "最高", "最低", "成交股數"]
    miss = [c for c in need if c not in df.columns]
    if miss:
        print("  ⚠ 櫃買欄位變了，缺：", miss, "現有：", fields); return None
    amt = next((c for c in df.columns if c.startswith("成交金額")), None)
    trd = next((c for c in df.columns if c.startswith("成交筆數")), None)
    df["code"] = df["代號"].astype(str).str.strip()
    df = df[df["code"].str.match(STOCK_RE)].copy()
    out = pd.DataFrame({
        "code": df["code"], "name": df["名稱"].str.strip(), "market": "上櫃",
        "open": df["開盤"].map(num), "high": df["最高"].map(num), "low": df["最低"].map(num),
        "close": df["收盤"].map(num), "chg": df["漲跌"].map(num),
        "volume_lots": (df["成交股數"].map(num) / 1000).round(0),
        "amount": df[amt].map(num) if amt else float("nan"),
        "trades": df[trd].map(num) if trd else float("nan")})
    return out


def fetch_day(d):
    tw = fetch_twse(d)
    time.sleep(SLEEP)
    if tw is None:
        return None                      # 證交所沒資料 = 休市
    ot = fetch_tpex(d)
    time.sleep(SLEEP)
    if ot is None:
        print("  ⚠ 櫃買中心沒資料，本日只有上市")
    df = pd.concat([x for x in (tw, ot) if x is not None], ignore_index=True)
    df = df[df["close"].notna() & (df["volume_lots"] > 0)].copy()   # 排除當天沒成交
    df.insert(0, "date", d.strftime("%Y-%m-%d"))
    # 證交所「X」＝不比價（除權息當天等），漲跌未知 → chg/prev_close/chg_pct 留空，不可當 0
    df["prev_close"] = (df["close"] - df["chg"]).round(4)
    df["chg_pct"] = (df["chg"] / df["prev_close"] * 100).round(2)
    df["body_pct"] = ((df["close"] - df["open"]) / df["open"] * 100).round(2)
    return df[COLS]


def load_panel():
    if os.path.exists(PANEL):
        return pd.read_csv(PANEL, dtype={"code": str})
    return pd.DataFrame(columns=COLS)


def save_panel(new_days):
    panel = load_panel()
    dates = {d for df in new_days for d in df["date"].unique()}
    keep = panel[~panel["date"].isin(dates)]
    panel = pd.concat(([keep] if len(keep) else []) + new_days, ignore_index=True)
    panel = panel.sort_values(["date", "code"]).reset_index(drop=True)
    panel.to_csv(PANEL, index=False, encoding="utf-8-sig")
    return panel


def run_fetch(start, end, force=False):
    os.makedirs(DAILY, exist_ok=True)
    got, d = [], start
    while d <= end:
        fp = os.path.join(DAILY, d.strftime("%Y%m%d") + ".csv")
        if d.weekday() == 6:      # 只跳過週日；週六可能是補班交易日（2016~2018 有 8 天）
            pass
        elif os.path.exists(fp) and not force:
            print(f"{d:%Y-%m-%d} 已有，跳過")
        else:
            df = fetch_day(d)
            if df is None:
                print(f"{d:%Y-%m-%d} 休市/無資料")
            else:
                df.to_csv(fp, index=False, encoding="utf-8-sig")
                got.append(df)
                print(f"{d:%Y-%m-%d} OK：上市 {(df.market == '上市').sum()} 檔、上櫃 {(df.market == '上櫃').sum()} 檔")
        d += timedelta(days=1)
    if got:
        panel = save_panel(got)
        print(f"panel.csv：{panel['date'].nunique()} 個交易日、{len(panel)} 筆（{panel['date'].min()} ~ {panel['date'].max()}）")
    else:
        print("沒有新資料")


def run_screen(date_str, vol_min=1000, up_min=3.0, ratio_min=1.5):
    panel = load_panel()
    days = sorted(panel["date"].unique())
    if date_str not in days:
        print(f"panel 裡沒有 {date_str}，先抓資料"); return
    i = days.index(date_str)
    today = panel[panel["date"] == date_str]
    if i > 0:
        prev = panel[panel["date"] == days[i - 1]][["code", "volume_lots"]].rename(columns={"volume_lots": "prev_lots"})
        today = today.merge(prev, on="code", how="left")
        today["vol_ratio"] = (today["volume_lots"] / today["prev_lots"]).round(2)
        print(f"昨日 = {days[i - 1]}")
    else:
        today = today.assign(prev_lots=float("nan"), vol_ratio=float("nan"))
        print("⚠ panel 沒有前一交易日，量比條件略過")
    cond = (today["volume_lots"] > vol_min) & (today["chg_pct"] > up_min)
    if i > 0:
        cond &= today["vol_ratio"] > ratio_min
    res = today[cond].sort_values("chg_pct", ascending=False)
    os.makedirs(DATA, exist_ok=True)
    fp = os.path.join(DATA, f"screen_{date_str}.csv")
    res.to_csv(fp, index=False, encoding="utf-8-sig")
    print(f"篩出 {len(res)} 檔（量>{vol_min}張、漲幅>{up_min}%、量比>{ratio_min}）→ {fp}")
    if len(res):
        print(res[["code", "name", "market", "close", "chg_pct", "volume_lots", "vol_ratio"]].head(20).to_string(index=False))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--start"); ap.add_argument("--end")
    ap.add_argument("--screen"); ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    if a.screen:
        run_screen(a.screen)
    else:
        end = datetime.strptime(a.end, "%Y-%m-%d") if a.end else datetime.now()
        start = datetime.strptime(a.start, "%Y-%m-%d") if a.start else end - timedelta(days=7)
        run_fetch(start.replace(hour=0, minute=0, second=0, microsecond=0),
                  end.replace(hour=0, minute=0, second=0, microsecond=0), a.force)
