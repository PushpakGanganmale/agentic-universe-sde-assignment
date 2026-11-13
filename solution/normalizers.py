import re
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


IST = timezone(timedelta(hours=5, minutes=30))


def normalize_phone(value: str | None) -> str | None:
    """Return a canonical Indian mobile number, or None if invalid."""
    if value is None:
        return None

    digits = re.sub(r"\D", "", str(value).strip())

    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]

    if len(digits) != 10 or digits[0] not in "6789":
        return None

    return f"+91{digits}"


def parse_date(value: str | None) -> date | None:
    """Parse supported day-first and ISO date formats."""
    if value is None or not str(value).strip():
        return None

    value = str(value).strip()

    formats = (
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%d-%b-%Y",
    )

    for fmt in formats:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue

    return None


def parse_decimal(value: str | None) -> Decimal | None:
    """Parse non-negative currency/decimal values and round to 2 places."""
    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None

    # The generator may produce the garbled rupee symbol â‚¹.
    text = re.sub(r"^(?:₹|â‚¹|Rs\.?|INR)\s*", "", text, flags=re.IGNORECASE)
    text = text.replace(",", "").strip()

    try:
        amount = Decimal(text)
    except InvalidOperation:
        return None

    if not amount.is_finite() or amount < 0:
        return None

    return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def normalize_enum(value: str | None, allowed_values: list[str]) -> str | None:
    """Match an enum case-insensitively and return its lowercase value."""
    if value is None:
        return None

    normalized = str(value).strip().lower()
    allowed = {item.lower() for item in allowed_values}

    if not normalized or normalized not in allowed:
        return None

    return normalized


def parse_timestamp(value: str) -> datetime:
    """
    Parse an event timestamp and return an IST-aware datetime.

    Supported:
    - UTC timestamps ending in Z
    - ISO timestamps with timezone offsets
    - Naive timestamps, interpreted as IST
    """
    text = str(value).strip()
    if not text:
        raise ValueError("Timestamp is empty")

    if text.endswith("Z"):
        text = text[:-1] + "+00:00"

    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"Invalid timestamp: {value}") from exc

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=IST)

    return parsed.astimezone(IST)
