# Code Review 第五輪處理報告（2026-09-11）

## 修正內容

### 新板開始時清除上一片狀態

`start_slot()` 現在會建立新的 `SlotSnapshot`，只保留目前 slot、port 與執行中狀態。上一片的卡號、MAC、token、checks、completed steps、錯誤與 log 不會殘留到下一片。

`retry_slot()` 維持原 snapshot，確保重開機驗收仍保留原板子的身分資料。

### QPlainTextEdit 終端樣式

Log 元件已由 `QLabel` 改為 `QPlainTextEdit`，stylesheet selector 同步從 `QLabel#terminal` 改為 `QPlainTextEdit#terminal`，恢復深色終端樣式與等寬字體。

## 版本

- `0.1.3` -> `0.1.4`
- 同步更新 `src/provisioner/__init__.py` 與 `pyproject.toml`。

## 驗證

- `python -m pytest -q`：6 passed
- `python -m compileall -q src tests`：通過
- Qt offscreen smoke test：成功建立 `QPlainTextEdit` log 元件，UI 顯示版本 `0.1.4`
- round5 review 未發現 P0/P1。
