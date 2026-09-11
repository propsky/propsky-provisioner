from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class SlotState(StrEnum):
    IDLE = "idle"
    RUNNING = "run"
    WAITING = "wait"
    PASS = "pass"
    FAIL = "fail"


class ProvisionStep(StrEnum):
    CONNECT = "連線"
    FIRMWARE = "韌體"
    MAC = "MAC"
    CLEAN = "清空"
    UPLOAD = "上傳"
    VERIFY = "驗證"
    LEDGER = "帳本"
    BOOT = "開機"
    LCD = "LCD"


STEPS = tuple(ProvisionStep)


@dataclass
class SlotSnapshot:
    slot: int
    port: str = "未使用"
    state: SlotState = SlotState.IDLE
    card_number: str | None = None
    mac: str | None = None
    token: str | None = None
    step: ProvisionStep | None = None
    completed_steps: set[ProvisionStep] = field(default_factory=set)
    message: str = "換上新板後按「開始」"
    progress: int = 0
    checks: list[str] = field(default_factory=list)
    error: str | None = None
    logs: list[str] = field(default_factory=list)
    started_at: datetime | None = None


@dataclass(frozen=True)
class LedgerRecord:
    card_number: str | None
    mac: str | None
    token: str | None
    burned_at: datetime
    port: str
    micropython: str | None
    app_version: str | None
    ssid: str | None
    rssi: str | None
    mqtt: str | None
    result: str
    note: str = ""


LEDGER_HEADERS = (
    "小卡編號",
    "MAC Address (CPUID)",
    "UUID (token)",
    "燒錄時間",
    "Port",
    "MicroPython",
    "程式版本",
    "SSID",
    "RSSI",
    "MQTT",
    "結果",
    "備註",
)
