from __future__ import annotations

import configparser
from dataclasses import dataclass
from pathlib import Path


@dataclass
class AppConfig:
    first_card_number: str = "F361"
    ssid: str = ""
    wifi_password: str = ""
    ports: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.ports is None:
            self.ports = ["未使用"] * 4


def load_config(path: Path) -> AppConfig:
    config = configparser.ConfigParser()
    if path.exists():
        config.read(path, encoding="utf-8")
    section = config["provisioner"] if "provisioner" in config else {}
    ports = [section.get(f"port_{index}", "未使用") for index in range(1, 5)]
    return AppConfig(
        first_card_number=section.get("first_card_number", "F361"),
        ssid=section.get("ssid", ""),
        wifi_password=section.get("wifi_password", ""),
        ports=ports,
    )


def save_config(path: Path, app_config: AppConfig) -> None:
    config = configparser.ConfigParser()
    config["provisioner"] = {
        "first_card_number": app_config.first_card_number,
        "ssid": app_config.ssid,
        "wifi_password": app_config.wifi_password,
        **{f"port_{index}": port for index, port in enumerate(app_config.ports, 1)},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        config.write(stream)
