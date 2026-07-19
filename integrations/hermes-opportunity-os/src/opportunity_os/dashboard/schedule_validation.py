"""Shared strict validation for the only schedule values Task 6 may mutate."""

from __future__ import annotations

import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from opportunity_os.sanitizer import contains_secret


_CRON_CHARS = re.compile(r"^[0-9*/,-]+$")
_TZ_NAME = re.compile(r"^[A-Za-z0-9._+-]+(?:/[A-Za-z0-9._+-]+)+$")
_FIELD_BOUNDS = ((0, 59), (0, 23), (1, 31), (1, 12), (0, 7))


def _number(value: str, lower: int, upper: int) -> int:
    if not value.isascii() or not value.isdigit():
        raise ValueError("cron contains a non-numeric token")
    number = int(value)
    if not lower <= number <= upper:
        raise ValueError("cron token is outside its field range")
    return number


def _validate_cron_part(part: str, lower: int, upper: int) -> None:
    if not part or _CRON_CHARS.fullmatch(part) is None:
        raise ValueError("cron contains forbidden syntax")
    for item in part.split(","):
        if not item:
            raise ValueError("cron contains an empty list item")
        pieces = item.split("/")
        if len(pieces) > 2:
            raise ValueError("cron contains multiple step separators")
        base = pieces[0]
        if len(pieces) == 2:
            step = pieces[1]
            if not step.isascii() or not step.isdigit() or not 1 <= int(step) <= upper:
                raise ValueError("cron step is invalid")
        if base == "*":
            continue
        bounds = base.split("-")
        if len(bounds) == 1:
            _number(bounds[0], lower, upper)
        elif len(bounds) == 2:
            start = _number(bounds[0], lower, upper)
            end = _number(bounds[1], lower, upper)
            if start > end:
                raise ValueError("cron range is reversed")
        else:
            raise ValueError("cron range is invalid")


def normalize_cron(value: object) -> str:
    if not isinstance(value, str) or contains_secret(value):
        raise ValueError("cron must be a safe five-field expression")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ValueError("cron contains a control character")
    fields = value.split()
    if len(fields) != 5:
        raise ValueError("cron must contain exactly five fields")
    for field, (lower, upper) in zip(fields, _FIELD_BOUNDS, strict=True):
        _validate_cron_part(field, lower, upper)
    return " ".join(fields)


def normalize_timezone(value: object) -> str:
    if (
        not isinstance(value, str)
        or value != value.strip()
        or contains_secret(value)
        or _TZ_NAME.fullmatch(value) is None
    ):
        raise ValueError("tz must be a canonical IANA timezone")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ValueError("tz contains a control character")
    try:
        zone = ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as error:
        raise ValueError("tz must be a known IANA timezone") from error
    if zone.key != value:
        raise ValueError("tz must use its normalized IANA key")
    return zone.key


def normalize_schedule(cron: object, tz: object) -> tuple[str, str]:
    return normalize_cron(cron), normalize_timezone(tz)
