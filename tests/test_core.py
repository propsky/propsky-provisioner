from datetime import datetime

from provisioner.ledger import Ledger
from provisioner.models import LedgerRecord
from provisioner.numbering import next_card_number, validate_card_number


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
