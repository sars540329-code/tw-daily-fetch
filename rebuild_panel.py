# 補 2018-12-22 → 用 data\daily\*.csv 重建 panel.csv → 檢查
import sys, os, glob
from datetime import datetime
sys.path.insert(0, r"E:\XQOWL\tw_daily_fetch")
import tw_daily_fetch as t
import pandas as pd

d = datetime(2018, 12, 22)
fp = os.path.join(t.DAILY, "20181222.csv")
if not os.path.exists(fp):
    df = t.fetch_day(d)
    print("2018-12-22", "無資料" if df is None else f"OK {len(df)} 筆")
    if df is not None:
        df.to_csv(fp, index=False, encoding="utf-8-sig")

files = sorted(glob.glob(os.path.join(t.DAILY, "*.csv")))
panel = pd.concat((pd.read_csv(f, dtype={"code": str}) for f in files), ignore_index=True)
panel = panel.drop_duplicates(["date", "code"], keep="last").sort_values(["date", "code"]).reset_index(drop=True)
panel.to_csv(t.PANEL, index=False, encoding="utf-8-sig")
sat = [x for x in panel["date"].unique() if datetime.strptime(x, "%Y-%m-%d").weekday() == 5]
print(f"重建 panel.csv：{len(files)} 個單日檔、{panel['date'].nunique()} 個交易日、{len(panel)} 筆（{panel['date'].min()} ~ {panel['date'].max()}）")
print("週六交易日", len(sat), sat)
