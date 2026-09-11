# Code Review 第一輪處理報告（2026-09-11）

## 結果

第一輪提出的 P0/P1 已完成修正，並在第二輪針對回歸問題補上協定測試。

## 修正內容

### P0

- `RawReplClient.execute()` 改為依序讀取 `OK`、stdout 結束符、stderr 結束符與 `>` prompt；stderr 非空時直接回報板上例外。
- `machine.reset()` 改為只送出指令，不等待 raw REPL 的回應結束符；並保留後續開機 log。

### P1

- 開機驗收比對 `Get token`、`My MAC Address`、`ESP Wi-Fi OK` 與 `Traceback`。
- 解析程式版本、RSSI、MQTT 狀態並回寫帳本；RSSI 低於 -75 dBm 時記錄警告。
- 失敗流程會把最新 MAC 紀錄更新為 `FAIL`。
- `Ledger.update_result()` 改為更新同一 MAC 的最新一列。
- 起始編號在使用者修改後立即同步；config 保存下一個待配號碼。
- 啟動時備份 XLSX，並檢查 MAC、token、小卡編號重複。
- `find_by_mac()` 支援 CSV 與既有三欄 XLSX，且 XLSX 讀取納入 Ledger 鎖。
- CSV/XLSX 寫入使用同一把可重入鎖，避免四個 worker 互相覆蓋。

### 規格偏差

- raw REPL 連線失敗最多 DTR/RTS 重試三次。
- 韌體版本與檔名日期都會檢查；不符時自動 erase/write flash 後重新執行流程。
- payload、`wifi.dat`、`token.dat` 都執行 SHA-256 驗證。
- 阻止四個燒錄器使用相同 COM port。
- 識別按鈕會開啟指定 port 並送出短脈衝資料，使 TX 指示燈閃爍。
- 凍結版使用外部 `esptool.exe`，非凍結版使用目前 Python 的 esptool module。
- payload 中由工具管理的檔案會略過並寫入 log；目錄不會被當成檔案刪除。
- 「今日紀錄」只顯示當天資料。

## 驗證

- `python -m compileall -q src tests`：通過
- `python -m pytest -q`：4 passed
- 新增 raw REPL「單一 chunk 包含完整回應」測試。
- 新增 MicroPython `YYYY-MM-DD` 韌體日期解析測試。
