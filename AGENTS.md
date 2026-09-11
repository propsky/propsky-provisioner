# Repository Guidance

## Current State

- The application is under active implementation in `src/provisioner`; the specification remains the source of truth for the ESP32/MicroPython flow, numbering rules, validation criteria, and ledger behavior.
- `出廠設定工具_介面草圖.html` is still only a visual reference; the runtime UI is the PySide6 application in `src/provisioner/ui.py`.
- Hardware assets are intentionally local and ignored: put exactly one firmware `.bin` in `firmware/` and payload files in `payload/` before starting a real provisioning run.

## Workflow

- Install with `python -m pip install -e ".[dev]"`; run with `python -m provisioner`.
- Run the hardware-independent checks with `python -m pytest -q`; there is no CI workflow yet.
- The repository-local OpenCode config is `.opencode/opencode.json`; it registers the `opencode-goal` plugin.
- Keep WiFi passwords out of CSV, XLSX, and serial logs. `config.ini` is local-only and ignored.
- Do not let Thonny or another serial tool hold the COM port during a run; the USB-TTL DTR/RTS wiring and esptool commands are specified in `ESP32出廠設定工具_規格_1.md`.
