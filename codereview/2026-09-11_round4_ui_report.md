# Code Review 第四輪 UI 處理報告（2026-09-11）

## 修正內容

### P1-A：SlotCard 狀態顏色與 PASS/FAIL

- `SlotCard` 啟用 `Qt.WA_StyledBackground`，使 stylesheet 的狀態邊框實際渲染。
- PASS/FAIL 狀態新增大字狀態標籤，並使用對應的綠色或紅色。
- 步驟列依目前狀態顯示：完成為綠色、目前步驟為藍色、失敗步驟為紅色。

### P1-B：每片板子的 log 落盤

- 每次開始燒錄時建立 `logs/<時間>_<COM>_pending.log`。
- 讀到 MAC 後將檔名改為 `logs/<時間>_<COM>_<MAC>.log`。
- `_on_log` 同步更新畫面與 append 至檔案。
- 流程結束會追加 PASS 或 FAIL 結果，保留 Traceback、開機輸出與錯誤原因。

### P2-C：Log 自動捲動與效能

- 四個 Log 分頁從 `QLabel + QScrollArea` 改為 read-only `QPlainTextEdit`。
- 使用 `appendPlainText()` 與 `ensureCursorVisible()`，新訊息會自動捲到最底，避免每次重新 join 全部內容。

### P2-D：步驟指示列

- `completed_steps` 現在實際反映到步驟列顏色。
- 目前步驟與失敗步驟會使用獨立狀態色。

## 版本

- `0.1.2` -> `0.1.3`
- 同步更新 `src/provisioner/__init__.py` 與 `pyproject.toml`。

## 驗證

- `python -m compileall -q src tests`：通過
- `python -m pytest -q`：6 passed
- Qt offscreen smoke test：成功建立 4 個 SlotCard 與 4 個 Log editor。
- `ruff` 未安裝，因此未執行 ruff lint。
