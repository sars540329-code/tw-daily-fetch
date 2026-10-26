# 台股日線抓取 tw_daily_fetch（v1.1）
來源：證交所 MI_INDEX（上市）＋ 櫃買中心 afterTrading/otc（上櫃）。不用 FinMind、不吃額度。
只留一般股票（4 碼、非 0 開頭），排除 ETF／權證／ETN。

## 用法（py -3.13）
- 雙擊「抓最近7天.bat」
- 區間：py -3.13 tw_daily_fetch.py --start 2026-09-01 --end 2026-10-16
- 篩選：py -3.13 tw_daily_fetch.py --screen 2026-10-16 （量>1000張、漲>3%、量比>1.5，昨日=前一交易日）
- 重抓：加 --force

## 輸出
- data\daily\YYYYMMDD.csv：單日
- data\panel.csv：累積日線（date, code, name, market, open, high, low, close, prev_close, chg, chg_pct, body_pct, volume_lots, amount, trades）
  - chg_pct = 跟昨收比；body_pct = (收-開)/開
- data\screen_日期.csv：篩選結果

## 注意
- 每次請求間隔 3.5 秒（一天 2 次請求 ≈ 7 秒），一年約 250 天 ≈ 30 分鐘。
- 舊版 Downloads\v1_爬證交所 的櫃買網址不管日期都回最新一天，已棄用。
- 已實測：2025-01-02~2026-10-16 共 433 個交易日、826,332 筆；2330、2454、6488 收盤價與 yfinance 逐日比對全部一致（yfinance 缺 2025-08-01，本工具有）。2024 以前未驗證。
- 價格為交易所原始價，未做除權息還原。

## 除權息還原（v1.2）
1. `py -3.13 fetch_corp_actions.py` → `data\corp_actions.csv`（官方：上市 TWT49U/TWTAUU/TWTB8U、上櫃 exDailyQ/revivt，2016~）
2. `py -3.13 adjust.py` → `data\panel_adj.parquet`（多了 adj_open/high/low/close、adj_mult；最新價不變，往回調整；量不調整）、`data\adj_events.csv`（每筆事件與係數）
- 係數＝參考價÷前收。官方表優先；上櫃面額變更無官方端點，用「收盤−漲跌＝參考價」偵測（只收無空檔或 ≥1.5 倍的變動）
- 證交所漲跌「X」＝不比價（除權息當天），v1.2 起存空值；舊資料的 0.00 不拿來偵測
- 舊版櫃買（2016 等）漲跌寫成「+ 0.10」，v1.2 起可解析
- 驗證（2025-01~2026-10）：2330、2317、2454、2881、6488、5347、5904、5314 還原價與 yfinance Adj Close 比值最大偏離 ≤0.05%

## 2016~2026 完整版（2026-10-21）
- panel.csv：2,629 個交易日、4,555,416 筆（2016-01-04 ~ 2026-10-19），每天上市＋上櫃皆有
- 含 8 個週六補班交易日（2016-01-30、06-04、09-10、2017-02-18、06-03、09-30、2018-03-31、12-22）；v1.2 起週六也會查
- 還原事件 16,523 筆：官方 16,507＋偵測 16（14 筆為上櫃 * 面額變更）
- 與 yfinance 長期比對的偏離，逐筆查證皆為 yfinance 問題：報價錯（2317 2021-08-17、6488 2016-07-12）、早年價格只留 2 位小數、漏減資（2317 2018-10-26 退還股款減資，官方參考價 68.10→82.62）
- `rebuild_panel.py`：用 data\daily\*.csv 重建 panel.csv（中斷或補單日後用）
- 空間：panel.csv 419MB、daily 425MB、panel_adj.parquet 173MB
