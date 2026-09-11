from __future__ import annotations

import threading
import time
from datetime import date, datetime
from pathlib import Path

import serial
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Qt, Signal, Slot
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import __version__
from .config import AppConfig, load_config, save_config
from .firmware import FirmwareInfo, discover_firmware
from .ledger import Ledger
from .models import LEDGER_HEADERS, ProvisionStep, SlotSnapshot, SlotState, STEPS
from .numbering import next_card_number, validate_card_number
from .provisioning import ProvisionService, available_ports


class WorkerSignals(QObject):
    log = Signal(int, str)
    step = Signal(int, str, int, str)
    finished = Signal(int, object)
    failed = Signal(int, str)


class ProvisionWorker(QRunnable):
    def __init__(self, slot: int, root: Path, port: str, card: str | None, ssid: str, password: str, firmware: FirmwareInfo | None, ledger: Ledger, allocate_card, retry: bool = False):
        super().__init__()
        self.slot = slot
        self.root = root
        self.port = port
        self.card = card
        self.ssid = ssid
        self.password = password
        self.firmware = firmware
        self.ledger = ledger
        self.allocate_card = allocate_card
        self.retry = retry
        self.token = None
        self.mac = None
        self.signals = WorkerSignals()

    @Slot()
    def run(self) -> None:
        service = ProvisionService(
            self.root,
            self.ledger,
            lambda message: self.signals.log.emit(self.slot, message),
            lambda step, progress, message: self.signals.step.emit(self.slot, step.value, progress, message),
        )
        try:
            if self.retry:
                service.retry_boot(self.port, self.token, self.mac)
                self.signals.finished.emit(self.slot, None)
            else:
                assert self.firmware is not None
                record = service.run(self.port, self.card, self.ssid, self.password, self.firmware, self.allocate_card)
                self.signals.finished.emit(self.slot, record)
        except Exception as exc:
            self.signals.failed.emit(self.slot, str(exc))


