from __future__ import annotations

import base64
import hashlib
import re
import subprocess
import sys
import time
import uuid
from collections.abc import Callable, Iterable
from datetime import datetime
from pathlib import Path

import serial
from serial.tools import list_ports

from .firmware import FirmwareInfo
from .ledger import Ledger
from .models import LedgerRecord, ProvisionStep

LogCallback = Callable[[str], None]
StepCallback = Callable[[ProvisionStep, int, str], None]


class ProvisionError(RuntimeError):
    pass


def available_ports() -> list[str]:
    return [port.device for port in list_ports.comports()]


class RawReplClient:
    """Small raw-REPL client tailored to MicroPython's Ctrl-A protocol."""

    def __init__(self, port: str, baudrate: int = 115200, timeout: float = 2.0) -> None:
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.serial: serial.Serial | None = None

    def __enter__(self) -> RawReplClient:
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                self.serial = serial.Serial(self.port, self.baudrate, timeout=self.timeout, write_timeout=3)
                self.serial.dtr = False
                self.serial.rts = False
                time.sleep(0.2)
                self.serial.reset_input_buffer()
                self._enter_raw_repl()
                return self
            except (ProvisionError, serial.SerialException) as exc:
                last_error = exc
                if self.serial and self.serial.is_open:
                    self.serial.dtr = True
                    time.sleep(0.15)
                    self.serial.close()
                time.sleep(0.25)
        raise ProvisionError(f"無法進入 raw REPL（已重試 3 次）：{last_error}") from last_error

    def __exit__(self, *_: object) -> None:
        if self.serial and self.serial.is_open:
            self.serial.close()

    def execute(self, source: str, timeout: float | None = None) -> str:
        if not self.serial:
            raise ProvisionError("序列埠尚未開啟")
        self.serial.write(source.encode("utf-8") + b"\x04")
        self.serial.flush()
        deadline = time.monotonic() + (timeout or self.timeout)
        if self._read_exact(2, deadline) != b"OK":
            raise ProvisionError("raw REPL 回應格式錯誤")
        stdout = self._read_until(b"\x04", max(0, deadline - time.monotonic()))[:-1]
        stderr = self._read_until(b"\x04", max(0, deadline - time.monotonic()))[:-1]
        self._read_exact(1, deadline)  # raw REPL prompt
        if stderr:
            raise ProvisionError(stderr.decode("utf-8", "replace"))
        return stdout.decode("utf-8", "replace")

    def write_file(self, name: str, content: bytes) -> None:
        encoded = base64.b64encode(content).decode("ascii")
        self.execute("import ubinascii\n_f=open(%r,'wb')" % name)
        for offset in range(0, len(encoded), 1024):
            self.execute("_f.write(ubinascii.a2b_base64(%r))" % encoded[offset : offset + 1024])
        self.execute("_f.close()")

    def sha256(self, name: str) -> str:
        output = self.execute(
            "import hashlib\nprint(hashlib.sha256(open(%r,'rb').read()).hexdigest())" % name
        )
        matches = re.findall(r"[0-9a-f]{64}", output)
        if not matches:
            raise ProvisionError(f"無法取得 {name} 的 sha256")
        return matches[-1]

    def reset(self) -> None:
        # machine.reset() deliberately never sends the raw-REPL terminator.
        assert self.serial
        self.serial.write(b"import machine\nmachine.reset()\x04")
        self.serial.flush()
        time.sleep(0.1)

    def _enter_raw_repl(self) -> None:
        assert self.serial
        self.serial.write(b"\x03\x03\x01")
        self.serial.flush()
        output = self._read_until(b">", 3)
        if b"raw REPL" not in output and b"raw repl" not in output.lower():
            raise ProvisionError("無法進入 raw REPL")

    def _read_until(self, marker: bytes, timeout: float) -> bytes:
        assert self.serial
        deadline = time.monotonic() + timeout
        received = bytearray()
        while time.monotonic() < deadline:
            chunk = self.serial.read(256)
            if chunk:
                received.extend(chunk)
                if marker in received:
                    return bytes(received)
        raise ProvisionError(f"序列埠逾時：{self.port}")

    def _read_exact(self, size: int, deadline: float) -> bytes:
        assert self.serial
        received = bytearray()
        while len(received) < size and time.monotonic() < deadline:
            received.extend(self.serial.read(size - len(received)))
        if len(received) != size:
            raise ProvisionError(f"序列埠逾時：{self.port}")
        return bytes(received)


