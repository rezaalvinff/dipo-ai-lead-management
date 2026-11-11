"""Knowledge base management + the approved context given to the AI."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.adapters.ai.base import KnowledgeContext
from app.core.errors import ConflictError, NotFoundError
from app.models import KnowledgeBaseArticle, VehicleModel, VehicleVariant
from app.models.enums import ActorType, KnowledgeStatus
from app.services.audit_service import record_audit

MAX_CONTEXT_CHARS = 12000
CATEGORY_HEADINGS = {
    "promo": "PROMO",
    "dp": "DP / UANG MUKA",
    "installment": "ANGSURAN / KREDIT",
    "price": "HARGA",
    "spec": "SPESIFIKASI",
    "faq": "FAQ",
    "dealer": "INFORMASI DEALER",
    "policy": "KEBIJAKAN",
}
APPROVAL_FIELDS = {"status", "approved_by_user_id", "approved_at"}

KnowledgeItem = VehicleModel | VehicleVariant | KnowledgeBaseArticle


def format_rupiah(value: Decimal | int | None) -> str | None:
    if value is None:
        return None
    return "Rp " + f"{int(value):,}".replace(",", ".")


def _apply_approval(item: KnowledgeItem, status: str | None, actor: uuid.UUID, changed: bool):
    """Content changes send an approved item back to draft unless re-approved now."""
    if status is None and changed and item.status == KnowledgeStatus.APPROVED:
        status = KnowledgeStatus.DRAFT
    if status is None:
        return
    item.status = status
    if status == KnowledgeStatus.APPROVED:
        item.approved_by_user_id = actor
        item.approved_at = datetime.now(UTC)
    else:
        item.approved_by_user_id = None
        item.approved_at = None


class KnowledgeService:
    def __init__(self, session: AsyncSession):
        self.session = session

    # ------------------------------------------------------------------ CRUD
    async def _get(self, model: type, item_id: uuid.UUID, label: str):
        item = await self.session.get(model, item_id)
        if item is None:
            raise NotFoundError(f"{label} tidak ditemukan", code="KNOWLEDGE_NOT_FOUND")
        return item

    async def create(self, model: type, data: dict[str, Any], actor: uuid.UUID) -> KnowledgeItem:
        status = data.pop("status", None) or KnowledgeStatus.DRAFT
        if model is VehicleModel:
            exists = await self.session.scalar(
                select(VehicleModel.id).where(VehicleModel.name == data["name"])
            )
            if exists:
                raise ConflictError("Model dengan nama ini sudah ada", code="MODEL_EXISTS")
        if model is VehicleVariant:
            await self._get(VehicleModel, data["vehicle_model_id"], "Model kendaraan")
        item = model(**data)
        _apply_approval(item, status, actor, changed=False)
        self.session.add(item)
        await self.session.flush()
        self._audit("knowledge.created", item, actor, {"status": item.status})
        await self.session.commit()
        await self.session.refresh(item)
        return item

    async def update(
        self, model: type, item_id: uuid.UUID, data: dict[str, Any], actor: uuid.UUID, label: str
    ) -> KnowledgeItem:
        item = await self._get(model, item_id, label)
        status = data.pop("status", None)
        changed = False
        for key, value in data.items():
            if getattr(item, key) != value:
                setattr(item, key, value)
                changed = True
        _apply_approval(item, status, actor, changed)
        self._audit(
            "knowledge.updated", item, actor, {"fields": sorted(data), "status": item.status}
        )
        await self.session.commit()
        await self.session.refresh(item)
        return item

    async def delete(self, model: type, item_id: uuid.UUID, actor: uuid.UUID, label: str) -> None:
        item = await self._get(model, item_id, label)
        self._audit("knowledge.deleted", item, actor, {"title": self._title(item)})
        await self.session.delete(item)
        await self.session.commit()

    async def list_models(self, status: str | None = None) -> list[VehicleModel]:
        query = select(VehicleModel).order_by(VehicleModel.sort_order, VehicleModel.name)
        if status:
            query = query.where(VehicleModel.status == status)
        return list(await self.session.scalars(query))

    async def list_variants(self, vehicle_model_id: uuid.UUID) -> list[VehicleVariant]:
        await self._get(VehicleModel, vehicle_model_id, "Model kendaraan")
        return list(
            await self.session.scalars(
                select(VehicleVariant)
                .where(VehicleVariant.vehicle_model_id == vehicle_model_id)
                .order_by(VehicleVariant.sort_order, VehicleVariant.name)
            )
        )

    async def list_articles(
        self,
        category: str | None = None,
        status: str | None = None,
        vehicle_model_id: uuid.UUID | None = None,
    ) -> list[KnowledgeBaseArticle]:
        query = select(KnowledgeBaseArticle).order_by(
            KnowledgeBaseArticle.category, KnowledgeBaseArticle.title
        )
        if category:
            query = query.where(KnowledgeBaseArticle.category == category)
        if status:
            query = query.where(KnowledgeBaseArticle.status == status)
        if vehicle_model_id:
            query = query.where(KnowledgeBaseArticle.vehicle_model_id == vehicle_model_id)
        return list(await self.session.scalars(query))

    @staticmethod
    def _title(item: KnowledgeItem) -> str:
        return getattr(item, "title", None) or getattr(item, "name", "")

    def _audit(self, action: str, item: KnowledgeItem, actor: uuid.UUID, data: dict) -> None:
        record_audit(
            self.session,
            action=action,
            entity_type=item.__tablename__,
            entity_id=item.id,
            actor_type=ActorType.USER,
            actor_user_id=actor,
            data=data,
        )

    # ------------------------------------------------------- AI context
    async def vehicle_catalog(self) -> dict[str, list[str]]:
        rows = await self.session.scalars(
            select(VehicleModel)
            .where(
                VehicleModel.status == KnowledgeStatus.APPROVED, VehicleModel.is_active.is_(True)
            )
            .order_by(VehicleModel.sort_order, VehicleModel.name)
        )
        return {m.name: list(m.aliases or []) for m in rows}

    async def vehicle_model_ids(self) -> dict[str, uuid.UUID]:
        rows = await self.session.execute(
            select(VehicleModel.name, VehicleModel.id).where(
                VehicleModel.status == KnowledgeStatus.APPROVED, VehicleModel.is_active.is_(True)
            )
        )
        return {name: model_id for name, model_id in rows}

    async def build_context(self, focus_vehicle: str | None = None) -> KnowledgeContext:
        """Only APPROVED + active + currently valid knowledge reaches the AI."""
        now = datetime.now(UTC)
        models = list(
            await self.session.scalars(
                select(VehicleModel)
                .options(selectinload(VehicleModel.variants))
                .where(
                    VehicleModel.status == KnowledgeStatus.APPROVED,
                    VehicleModel.is_active.is_(True),
                )
                .order_by(VehicleModel.sort_order, VehicleModel.name)
            )
        )
        articles = list(
            await self.session.scalars(
                select(KnowledgeBaseArticle)
                .where(
                    KnowledgeBaseArticle.status == KnowledgeStatus.APPROVED,
                    KnowledgeBaseArticle.is_active.is_(True),
                    or_(
                        KnowledgeBaseArticle.valid_from.is_(None),
                        KnowledgeBaseArticle.valid_from <= now,
                    ),
                    or_(
                        KnowledgeBaseArticle.valid_until.is_(None),
                        KnowledgeBaseArticle.valid_until >= now,
                    ),
                )
                .order_by(KnowledgeBaseArticle.category, KnowledgeBaseArticle.title)
            )
        )
        model_names = {m.id: m.name for m in models}

        entries: list[tuple[str, str, str]] = []
        for model in models:
            if model.description:
                entries.append(("spec", model.name, model.description))
            for variant in model.variants:
                if variant.status != KnowledgeStatus.APPROVED or not variant.is_active:
                    continue
                label = f"{model.name} {variant.name}"
                specs = "; ".join(f"{k}: {v}" for k, v in (variant.specs or {}).items())
                extra = ", ".join(x for x in (variant.transmission, variant.fuel_type) if x)
                if specs or extra:
                    entries.append(("spec", label, "; ".join(x for x in (extra, specs) if x)))
                price = format_rupiah(variant.price_otr)
                if price:
                    note = f" ({variant.price_note})" if variant.price_note else ""
                    entries.append(("price", f"harga {label}", f"{price}{note}"))
        for article in articles:
            title = article.title
            if article.vehicle_model_id in model_names:
                title = f"{title} [{model_names[article.vehicle_model_id]}]"
            content = article.content
            if article.valid_until:
                content += f" (berlaku s/d {article.valid_until:%d-%m-%Y})"
            entries.append((article.category, title, content))

        if focus_vehicle:
            focus = focus_vehicle.lower()
            entries.sort(key=lambda e: 0 if focus in e[1].lower() else 1)

        lines: list[str] = []
        size = 0
        for category in CATEGORY_HEADINGS:
            group = [e for e in entries if e[0] == category]
            if not group:
                continue
            block = [f"## {CATEGORY_HEADINGS[category]}"] + [f"- {t}: {c}" for _, t, c in group]
            text = "\n".join(block)
            if size + len(text) > MAX_CONTEXT_CHARS:
                break
            lines.append(text)
            size += len(text)
        missing = [h for c, h in CATEGORY_HEADINGS.items() if not any(e[0] == c for e in entries)]
        if missing:
            lines.append("Tidak ada informasi resmi untuk: " + ", ".join(missing) + ".")

        catalog = {m.name: list(m.aliases or []) for m in models}
        return KnowledgeContext(
            vehicle_models=list(catalog),
            vehicle_catalog=catalog,
            text="\n\n".join(lines),
            categories_available={e[0] for e in entries},
            entries=entries,
        )
