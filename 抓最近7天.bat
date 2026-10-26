@echo off
chcp 65001 >nul
title 台股日線抓取（證交所＋櫃買）
cd /d E:\XQOWL\tw_daily_fetch
py -3.13 tw_daily_fetch.py %*
echo.
pause
