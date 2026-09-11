from datetime import datetime

from provisioner.ledger import Ledger
from provisioner.models import LedgerRecord
from provisioner.numbering import next_card_number, validate_card_number
from provisioner.provisioning import ProvisionService, RawReplClient


class FakeSerial:
    def __init__(self, incoming: bytes) -> None:
        self.incoming = bytearray(incoming)
        self.writes: list[bytes] = []
        self.is_open = True

    @property
    def in_waiting(self) -> int:
        return len(self.incoming)

    def write(self, data: bytes) -> int:
        self.writes.append(data)
        return len(data)

    def flush(self) -> None:
        pass

    def close(self) -> None:
        self.is_open = False

    def read(self, size: int) -> bytes:
        result = bytes(self.incoming[:size])
        del self.incoming[:size]
        return result


def test_card_number_preserves_prefix_and_padding() -> None:
    assert next_card_number("F009") == "F010"
    assert next_card_number("ABC99") == "ABC100"
    assert validate_card_number("F361")
    assert not validate_card_number("F")


def test_ledger_writes_csv_without_wifi_password(tmp_path) -> None:
    ledger = Ledger(tmp_path)
    record = LedgerRecord(
        card_number="F361",
        mac="9454C5536768",
        token="00000000-0000-4000-8000-000000000000",
        burned_at=datetime(2026, 9, 11, 12, 30),
        port="COM3",
        micropython="1.29.0",
        app_version="SP3_V0.31a",
        ssid="propsky",
        rssi="-50",
        mqtt="OK",
        result="PASS",
    )
    ledger.append_csv(record)
    content = ledger.csv_path.read_text(encoding="utf-8-sig")
    assert "9454C5536768" in content
    assert "password" not in content.lower()


def test_raw_repl_consumes_complete_response_in_one_chunk() -> None:
    client = RawReplClient("FAKE", timeout=0.1)
    client.serial = FakeSerial(b"OKhello\x04\x04>")  # type: ignore[assignment]

    assert client.execute("print('hello')") == "hello"
    assert client._read_buffer == bytearray()


def test_raw_repl_ignores_friendly_prompt_before_banner() -> None:
    client = RawReplClient("FAKE", timeout=0.1)
    fake = FakeSerial(b">>> raw REPL; CTRL-B to exit\r\n>")
    client.serial = fake  # type: ignore[assignment]

    client._enter_raw_repl()

    assert fake.writes == [b"\x03\x03\x01"]


def test_firmware_date_accepts_hyphenated_uname() -> None:
    class Client:
        def execute(self, source: str) -> str:
            return "(sysname='esp32', version='v1.29.0 on 2026-08-24')"

    assert ProvisionService._read_firmware(Client()) == "1.29.0 20260824"


def test_ledger_allows_repeat_burn_but_rejects_conflicting_identity(tmp_path) -> None:
    ledger = Ledger(tmp_path)
    base = LedgerRecord(
        card_number="F361",
        mac="AA11",
        token="token-a",
        burned_at=datetime(2026, 9, 11, 12, 30),
        port="COM3",
        micropython="1.29.0",
        app_version=None,
        ssid="propsky",
        rssi=None,
        mqtt="未確認",
        result="WAIT",
    )
    ledger.append_csv(base)
    ledger.append_csv(base)
    assert ledger.duplicate_fields() == []
    ledger.append_csv(LedgerRecord(**{**base.__dict__, "card_number": "F362", "burned_at": datetime.now()}))
    assert "MAC Address (CPUID)" in ledger.duplicate_fields()
