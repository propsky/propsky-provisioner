from __future__ import annotations

import re


_CARD_NUMBER = re.compile(r"^(?P<prefix>.*?)(?P<number>\d+)$")


def next_card_number(value: str) -> str:
    """Increment the numeric suffix while preserving prefix and zero padding."""
    match = _CARD_NUMBER.fullmatch(value.strip())
    if not match:
        raise ValueError("小卡編號必須以數字結尾，例如 F361")
    number = match.group("number")
    return f"{match.group('prefix')}{int(number) + 1:0{len(number)}d}"


def validate_card_number(value: str) -> bool:
    return bool(_CARD_NUMBER.fullmatch(value.strip()))
