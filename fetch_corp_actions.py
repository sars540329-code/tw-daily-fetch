# -*- coding: utf-8 -*-
# 抓官方「除權息／減資／面額變更」事件表 → data\corp_actions.csv
# 上市：TWT49U（除權息）、TWTAUU（減資）、TWTB8U（面額變更）
# 上櫃：exDailyQ（除權息）、revivt（減資）；上櫃面額變更目前沒有已知端點，靠 adjust.py 的「參考價偵測」補
import os, re, time, sys
import requests, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data", "corp_actions.csv")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
SLEEP = 4


def num(s):
    s = str(s).replace(",", "").replace(" ", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def to_date(s):
    s = str(s).strip()
    m = re.match(r"(\d{2,3})年(\d{1,2})月(\d{1,2})日", s)
    if m:
        return f"{int(m[1]) + 1911:04d}-{int(m[2]):02d}-{int(m[3]):02d}"
    d = re.sub(r"\D", "", s)
    if len(d) == 7:
        return f"{int(d[:3]) + 1911:04d}-{d[3:5]}-{d[5:7]}"
    if len(d) == 6:   # 民國 2 位數年 (例 990105)
        return f"{int(d[:2]) + 1911:04d}-{d[2:4]}-{d[4:6]}"
    if len(d) == 8:
        return f"{d[:4]}-{d[4:6]}-{d[6:8]}"
    return None


def get(url, params):
    for i in range(3):
        try:
            r = requests.get(url, params=params, headers=UA, timeout=60)
            j = r.json()
            ts = j.get("tables") or [j]
            return max(ts, key=lambda t: len(t.get("data") or []))
        except Exception as e:
            print("  重試", i + 1, str(e)[:80]); time.sleep(10)
    return {}


def rows(t, cols_map, market, kind):
    f = [re.sub(r"\s+", "", x) for x in (t.get("fields") or [])]
    out = []
    for r in t.get("data") or []:
        g = {k: r[f.index(v)] if v in f else None for k, v in cols_map.items()}
        out.append({"date": to_date(g["date"]), "code": str(g["code"]).strip(), "market": market, "kind": kind,
                    "prev_close": num(g["prev"]), "ref": num(g["ref"]), "note": g.get("note")})
    return out


def main(y0=2016, y1=2026):
    allr = []
    for y in range(y0, y1 + 1):
        a, b = f"{y}0101", f"{y}1231"
        A, B = f"{y}/01/01", f"{y}/12/31"
        t = get("https://www.twse.com.tw/rwd/zh/exRight/TWT49U", {"response": "json", "startDate": a, "endDate": b})
        r1 = rows(t, {"date": "資料日期", "code": "股票代號", "prev": "除權息前收盤價", "ref": "除權息參考價", "note": "權/息"}, "上市", "除權息"); time.sleep(SLEEP)
        t = get("https://www.twse.com.tw/rwd/zh/reducation/TWTAUU", {"response": "json", "startDate": a, "endDate": b})
        r2 = rows(t, {"date": "恢復買賣日期", "code": "股票代號", "prev": "停止買賣前收盤價格", "ref": "恢復買賣參考價"}, "上市", "減資"); time.sleep(SLEEP)
        t = get("https://www.twse.com.tw/rwd/zh/change/TWTB8U", {"response": "json", "startDate": a, "endDate": b})
        r3 = rows(t, {"date": "恢復買賣日期", "code": "股票代號", "prev": "停止買賣前收盤價格", "ref": "恢復買賣參考價"}, "上市", "面額變更"); time.sleep(SLEEP)
        t = get("https://www.tpex.org.tw/www/zh-tw/bulletin/exDailyQ", {"startDate": A, "endDate": B, "response": "json"})
        r4 = rows(t, {"date": "除權息日期", "code": "代號", "prev": "除權息前收盤價", "ref": "除權息參考價", "note": "權/息"}, "上櫃", "除權息"); time.sleep(SLEEP)
        t = get("https://www.tpex.org.tw/www/zh-tw/bulletin/revivt", {"startDate": A, "endDate": B, "response": "json"})
        r5 = rows(t, {"date": "恢復買賣日期", "code": "股票代號", "prev": "最後交易日之收盤價格", "ref": "減資恢復買賣開始日參考價格"}, "上櫃", "減資"); time.sleep(SLEEP)
        n = [len(x) for x in (r1, r2, r3, r4, r5)]
        print(f"{y}：上市 除權息{n[0]} 減資{n[1]} 面額{n[2]}｜上櫃 除權息{n[3]} 減資{n[4]}")
        allr += r1 + r2 + r3 + r4 + r5
    df = pd.DataFrame(allr)
    df = df[df["code"].str.match(r"^[1-9]\d{3}$") & df["date"].notna() & df["prev_close"].notna() & df["ref"].notna()]
    df = df[(df["prev_close"] > 0) & (df["ref"] > 0)]
    df["factor"] = (df["ref"] / df["prev_close"]).round(8)
    df = df.drop_duplicates(["date", "code", "kind"]).sort_values(["date", "code"])
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    df.to_csv(OUT, index=False, encoding="utf-8-sig")
    print(f"corp_actions.csv：{len(df)} 筆（{df['date'].min()} ~ {df['date'].max()}）")
    print(df.groupby(["market", "kind"]).size().to_string())


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
