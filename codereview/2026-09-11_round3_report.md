# Code Review 第三輪處理報告（2026-09-11）

## 修正內容

### P0-A：friendly REPL 提示誤判

- `_enter_raw_repl()` 不再以第一個 `>` 作為完成條件。
- 現在先等待 `raw REPL` banner，再消費 raw REPL 的 `>` prompt，因此會正確跳過前面的 `>>>` friendly REPL 提示。
- 新增 fake serial 測試，覆蓋 `>>> raw REPL; CTRL-B to exit\r\n>`。

### P1-B：帳本重複檢查誤擋重燒

- `duplicate_fields()` 改檢查 identity mapping，而不是單純計算值是否重複。
- 同一 MAC 重燒多列，只要 token 與小卡編號一致就允許。
- 同一 MAC 對應不同 token/小卡編號會被拒絕。
- 同一小卡編號或 token 對應不同 MAC 會被拒絕。
- CSV 與 XLSX 資料會合併檢查，並在 Ledger lock 內執行。
- 新增測試覆蓋「同 MAC 重複列允許」與「衝突 identity 拒絕」。

### P1-C：DTR/RTS 開 port 順序

- raw REPL 與識別流程都改為先建立未開啟的 Serial object。
- 先設定 `DTR=False`、`RTS=False`，再設定 port 並呼叫 `open()`。
- 連線失敗釋放時先釋放 RTS，再處理 DTR，避免 IO0 留在低電位。
- 識別改送無害 `NUL` 位元組，不再送 Ctrl-C 中斷板上程式。

### P2/P3

- 凍結版 esptool 優先尋找 `provision.exe` 同目錄的 `esptool.exe`，再 fallback 到 PATH。
- uname 沒有日期時只比對韌體版本並寫入 log，不再誤判日期錯誤。
- 燒錄開始後修改起始編號會顯示提示，並保留當日目前配號順序。
- 移除未使用的 `Iterable` 與 `ProvisionError` import。

## 版本

- `0.1.1` -> `0.1.2`
- 同步更新 `src/provisioner/__init__.py` 與 `pyproject.toml`。

## 驗證

- `python -m compileall -q src tests`：通過
- `python -m pytest -q`：6 passed
- `ruff` 未安裝，因此未執行 ruff lint。

## 尚待後續

- raw-paste 模式尚未加入。
- MQTT 狀態仍限於開機 60 秒 log 視窗內解析。
