from datetime import UTC, datetime, timedelta, timezone

from pydantic import BaseModel, ConfigDict

# WIB = UTC+7, no daylight saving.
WIB = timezone(timedelta(hours=7), "WIB")


def to_wib_text(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(WIB).strftime("%d/%m/%Y %H:%M:%S WIB")


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)
