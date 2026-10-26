# -*- coding: utf-8 -*-
# 除權息／減資／面額變更 還原 → data\panel_adj.parquet（另存 adj_events.csv 供核對）
# 還原係數來源（優先序）：
#   1) 官方事件表 corp_actions.csv：factor = 參考價 / 前收
#   2) 參考價偵測：交易所漲跌是跟參考價比 → 參考價 = 收盤 − 漲跌；若 ≠ 前一筆收盤（差 >1%）且官方表沒有，視為事件
# 還原方式：向後調整（最新價不變），adj = 原始價 × Π(之後所有事件 factor)
# 成交量不調整（保留原始張數）
import os, sys
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
D = os.path.join(HERE, "data")
DETECT_MIN = 0.01        # 偵測門檻：參考價與前收差 >1% 才算事件


def main():
    p = pd.read_csv(os.path.join(D, "panel.csv"), dtype={"code": str})
    p = p.sort_values(["code", "date"]).reset_index(drop=True)
    ca = pd.read_csv(os.path.join(D, "corp_actions.csv"), dtype={"code": str})
    ca = ca[ca["date"] <= p["date"].max()]

    # ── 官方事件對到「該股事件日當天或之後第一個有成交的日子」
    first = p[["code", "date"]].copy()
    first["trade_date"] = pd.to_datetime(first["date"])
    ca = ca.assign(ev_date=pd.to_datetime(ca["date"])).sort_values("ev_date")
    ev = pd.merge_asof(ca, first[["code", "trade_date"]].sort_values("trade_date"),
                       left_on="ev_date", right_on="trade_date", by="code", direction="forward")
    ev = ev.dropna(subset=["trade_date"])
    ev["trade_date"] = ev["trade_date"].dt.strftime("%Y-%m-%d")
    # 同一天多個事件（例如減資同時除權）→ 相乘
    off = ev.groupby(["code", "trade_date"])["factor"].prod().rename("f_off").reset_index()
    kinds = ev.groupby(["code", "trade_date"])["kind"].agg("+".join).rename("kind").reset_index()

    # ── 參考價偵測
    p["prev_close_act"] = p.groupby("code")["close"].shift(1)
    ref = p["close"] - p["chg"]
    # 前一筆必須是「市場上一個交易日」：冷門股中間沒成交時，櫃買漲跌是跟它自己的參考價比，會誤判
    days = np.sort(p["date"].unique())
    prev_mkt = dict(zip(days[1:], days[:-1]))
    no_gap = p.groupby("code")["date"].shift(1).eq(p["date"].map(prev_mkt))
    # 舊資料「X 不比價」被存成 chg=0：漲跌 0 但收盤≠前收 → 無法判斷，不拿來偵測
    base = p["chg"].notna() & (p["prev_close_act"] > 0) & ~((p["chg"] == 0) & (p["close"] != p["prev_close_act"]))
    f_raw = ref / p["prev_close_act"]
    # 有空檔（停止交易後恢復）只接受大幅結構變動（面額變更／減資，≥1.5 倍）；冷門股空檔誤差都在 20% 內
    big = (np.log(f_raw.where(f_raw > 0)).abs() > np.log(1.5))
    usable = base & (no_gap | big)
    p["f_det"] = np.where(usable, ref / p["prev_close_act"], np.nan)

    p = p.merge(off, left_on=["code", "date"], right_on=["code", "trade_date"], how="left").drop(columns="trade_date")
    p = p.merge(kinds, left_on=["code", "date"], right_on=["code", "trade_date"], how="left").drop(columns="trade_date")
    det_only = p["f_off"].isna() & (p["f_det"] - 1).abs().gt(DETECT_MIN)
    p["factor"] = np.where(p["f_off"].notna(), p["f_off"], np.where(det_only, p["f_det"], 1.0))
    p.loc[det_only, "kind"] = "偵測(無官方)"
    # 每檔第一筆不調整
    p.loc[p.groupby("code").cumcount() == 0, "factor"] = 1.0

    # ── 向後還原：mult(t) = Π factor(s) for s > t
    p["logf"] = np.log(p["factor"])
    rev_cum = p.iloc[::-1].groupby("code")["logf"].cumsum().iloc[::-1]
    p["adj_mult"] = np.exp(rev_cum - p["logf"])
    for c in ("open", "high", "low", "close"):
        p["adj_" + c] = (p[c] * p["adj_mult"]).round(4)

    # ── 輸出
    evt = p[p["factor"] != 1.0][["date", "code", "name", "market", "kind", "prev_close_act", "close", "chg",
                                   "f_off", "f_det", "factor"]]
    evt.to_csv(os.path.join(D, "adj_events.csv"), index=False, encoding="utf-8-sig")
    out = p.drop(columns=["prev_close_act", "f_det", "f_off", "kind", "logf", "factor"])
    out.to_parquet(os.path.join(D, "panel_adj.parquet"), index=False)

    both = evt["f_off"].notna() & evt["f_det"].notna()
    diff = (evt.loc[both, "f_off"] - evt.loc[both, "f_det"]).abs()
    print(f"還原完成：{out['code'].nunique()} 檔、{len(out)} 筆 → data\\panel_adj.parquet")
    print(f"事件 {len(evt)} 筆：官方 {evt['f_off'].notna().sum()}、僅偵測 {(evt['kind'] == '偵測(無官方)').sum()}")
    print(f"官方 vs 偵測 都有的 {both.sum()} 筆：係數差 >0.5% 的 {int((diff > 0.005).sum())} 筆")
    big = evt[evt["kind"] == "偵測(無官方)"].assign(chgpct=lambda x: (x["factor"] - 1) * 100)
    if len(big):
        print("僅偵測事件（前 15，請人工核對）：")
        print(big.sort_values("chgpct")[["date", "code", "name", "market", "prev_close_act", "close", "chg", "factor"]].head(15).to_string(index=False))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
