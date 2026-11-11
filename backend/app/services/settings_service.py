"""Admin-editable settings with safe defaults defined in code."""

import string
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, NotFoundError
from app.models import AppSetting
from app.models.enums import ActorType
from app.services.audit_service import record_audit

ALLOWED_PLACEHOLDERS = {"nama", "domisili", "unit"}


@dataclass(frozen=True)
class SettingDef:
    key: str
    default: Any
    kind: type
    description: str


SETTING_DEFS = {
    d.key: d
    for d in [
        SettingDef(
            "qualification.closing_message",
            "Baik, akan segera saya lanjutkan ke tim sales untuk diberikan informasi promo dan "
            "penawarannya. Mohon ditunggu, terima kasih.",
            str,
            "Pesan penutup setelah data lengkap. Placeholder: {nama}, {domisili}, {unit}.",
        ),
        SettingDef(
            "qualification.human_handover_message",
            "Baik, saya hubungkan dengan tim kami. Mohon ditunggu sebentar, terima kasih.",
            str,
            "Pesan saat customer meminta berbicara dengan manusia.",
        ),
        SettingDef(
            "qualification.returning_customer_message",
            "Terima kasih sudah menghubungi kami kembali. Pesan Anda sudah kami teruskan ke tim "
            "sales, mohon ditunggu.",
            str,
            "Pesan untuk customer yang datanya sudah lengkap dan chat lagi.",
        ),
        SettingDef(
            "qualification.ai_unavailable_message",
            "Mohon maaf, sistem kami sedang sibuk. Pesan Anda sudah kami teruskan ke tim kami, "
            "mohon ditunggu.",
            str,
            "Pesan bila AI gagal berulang kali dan percakapan dialihkan ke admin.",
        ),
        SettingDef(
            "qualification.max_asks_per_field",
            2,
            int,
            "Berapa kali AI boleh menanyakan data yang sama sebelum dilewati (1-5).",
        ),
        SettingDef(
            "ai.enabled",
            True,
            bool,
            "Matikan untuk menghentikan semua balasan AI (semua chat masuk ke Admin Queue).",
        ),
    ]
}


def render_template(template: str, values: dict[str, str | None]) -> str:
    """Fill {nama}/{domisili}/{unit}; unknown values become empty, never crash."""

    class _Safe(dict):
        def __missing__(self, key: str) -> str:
            return ""

    safe = _Safe({k: (v or "") for k, v in values.items()})
    return " ".join(template.format_map(safe).split())


def _validate(defn: SettingDef, value: Any) -> Any:
    if defn.kind is bool:
        if not isinstance(value, bool):
            raise AppError("Nilai harus true/false", code="INVALID_SETTING")
        return value
    if defn.kind is int:
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 5:
            raise AppError("Nilai harus angka 1-5", code="INVALID_SETTING")
        return value
    if not isinstance(value, str) or not value.strip() or len(value) > 1000:
        raise AppError("Teks wajib diisi (maks. 1000 karakter)", code="INVALID_SETTING")
    for _, field_name, _, _ in string.Formatter().parse(value):
        if field_name is not None and field_name not in ALLOWED_PLACEHOLDERS:
            raise AppError(
                f"Placeholder {{{field_name}}} tidak dikenal. "
                "Gunakan: {nama}, {domisili}, {unit}",
                code="INVALID_PLACEHOLDER",
            )
    return value.strip()


class SettingsService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, key: str) -> Any:
        defn = SETTING_DEFS[key]
        row = await self.session.get(AppSetting, key)
        return defn.default if row is None else row.value

    async def list_all(self) -> list[dict]:
        rows = {r.key: r for r in await self.session.scalars(select(AppSetting))}
        return [
            {
                "key": d.key,
                "value": rows[d.key].value if d.key in rows else d.default,
                "default": d.default,
                "description": d.description,
                "is_default": d.key not in rows,
            }
            for d in SETTING_DEFS.values()
        ]

    async def set(self, key: str, value: Any, actor_user_id: uuid.UUID) -> Any:
        defn = SETTING_DEFS.get(key)
        if defn is None:
            raise NotFoundError("Pengaturan tidak dikenal", code="UNKNOWN_SETTING")
        value = _validate(defn, value)
        row = await self.session.get(AppSetting, key)
        old = defn.default if row is None else row.value
        if row is None:
            row = AppSetting(key=key, description=defn.description)
            self.session.add(row)
        row.value = value
        row.updated_by_user_id = actor_user_id
        record_audit(
            self.session,
            action="setting.updated",
            entity_type="setting",
            entity_id=key,
            actor_type=ActorType.USER,
            actor_user_id=actor_user_id,
            data={"old": old, "new": value},
        )
        await self.session.commit()
        return value

    async def reset(self, key: str, actor_user_id: uuid.UUID) -> Any:
        if key not in SETTING_DEFS:
            raise NotFoundError("Pengaturan tidak dikenal", code="UNKNOWN_SETTING")
        row = await self.session.get(AppSetting, key)
        if row is not None:
            await self.session.delete(row)
            record_audit(
                self.session,
                action="setting.reset",
                entity_type="setting",
                entity_id=key,
                actor_type=ActorType.USER,
                actor_user_id=actor_user_id,
            )
            await self.session.commit()
        return SETTING_DEFS[key].default
