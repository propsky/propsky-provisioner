# Code Review 第二輪處理報告（2026-09-11）

## P0 修正

### 1. raw REPL 回應遺失

`RawReplClient` 新增內部 read buffer。讀取 marker 時只消費到 marker，marker 後同一個 serial chunk 的資料會保留給下一次 `_read_until()` 或 `_read_exact()`。讀取大小優先使用 `in_waiting`，避免 `read(256)` 為了湊滿長度而等待。

新增測試覆蓋 `OKhello\x04\x04>` 一次讀入的情境，確認 stdout、stderr 與 prompt 都能正確消費。

### 2. 韌體日期格式

韌體日期解析改支援 `2026-08-24`、`20260824` 等格式，統一正規化為 `20260824` 後比對，避免正確韌體被無限判定為不符。

## P1/P2 修正

- 起始編號欄位完成編輯時立即更新本次 session 的下一個號碼。
- 啟動與開始燒錄前檢查帳本內 MAC、token、小卡編號重複。
- retry boot 驗收增加 token/MAC 比對，不再顯示假的綠勾。
- 識別按鈕實際開啟 COM port、送出短暫控制字元並關閉 port。
- XLSX fallback 查找全程使用 Ledger lock。
- 韌體版本或日期不符時關閉 raw REPL、執行 flash，然後自動回到流程開始；raw REPL 三次失敗也會觸發一次自動重燒。
- 凍結版 esptool 不再呼叫 `provision.exe -m esptool`，改尋找 `esptool.exe`；開發版仍使用 `sys.executable -m esptool`。
- CSV 被其他程式鎖定時轉為明確的 `ProvisionError`，UI 會顯示可操作的錯誤訊息。
- RSSI 低於 -75 dBm 時寫入操作 log 警告。
- 今日紀錄改以 `燒錄時間` 日期篩選。
- 清檔時跳過目錄，payload 內被工具管理的檔案會明確記錄略過原因。

## 驗證

- `python -m compileall -q src tests`：通過
- `python -m pytest -q`：4 passed
- `ruff` 未安裝，因此未執行 ruff lint。

## 實機注意事項

- 仍需在實機確認 USB-TTL 的 DTR/RTS 接線、esptool executable 的打包位置，以及不同 MicroPython 版本的 raw REPL 流控行為。
- MQTT 狀態目前會在 60 秒開機 log 視窗內解析；若韌體在此視窗後才輸出 MQTT 狀態，仍會記為「未確認」。
- raw-paste 尚未加入，目前仍使用一般 raw REPL fallback 流程。
