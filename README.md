# Propsky ESP32 出廠設定工具

依照 `ESP32出廠設定工具_規格_1.md` 與 `出廠設定工具_介面草圖.html` 實作的 Windows PySide6 應用程式。

## 開發環境

規格指定 Python 3.12 64-bit。建立虛擬環境後安裝依賴：

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

啟動 GUI：

```powershell
python -m provisioner
```

## 專案結構

- `src/provisioner/ui.py`: 1024x768 風格的四格燒錄 GUI、今日紀錄與 Log 分頁。
- `src/provisioner/provisioning.py`: COM、raw REPL、payload 上傳、SHA-256 驗證、esptool 與開機驗收。
- `src/provisioner/ledger.py`: `provision_log.csv` 優先寫入，再同步 `出廠帳本.xlsx`。
- `src/provisioner/models.py`: 流程狀態、九個步驟與帳本欄位模型。
- `firmware/`: 必須放剛好一個 `.bin`，檔名需含日期與版本，例如 `ESP32_GENERIC-20260824-v1.29.0.bin`。
- `payload/`: 要上傳的檔案；`boot.py`、`token.dat`、`wifi.dat` 會被略過或由程式產生。

## 驗證

不需要接 ESP32 的核心測試：

```powershell
python -m pytest -q
```

## 實機測試

測試員請依照 [`docs/實機測試流程與檢核表.md`](docs/實機測試流程與檢核表.md) 執行單片、重燒、失敗恢復、四路並行與打包驗證，並使用文件內的問題回報模板回報結果。

實機測試前，確認 USB-TTL 使用 CH340 或 CP210x，且不要讓 Thonny 佔用 COM port。GUI 會在開始前檢查 firmware 目錄、SSID 與 COM port。

WiFi 密碼只留在本機 `config.ini` 記憶設定，不會寫入 CSV、XLSX 或 serial log。