class SlotCard(QWidget):
    start_requested = Signal(int)
    retry_requested = Signal(int)
    completed_requested = Signal(int)
    log_requested = Signal(int)

    def __init__(self, slot: int) -> None:
        super().__init__()
        self.slot = slot
        self.snapshot = SlotSnapshot(slot=slot)
        self.setObjectName("slotCard")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setMinimumHeight(300)
        self.port_combo = QComboBox()
        self.port_combo.setMinimumWidth(170)
        self.identify_button = QPushButton("識別")
        self.identify_button.setObjectName("subtleButton")
        self.state_label = QLabel("待機")
        self.card_label = QLabel("----")
        self.card_label.setObjectName("cardNumber")
        self.status_big_label = QLabel("")
        self.status_big_label.setObjectName("bigStatus")
        self.status_big_label.setAlignment(Qt.AlignCenter)
        self.status_big_label.hide()
        self.mac_label = QLabel("MAC\n-")
        self.steps_label = QLabel("　".join(step.value for step in STEPS))
        self.steps_label.setObjectName("steps")
        self.message_label = QLabel("換上新板後按「開始」")
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(7)
        self.check_label = QLabel("")
        self.prompt_label = QLabel("")
        self.prompt_label.setWordWrap(True)
        self.prompt_label.setObjectName("prompt")
        self.start_button = QPushButton("開始")
        self.start_button.setObjectName("primaryButton")
        self.start_button.setMinimumHeight(38)
        self.log_button = QPushButton("Log >")
        self.log_button.setObjectName("linkButton")
        self.retry_button = QPushButton("重開機")
        self.retry_button.setObjectName("secondaryButton")
        self.retry_button.hide()
        self.complete_button = QPushButton("完成，可拔板")
        self.complete_button.setObjectName("successButton")
        self.complete_button.hide()

        header = QHBoxLayout()
        header.addWidget(QLabel(f"燒錄器 {slot}"))
        header.addWidget(self.port_combo)
        header.addWidget(self.identify_button)
        header.addStretch()
        header.addWidget(self.state_label)

        identity = QHBoxLayout()
        identity.addWidget(self.card_label)
        identity.addWidget(self.mac_label)
        identity.addStretch()

        footer = QHBoxLayout()
        footer.addWidget(self.start_button, 1)
        footer.addWidget(self.complete_button, 1)
        footer.addWidget(self.retry_button)
        footer.addWidget(self.log_button)

        body = QVBoxLayout(self)
        body.setContentsMargins(10, 8, 10, 8)
        body.addLayout(header)
        body.addLayout(identity)
        body.addWidget(self.status_big_label)
        body.addWidget(self.steps_label)
        body.addWidget(self.message_label)
        body.addWidget(self.progress)
        body.addWidget(self.check_label)
        body.addWidget(self.prompt_label)
        body.addStretch()
        body.addLayout(footer)
        self.start_button.clicked.connect(lambda: self.start_requested.emit(self.slot))
        self.identify_button.clicked.connect(self.identify)
        self.log_button.clicked.connect(lambda: self.log_requested.emit(self.slot))
        self.complete_button.clicked.connect(self.mark_complete)
        self.retry_button.clicked.connect(lambda: self.retry_requested.emit(self.slot))

    def set_ports(self, ports: list[str], selected: str = "未使用") -> None:
        self.port_combo.clear()
        self.port_combo.addItem("未使用")
        self.port_combo.addItems(ports)
        index = self.port_combo.findText(selected)
        self.port_combo.setCurrentIndex(max(0, index))

    def identify(self) -> None:
        port = self.port_combo.currentText()
        if port == "未使用":
            self.message_label.setText("請先選擇 COM port")
            return
        try:
            connection = serial.Serial(None, 115200, timeout=0.2, write_timeout=1)
            connection.dtr = False
            connection.rts = False
            connection.port = port
            connection.open()
            try:
                deadline = time.monotonic() + 2.5
                while time.monotonic() < deadline:
                    connection.write(b"\x00" * 32)
                    connection.flush()
                    time.sleep(0.02)
            finally:
                connection.close()
            self.message_label.setText(f"已識別 {port}，TX 指示燈應已閃爍")
        except serial.SerialException as exc:
            self.message_label.setText(f"識別失敗：{exc}")

    def set_snapshot(self, snapshot: SlotSnapshot) -> None:
        self.snapshot = snapshot
        self.state_label.setText(self._state_text(snapshot.state))
        self.card_label.setText(snapshot.card_number or "----")
        self.mac_label.setText(f"MAC\n{snapshot.mac or '-'}")
        self.message_label.setText(snapshot.message)
        self.progress.setValue(snapshot.progress)
        self.check_label.setText("　".join(f"✓ {item}" for item in snapshot.checks))
        self.steps_label.setText(self._steps_html(snapshot))
        if snapshot.state in {SlotState.PASS, SlotState.FAIL}:
            self.status_big_label.setText(snapshot.state.value.upper())
            self.status_big_label.setStyleSheet(f"color: {self._state_color(snapshot.state)};")
            self.status_big_label.show()
        else:
            self.status_big_label.hide()
        self.prompt_label.setText(
            f"請把 {snapshot.card_number} 寫在板子上，確認 LCD 正常後按「完成」"
            if snapshot.state == SlotState.WAITING and snapshot.card_number
            else snapshot.error or ""
        )
        self.prompt_label.setVisible(bool(self.prompt_label.text()))
        running = snapshot.state == SlotState.RUNNING
        waiting = snapshot.state == SlotState.WAITING
        self.port_combo.setEnabled(not running and not waiting)
        self.start_button.setEnabled(not running and not waiting)
        self.start_button.setVisible(not waiting)
        self.complete_button.setVisible(waiting)
        self.retry_button.setVisible(waiting)
        self.setStyleSheet(f"QWidget#slotCard {{ border: 3px solid {self._state_color(snapshot.state)}; }}")

    @staticmethod
    def _steps_html(snapshot: SlotSnapshot) -> str:
        parts = []
        for step in STEPS:
            color = "#1f9d55" if step in snapshot.completed_steps else "#6b7380"
            if step == snapshot.step and snapshot.state == SlotState.RUNNING:
                color = "#2f6fdb"
            if step == snapshot.step and snapshot.state == SlotState.FAIL:
                color = "#d93a3a"
            parts.append(f'<span style="color:{color};">{step.value}</span>')
        return "　".join(parts)

    def reset(self) -> None:
        self.set_snapshot(SlotSnapshot(slot=self.slot, port=self.port_combo.currentText()))

    def mark_complete(self) -> None:
        self.snapshot.state = SlotState.PASS
        self.snapshot.message = "已完成，可拔板"
        self.snapshot.error = None
        self.complete_button.hide()
        self.retry_button.hide()
        self.start_button.show()
        self.start_button.setText("開始")
        self.set_snapshot(self.snapshot)
        self.completed_requested.emit(self.slot)

    @staticmethod
    def _state_text(state: SlotState) -> str:
        return {SlotState.IDLE: "待機", SlotState.RUNNING: "執行中", SlotState.WAITING: "請確認", SlotState.PASS: "PASS", SlotState.FAIL: "失敗"}[state]

    @staticmethod
    def _state_color(state: SlotState) -> str:
        return {SlotState.IDLE: "#9aa3ae", SlotState.RUNNING: "#2f6fdb", SlotState.WAITING: "#e0a100", SlotState.PASS: "#1f9d55", SlotState.FAIL: "#d93a3a"}[state]


