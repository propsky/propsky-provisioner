from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FirmwareInfo:
    path: Path
    version: str
    date: str


def discover_firmware(directory: Path) -> FirmwareInfo:
    images = sorted(directory.glob("*.bin"))
    if len(images) != 1:
        raise ValueError(f"firmware/ 必須剛好有一個 .bin，目前有 {len(images)} 個")
    image = images[0]
    match = re.search(r"(?P<date>20\d{6}).*?v?(?P<version>\d+\.\d+\.\d+)", image.name, re.I)
    if not match:
        raise ValueError(f"無法從韌體檔名解析日期與版本：{image.name}")
    return FirmwareInfo(image, match.group("version"), match.group("date"))