class EsptoolRunner:
    def __init__(self, log: LogCallback) -> None:
        self.log = log

    def flash(self, port: str, firmware: FirmwareInfo) -> None:
        commands = [
            [sys.executable, "-m", "esptool", "--port", port, "erase-flash"],
            [sys.executable, "-m", "esptool", "--port", port, "write-flash", "0x1000", str(firmware.path)],
        ]
        for command in commands:
            self.log("$ " + " ".join(command))
            completed = subprocess.run(command, capture_output=True, text=True, check=False)
            for line in (completed.stdout + completed.stderr).splitlines():
                self.log(line)
            if completed.returncode != 0:
                raise ProvisionError(f"esptool 失敗（{completed.returncode}）：{command[-1]}")


class ProvisionService:
    def __init__(
        self,
        root: Path,
        ledger: Ledger,
        log: LogCallback,
        step: StepCallback,
    ) -> None:
        self.root = root
        self.ledger = ledger
        self.log = log
        self.step = step

    def run(
        self,
        port: str,
        card_number: str | None,
        ssid: str,
        wifi_password: str,
        firmware: FirmwareInfo,
        allocate_card: Callable[[], str],
    ) -> LedgerRecord:
        if ";" in ssid:
            raise ProvisionError("SSID 不可含有分號")
        payload_files = self._payload_files()
        token = str(uuid.uuid4())
        start = datetime.now()
        self.step(ProvisionStep.CONNECT, 5, f"開啟 {port}，進入 raw REPL")
        self.log(f"開啟 {port}，進入 raw REPL")
        try:
            client = RawReplClient(port)
            with client:
                firmware_version = self._read_firmware(client)
                if firmware_version and (firmware.version not in firmware_version or firmware.date not in firmware_version):
                    self.log("韌體版本不符，執行 erase-flash + write-flash")
                    EsptoolRunner(self.log).flash(port, firmware)
                    raise ProvisionError("韌體已重燒，請重新按開始完成流程")

                self.step(ProvisionStep.FIRMWARE, 12, f"MicroPython {firmware_version or firmware.version}")
                mac = self._read_mac(client)
                self.step(ProvisionStep.MAC, 20, f"MAC = {mac}")
                existing = self.ledger.find_by_mac(mac)
                if existing:
                    card_number = existing.get("小卡編號") or card_number
                    token = existing.get("UUID (token)") or token
                    self.log(f"帳本已存在 MAC，沿用小卡編號 {card_number} 與 token")

                self.step(ProvisionStep.CLEAN, 28, "清空檔案系統，保留 boot.py")
                client.execute(
                    "import os\n[os.remove(f) for f in os.listdir() if f != 'boot.py']"
                )
                self.step(ProvisionStep.UPLOAD, 35, f"上傳 {len(payload_files) + 2} 個檔案")
                for index, path in enumerate(payload_files):
                    client.write_file(path.name, path.read_bytes())
                    self.log(f"上傳 {path.name} ... {path.stat().st_size} bytes")
                    self.step(ProvisionStep.UPLOAD, 35 + int((index + 1) / max(1, len(payload_files) + 2) * 25), path.name)
                client.write_file("wifi.dat", f"{ssid};{wifi_password}".encode())
                client.write_file("token.dat", token.encode())

                self.step(ProvisionStep.VERIFY, 65, "驗證檔案 sha256")
                files_to_verify = [*payload_files, Path("wifi.dat"), Path("token.dat")]
                local_contents = {
                    path.name: (path.read_bytes() if path.name not in {"wifi.dat", "token.dat"} else
                                (f"{ssid};{wifi_password}" if path.name == "wifi.dat" else token).encode())
                    for path in files_to_verify
                }
                for path in files_to_verify:
                    local_hash = hashlib.sha256(local_contents[path.name]).hexdigest()
                    if client.sha256(path.name) != local_hash:
                        self.log(f"sha256 不符，重傳 {path.name}")
                        client.write_file(path.name, local_contents[path.name])
                        if client.sha256(path.name) != local_hash:
                            raise ProvisionError(f"sha256 驗證失敗：{path.name}")

                if not existing and not card_number:
                    card_number = allocate_card()
                self.step(ProvisionStep.LEDGER, 78, f"配號 {card_number or '沿用'}，寫入帳本")
                record = LedgerRecord(
                    card_number=card_number,
                    mac=mac,
                    token=token,
                    burned_at=start,
                    port=port,
                    micropython=firmware.version,
                    app_version=None,
                    ssid=ssid,
                    rssi=None,
                    mqtt="未確認",
                    result="WAIT",
                    note="",
                )
                self.ledger.append_csv(record)
                try:
                    self.ledger.sync_xlsx(record)
                except PermissionError:
                    self.log("Excel 目前開啟，已先寫入 CSV，請關閉 Excel 後同步")

                self.step(ProvisionStep.BOOT, 85, "重開機，等待 ESP Wi-Fi OK（60 秒）")
                client.reset()
                boot_log = self._wait_for_boot(client)
                if "Traceback" in boot_log:
                    raise ProvisionError("啟動 log 出現 Traceback")
                if "ESP Wi-Fi OK" not in boot_log:
                    raise ProvisionError("60 秒內沒有 ESP Wi-Fi OK")
                expected_token = token
                token_match = re.search(r"Get token:\s*([0-9a-f-]{36})", boot_log, re.I)
                mac_match = re.search(r"My MAC Address:\s*([0-9A-F]{12,16})", boot_log, re.I)
                if not token_match or token_match.group(1).lower() != expected_token.lower():
                    raise ProvisionError("驗收 token 不一致")
                if not mac_match or mac_match.group(1).upper() != mac.upper():
                    raise ProvisionError("驗收 MAC 不一致")
                details = self._boot_details(boot_log)
                try:
                    self.ledger.update_details(mac, **details)
                except PermissionError:
                    self.log("Excel 目前開啟，已保留 CSV 驗收資料，請關閉 Excel 後同步")
                self.step(ProvisionStep.LCD, 100, "等待人工確認 LCD")
                return record
        except serial.SerialException as exc:
            raise ProvisionError(f"COM port 被佔用或無法開啟：{port} ({exc})") from exc

    def retry_boot(self, port: str) -> None:
        self.log(f"重新開機驗收 {port}（不重傳檔案、不寫新紀錄）")
        with RawReplClient(port) as client:
            client.reset()
            boot_log = self._wait_for_boot(client)
            if "Traceback" in boot_log:
                raise ProvisionError("啟動 log 出現 Traceback")
            if "ESP Wi-Fi OK" not in boot_log:
                raise ProvisionError("60 秒內沒有 ESP Wi-Fi OK")

    def _payload_files(self) -> list[Path]:
        payload = self.root / "payload"
        if not payload.exists():
            raise ProvisionError("找不到 payload/ 資料夾")
        ignored = {"boot.py", "token.dat", "wifi.dat"}
        files = sorted(path for path in payload.iterdir() if path.is_file() and path.name not in ignored)
        if not files:
            raise ProvisionError("payload/ 不可為空")
        return files

    @staticmethod
    def _read_firmware(client: RawReplClient) -> str | None:
        output = client.execute("import os\nprint(os.uname())")
        match = re.search(r"v(\d+\.\d+\.\d+)", output)
        if not match:
            return None
        date = re.search(r"20\d{6}", output)
        return f"{match.group(1)} {date.group(0)}" if date else match.group(1)

    @staticmethod
    def _read_mac(client: RawReplClient) -> str:
        output = client.execute("import machine\nprint(machine.unique_id().hex().upper())")
        matches = re.findall(r"\b[0-9A-F]{12,16}\b", output)
        if not matches:
            raise ProvisionError("無法讀取 machine.unique_id()")
        return matches[-1]

    def _wait_for_boot(self, client: RawReplClient) -> str:
        assert client.serial
        deadline = time.monotonic() + 60
        data = bytearray()
        while time.monotonic() < deadline:
            chunk = client.serial.read(512)
            if chunk:
                text = chunk.decode("utf-8", "replace")
                self.log(text.rstrip())
                data.extend(chunk)
                if b"Traceback" in data or (
                    b"ESP Wi-Fi OK" in data
                    and re.search(rb"Get token:\s*[0-9a-f-]{36}", data, re.I)
                    and re.search(rb"My MAC Address:\s*[0-9A-F]{12,16}", data, re.I)
                ):
                    break
        return data.decode("utf-8", "replace")

    @staticmethod
    def _boot_details(log: str) -> dict[str, str]:
        version = re.search(r"版本為:\s*([^\s\r\n]+)", log)
        rssi = re.search(r"WiFi Signal Strength:\s*(-?\d+)\s*dBm", log)
        return {
            "app_version": version.group(1) if version else "",
            "rssi": rssi.group(1) if rssi else "",
            "mqtt": "OK" if "MainStatus: STANDBY_MQTT" in log else "未確認",
        }