class MainWindow(QMainWindow):
    def __init__(self, root: Path) -> None:
        super().__init__()
        self.root = root
        self.config_path = root / "config.ini"
        self.config = load_config(self.config_path)
        self.ledger = Ledger(root)
        self.snapshots = [SlotSnapshot(slot=index + 1, port=self.config.ports[index]) for index in range(4)]
        self.cards_lock = threading.Lock()
        self.next_card = self.config.first_card_number
        self.cards_used = 0
        self.ledger.backup()
        self.thread_pool = QThreadPool.globalInstance()
        self.workers: dict[int, ProvisionWorker] = {}
        self.log_views: list[QPlainTextEdit] = []
        self.log_paths: dict[int, Path] = {}
        self.cards: list[SlotCard] = []
        self._build_ui()
        self._refresh_ports()
        self._refresh_records()

    def _build_ui(self) -> None:
        self.setWindowTitle(f"Propsky 出廠設定工具 v{__version__}")
        self.setMinimumSize(1000, 720)
        self.resize(1200, 820)
        self._set_style()

        title = QLabel(f"Propsky 出廠設定工具  v{__version__} · SmartPay 投幣板")
        title.setObjectName("titleBar")
        self.first_card = QLineEdit(self.config.first_card_number)
        self.first_card.setMaximumWidth(90)
        self.ssid = QLineEdit(self.config.ssid)
        self.ssid.setMaximumWidth(130)
        self.password = QLineEdit(self.config.wifi_password)
        self.password.setEchoMode(QLineEdit.Normal)
        self.password.setMaximumWidth(130)
        self.load_wifi = QPushButton("載入 wifi.dat")
        self.scan_button = QPushButton("重新掃描")
        self.ready_label = QLabel("尚未檢查設定")
        self.pass_label = QLabel("PASS 0")
        self.fail_label = QLabel("FAIL 0")
        self.startup = QHBoxLayout()
        self.startup.addWidget(QLabel("起始編號"))
        self.startup.addWidget(self.first_card)
        self.startup.addWidget(QLabel("WiFi"))
        self.startup.addWidget(self.ssid)
        self.startup.addWidget(self.password)
        self.startup.addWidget(self.load_wifi)
        self.startup.addWidget(self.scan_button)
        self.startup.addWidget(self.ready_label)
        self.startup.addStretch()
        self.startup.addWidget(self.pass_label)
        self.startup.addWidget(self.fail_label)

        self.tabs = QTabWidget()
        burn_page = QWidget()
        grid = QGridLayout(burn_page)
        grid.setSpacing(10)
        for index in range(4):
            card = SlotCard(index + 1)
            card.start_requested.connect(self.start_slot)
            card.retry_requested.connect(self.retry_slot)
            card.completed_requested.connect(self.complete_slot)
            card.log_requested.connect(self.show_log)
            self.cards.append(card)
            grid.addWidget(card, index // 2, index % 2)
        self.tabs.addTab(burn_page, "燒錄")

        self.records = QTableWidget(0, len(LEDGER_HEADERS))
        self.records.setHorizontalHeaderLabels(LEDGER_HEADERS)
        self.records.setAlternatingRowColors(True)
        self.records.setEditTriggers(QTableWidget.NoEditTriggers)
        records_page = QWidget()
        records_layout = QVBoxLayout(records_page)
        records_toolbar = QHBoxLayout()
        open_ledger = QPushButton("開啟帳本")
        open_csv = QPushButton("開啟 CSV")
        records_toolbar.addWidget(open_ledger)
        records_toolbar.addWidget(open_csv)
        records_toolbar.addStretch()
        self.records_summary = QLabel()
        records_toolbar.addWidget(self.records_summary)
        records_layout.addLayout(records_toolbar)
        records_layout.addWidget(self.records)
        self.tabs.addTab(records_page, "今日紀錄")
        open_ledger.clicked.connect(lambda: self._open_path(self.ledger.xlsx_path))
        open_csv.clicked.connect(lambda: self._open_path(self.ledger.csv_path))

        for index in range(4):
            view = QPlainTextEdit("（待機中，尚無資料）")
            view.setObjectName("terminal")
            view.setReadOnly(True)
            view.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self.log_views.append(view)
            self.tabs.addTab(view, f"Log {index + 1}")

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.addWidget(title)
        layout.addLayout(self.startup)
        layout.addWidget(self.tabs)
        self.setCentralWidget(content)
        self.load_wifi.clicked.connect(self._load_wifi)
        self.scan_button.clicked.connect(self._refresh_ports)
        self.first_card.editingFinished.connect(self._first_card_changed)
        self.ssid.editingFinished.connect(self._save_settings)
        self.password.editingFinished.connect(self._save_settings)

    def _refresh_ports(self) -> None:
        ports = available_ports()
        for index, card in enumerate(self.cards):
            selected = self.config.ports[index] if self.config.ports[index] in ports else "未使用"
            card.set_ports(ports, selected)
            self.snapshots[index].port = selected
        duplicate_fields = self.ledger.duplicate_fields()
        suffix = f"；帳本重複：{', '.join(duplicate_fields)}" if duplicate_fields else ""
        self.ready_label.setText(f"找到 {len(ports)} 個 COM port{suffix}")

    def _load_wifi(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "載入 wifi.dat", str(self.root), "wifi.dat (wifi.dat)")
        if not path:
            return
        raw = Path(path).read_text(encoding="utf-8").rstrip("\r\n")
        if ";" not in raw:
            QMessageBox.warning(self, "格式錯誤", "wifi.dat 格式必須是 SSID;密碼")
            return
        self.ssid.setText(raw.split(";", 1)[0])
        self.password.setText(raw.split(";", 1)[1])
        self._save_settings()

    def start_slot(self, slot: int) -> None:
        index = slot - 1
        port = self.cards[index].port_combo.currentText()
        if port == "未使用":
            QMessageBox.warning(self, "無法開始", "請先為這個燒錄器選擇 COM port")
            return
        if any(i != index and card.port_combo.currentText() == port for i, card in enumerate(self.cards)):
            QMessageBox.warning(self, "COM port 重複", "同一個 COM port 不可分配給多個燒錄器")
            return
        if not validate_card_number(self.first_card.text()):
            QMessageBox.warning(self, "編號格式錯誤", "小卡編號必須以數字結尾，例如 F361")
            return
        duplicate_fields = self.ledger.duplicate_fields()
        if duplicate_fields:
            QMessageBox.warning(self, "帳本資料重複", f"請先處理重複欄位：{', '.join(duplicate_fields)}")
            return
        if not self.ssid.text() or ";" in self.ssid.text():
            QMessageBox.warning(self, "WiFi 設定錯誤", "請輸入 SSID，且 SSID 不可含分號")
            return
        try:
            firmware = discover_firmware(self.root / "firmware")
        except ValueError as exc:
            QMessageBox.warning(self, "啟動檢查失敗", str(exc))
            return
        self._save_settings()
        snapshot = SlotSnapshot(
            slot=slot,
            port=port,
            state=SlotState.RUNNING,
            message="正在連線...",
        )
        self.snapshots[index] = snapshot
        self._start_log(slot, port)
        self.cards[index].set_snapshot(snapshot)
        worker = ProvisionWorker(slot, self.root, port, None, self.ssid.text(), self.password.text(), firmware, self.ledger, self._allocate_card)
        worker.signals.log.connect(self._on_log)
        worker.signals.step.connect(self._on_step)
        worker.signals.finished.connect(self._on_finished)
        worker.signals.failed.connect(self._on_failed)
        self.workers[slot] = worker
        self.thread_pool.start(worker)

    def _allocate_card(self) -> str:
        with self.cards_lock:
            card = self.next_card
            self.next_card = next_card_number(card)
            self.cards_used += 1
            return card

    def _first_card_changed(self) -> None:
        value = self.first_card.text().strip()
        if self.cards_used == 0 and validate_card_number(value):
            self.next_card = value
        elif self.cards_used > 0 and value != self.next_card:
            QMessageBox.information(self, "編號已鎖定", "今日已開始配號，新的起始編號將於明日生效")
        self._save_settings()

    def _on_log(self, slot: int, message: str) -> None:
        snapshot = self.snapshots[slot - 1]
        snapshot.logs.append(message)
        view = self.log_views[slot - 1]
        view.appendPlainText(message)
        view.ensureCursorVisible()
        path = self.log_paths.get(slot)
        if path:
            with path.open("a", encoding="utf-8") as stream:
                stream.write(message + "\n")

    def _on_step(self, slot: int, step: str, progress: int, message: str) -> None:
        snapshot = self.snapshots[slot - 1]
        snapshot.step = ProvisionStep(step)
        snapshot.progress = progress
        snapshot.message = message
        snapshot.completed_steps.add(snapshot.step)
        if snapshot.step == ProvisionStep.MAC:
            match = message.split("=", 1)
            if len(match) == 2:
                snapshot.mac = match[1].strip()
                self._rename_log(slot, snapshot.mac)
        if snapshot.step == ProvisionStep.LEDGER and message.startswith("配號"):
            snapshot.card_number = message.split(" ", 1)[1].split("，", 1)[0]
        self.cards[slot - 1].set_snapshot(snapshot)

    def _on_finished(self, slot: int, record: object) -> None:
        snapshot = self.snapshots[slot - 1]
        if record is not None:
            snapshot.token = getattr(record, "token", None)
            snapshot.mac = getattr(record, "mac", snapshot.mac)
        snapshot.state = SlotState.WAITING
        snapshot.message = "驗收通過，請確認 LCD"
        snapshot.checks = ["token 一致", "MAC 一致", "ESP Wi-Fi OK"]
        self._write_log_result(slot, "PASS - 等待人工 LCD 確認")
        self.cards[slot - 1].set_snapshot(snapshot)
        self._refresh_records()

    def retry_slot(self, slot: int) -> None:
        index = slot - 1
        port = self.cards[index].port_combo.currentText()
        snapshot = self.snapshots[index]
        snapshot.state = SlotState.RUNNING
        snapshot.message = "重新開機驗收..."
        snapshot.error = None
        self.cards[index].set_snapshot(snapshot)
        worker = ProvisionWorker(slot, self.root, port, snapshot.card_number, self.ssid.text(), self.password.text(), None, self.ledger, self._allocate_card, retry=True)
        worker.token = snapshot.token
        worker.mac = snapshot.mac
        worker.signals.log.connect(self._on_log)
        worker.signals.step.connect(self._on_step)
        worker.signals.finished.connect(self._on_finished)
        worker.signals.failed.connect(self._on_failed)
        self.workers[slot] = worker
        self.thread_pool.start(worker)

    def complete_slot(self, slot: int) -> None:
        mac = self.snapshots[slot - 1].mac
        if mac:
            try:
                self.ledger.update_result(mac, "PASS")
            except PermissionError:
                self._on_log(slot, "Excel 目前開啟，CSV 已更新為 PASS，XLSX 待稍後同步")
        self._refresh_records()

    def _on_failed(self, slot: int, error: str) -> None:
        snapshot = self.snapshots[slot - 1]
        snapshot.state = SlotState.FAIL
        snapshot.error = error
        snapshot.message = "FAIL"
        self._write_log_result(slot, f"FAIL - {error}")
        if snapshot.mac:
            try:
                self.ledger.update_result(snapshot.mac, "FAIL", error)
            except PermissionError:
                self._on_log(slot, "帳本目前開啟，請關閉後重試 FAIL 同步")
        self.cards[slot - 1].set_snapshot(snapshot)
        self._refresh_records()

    def show_log(self, slot: int) -> None:
        self.tabs.setCurrentIndex(1 + slot)

    def _refresh_records(self) -> None:
        rows = [
            row for row in self.ledger.existing_records()
            if str(row.get("燒錄時間", ""))[:10] == date.today().isoformat()
        ]
        self.records.setRowCount(len(rows))
        passed = failed = 0
        for row_index, row in enumerate(rows):
            for column, header in enumerate(LEDGER_HEADERS):
                self.records.setItem(row_index, column, QTableWidgetItem(row.get(header, "")))
            if row.get("結果") == "PASS":
                passed += 1
            elif row.get("結果") == "FAIL":
                failed += 1
        self.records_summary.setText(f"今日 {len(rows)} 片 · PASS {passed} · FAIL {failed}")
        self.pass_label.setText(f"PASS {passed}")
        self.fail_label.setText(f"FAIL {failed}")

    def _save_settings(self) -> None:
        first = self.next_card if self.cards_used else self.first_card.text().strip()
        self.config = AppConfig(first, self.ssid.text(), self.password.text(), [card.port_combo.currentText() for card in self.cards])
        save_config(self.config_path, self.config)

    def _start_log(self, slot: int, port: str) -> None:
        logs = self.root / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        safe_port = port.replace("/", "_").replace("\\", "_")
        path = logs / f"{datetime.now():%Y%m%d-%H%M%S}_{safe_port}_pending.log"
        path.write_text(f"START {port}\n", encoding="utf-8")
        self.log_paths[slot] = path
        self.log_views[slot - 1].clear()
        self.log_views[slot - 1].appendPlainText(f"START {port}")

    def _rename_log(self, slot: int, identity: str) -> None:
        path = self.log_paths.get(slot)
        if not path or "_pending.log" not in path.name:
            return
        safe_identity = identity.replace("/", "_").replace("\\", "_")
        renamed = path.with_name(path.name.replace("_pending.log", f"_{safe_identity}.log"))
        path.rename(renamed)
        self.log_paths[slot] = renamed

    def _write_log_result(self, slot: int, result: str) -> None:
        path = self.log_paths.get(slot)
        if path:
            with path.open("a", encoding="utf-8") as stream:
                stream.write(result + "\n")

    @staticmethod
    def _open_path(path: Path) -> None:
        if path.exists():
            import os
            os.startfile(path)  # type: ignore[attr-defined]

    def closeEvent(self, event) -> None:  # noqa: N802
        self._save_settings()
        super().closeEvent(event)

    @staticmethod
    def _set_style() -> None:
        QApplication.instance().setStyleSheet(
            """
            QWidget { font-family: 'Microsoft JhengHei', 'Noto Sans TC', sans-serif; font-size: 13px; color: #1b1f24; }
            QMainWindow { background: #e6e9ed; }
            QLabel#titleBar { background: #f4f5f7; border: 1px solid #b9c0c9; padding: 8px 10px; font-weight: 700; }
            QLineEdit, QComboBox { background: white; border: 1px solid #cbd1d8; border-radius: 4px; padding: 5px 7px; }
            QPushButton { background: #f4f5f7; border: 1px solid #cbd1d8; border-radius: 4px; padding: 5px 9px; }
            QPushButton:hover { background: #e8edf4; }
            QPushButton#primaryButton { background: #2f6fdb; color: white; font-size: 16px; font-weight: 700; }
            QPushButton#successButton { background: #1f9d55; color: white; font-size: 16px; font-weight: 700; }
            QPushButton#secondaryButton { background: #fff; }
            QPushButton#linkButton { border: none; background: transparent; color: #2f6fdb; }
            QPushButton#subtleButton { background: rgba(255,255,255,.25); }
            QTabWidget::pane { border: 1px solid #cbd1d8; background: white; }
            QTabBar::tab { padding: 8px 16px; background: #f4f5f7; border: 1px solid transparent; }
            QTabBar::tab:selected { background: white; border-color: #cbd1d8; border-bottom-color: white; }
            QWidget#slotCard { background: white; border-radius: 8px; }
             QLabel#cardNumber { font-family: Consolas, monospace; font-size: 42px; font-weight: 800; min-width: 170px; }
             QLabel#bigStatus { font-size: 32px; font-weight: 800; }
            QLabel#steps { background: #eef0f3; border-radius: 3px; padding: 5px; color: #6b7380; }
            QLabel#prompt { background: #fff8e1; border: 1px dashed #e0a100; border-radius: 5px; padding: 7px; }
             QPlainTextEdit#terminal { background: #15181c; color: #c9d1d9; font-family: Consolas, monospace; padding: 12px; }
            QProgressBar { background: #eef0f3; border: none; border-radius: 4px; }
            QProgressBar::chunk { background: #2f6fdb; border-radius: 4px; }
            QTableWidget { border: 1px solid #d7dbe1; gridline-color: #e6e9ed; }
            QHeaderView::section { background: #f4f5f7; padding: 6px; border: none; }
            """
        )


def run(root: Path) -> int:
    app = QApplication.instance() or QApplication([])
    app.setFont(QFont("Microsoft JhengHei", 10))
    window = MainWindow(root)
    window.show()
    return app.exec()
