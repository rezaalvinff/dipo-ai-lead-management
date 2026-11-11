"""Phone number helpers. Numbers are stored in E.164 format (+628...)."""

import re

# Simulator numbers must live in a fictional range so they can never collide
# with a real customer's number.
SIMULATED_PHONE_PREFIX = "+62800"

_DIGITS = re.compile(r"\D+")


def normalize_phone(raw: str) -> str:
    """Normalize Indonesian-style numbers to E.164.

    "0812-3456-789" -> "+628123456789", "628123..." -> "+628123...".
    """
    digits = _DIGITS.sub("", raw or "")
    if not digits:
        raise ValueError("Phone number is empty")
    if digits.startswith("0"):
        digits = "62" + digits[1:]
    if not 8 <= len(digits) <= 15:
        raise ValueError("Phone number must have 8-15 digits")
    return "+" + digits


def mask_phone(phone: str) -> str:
    """Hide the middle of a phone number for logs: +6281****789."""
    if len(phone) <= 7:
        return "***"
    return phone[:5] + "*" * (len(phone) - 8) + phone[-3:]


def is_simulated_phone(phone: str) -> bool:
    return phone.startswith(SIMULATED_PHONE_PREFIX)
