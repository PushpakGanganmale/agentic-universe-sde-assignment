from datetime import date
from decimal import Decimal

import pytest

from solution.normalizers import (
    normalize_phone,
    parse_date,
    parse_decimal,
    normalize_enum,
    parse_timestamp,
)


@pytest.mark.parametrize("raw", [
    "9876543210",
    "+919876543210",
    "+91 98765 43210",
    "09876543210",
    "91-98765-43210",
    "(+91) 9876543210",
])
def test_valid_phone_formats(raw):
    assert normalize_phone(raw) == "+919876543210"


@pytest.mark.parametrize("raw", [
    None, "", "N/A", "123456789", "5223456789",
    "022-2345-6789", "+1 415 555 0134",
])
def test_invalid_phone_formats(raw):
    assert normalize_phone(raw) is None


@pytest.mark.parametrize("raw, expected", [
    ("2026-11-23", date(2026, 11, 23)),
    ("27/10/2026", date(2026, 10, 27)),
    ("11-12-2026", date(2026, 12, 11)),
    ("21-Nov-2026", date(2026, 11, 21)),
])
def test_supported_dates(raw, expected):
    assert parse_date(raw) == expected


@pytest.mark.parametrize("raw", [
    "31/02/2026", "soon", "2026-13-01", "TBD", ""
])
def test_invalid_dates(raw):
    assert parse_date(raw) is None


@pytest.mark.parametrize("raw, expected", [
    ("27554.00", Decimal("27554.00")),
    ("₹27,554", Decimal("27554.00")),
    ("â‚¹27,554", Decimal("27554.00")),
    ("Rs. 1200", Decimal("1200.00")),
    ("INR 25301.4", Decimal("25301.40")),
    ("1,234.567", Decimal("1234.57")),
])
def test_valid_decimals(raw, expected):
    assert parse_decimal(raw) == expected


@pytest.mark.parametrize("raw", [
    "N/A", "-", "twelve thousand", "-500", ""
])
def test_invalid_decimals(raw):
    assert parse_decimal(raw) is None


def test_enum_normalization():
    allowed = ["en", "hi", "ta", "kn", "te", "mr"]
    assert normalize_enum(" HI ", allowed) == "hi"
    assert normalize_enum("En", allowed) == "en"
    assert normalize_enum("Hindi", allowed) is None
    assert normalize_enum("", allowed) is None


def test_timestamp_utc_converts_to_ist():
    result = parse_timestamp("2026-10-01T05:26:10Z")
    assert result.isoformat() == "2026-10-01T10:56:10+05:30"


def test_timestamp_offset():
    result = parse_timestamp("2026-10-01T10:40:19+05:30")
    assert result.isoformat() == "2026-10-01T10:40:19+05:30"


def test_naive_timestamp_is_ist():
    result = parse_timestamp("2026-10-01 09:15:55")
    assert result.isoformat() == "2026-10-01T09:15:55+05:30"
