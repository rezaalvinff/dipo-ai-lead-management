"""Knowledge base management. Admin edits/approves; supervisor can read."""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session, require_roles
from app.models import KnowledgeBaseArticle, User, VehicleModel, VehicleVariant
from app.models.enums import RoleName
from app.schemas.knowledge import (
    ArticleCreate,
    ArticleOut,
    ArticleUpdate,
    KnowledgePreview,
    VariantCreate,
    VariantOut,
    VariantUpdate,
    VehicleModelCreate,
    VehicleModelOut,
    VehicleModelUpdate,
)
from app.services.knowledge_service import KnowledgeService

router = APIRouter(prefix="/knowledge", tags=["knowledge"])
reader = require_roles(RoleName.ADMIN, RoleName.SUPERVISOR)
editor = require_roles(RoleName.ADMIN)


def _payload(body, *, exclude_unset: bool = True) -> dict:
    return body.model_dump(exclude_unset=exclude_unset)


# ---------------------------------------------------------------- vehicle models
@router.get("/vehicle-models", response_model=list[VehicleModelOut])
async def list_models(
    status: str | None = Query(default=None, pattern="^(draft|approved|archived)$"),
    _: User = Depends(reader),
    session: AsyncSession = Depends(get_session),
):
    return await KnowledgeService(session).list_models(status)


@router.post("/vehicle-models", response_model=VehicleModelOut, status_code=201)
async def create_model(
    body: VehicleModelCreate,
    user: User = Depends(editor),
    session: AsyncSession = Depends(get_session),
):
    return await KnowledgeService(session).create(
        VehicleModel, _payload(body, exclude_unset=False), user.id
    )


@router.patch("/vehicle-models/{item_id}", response_model=VehicleModelOut)
async def update_model(
    item_id: uuid.UUID,
    body: VehicleModelUpdate,
    user: User = Depends(editor),
    session: AsyncSession = Depends(get_session),
):
    return await KnowledgeService(session).update(
        VehicleModel, item_id, _payload(body), user.id, "Model kendaraan"
    )


@router.delete("/vehicle-models/{item_id}", status_code=204)
async def delete_model(
    item_id: uuid.UUID, user: User = Depends(editor), session: AsyncSession = Depends(get_session)
) -> None:
    await KnowledgeService(session).delete(VehicleModel, item_id, user.id, "Model kendaraan")


# ---------------------------------------------------------------- variants
@router.get("/vehicle-models/{model_id}/variants", response_model=list[VariantOut])
async def list_variants(
    model_id: uuid.UUID, _: User = Depends(reader), session: AsyncSession = Depends(get_session)
):
    return await KnowledgeService(session).list_variants(model_id)


@router.post("/vehicle-models/{model_id}/variants", response_model=VariantOut, status_code=201)
async def create_variant(
    model_id: uuid.UUID,
    body: VariantCreate,
    user: User = Depends(editor),
    session: AsyncSession = Depends(get_session),
):
    data = _payload(body, exclude_unset=False) | {"vehicle_model_id": model_id}
    return await KnowledgeService(session).create(VehicleVariant, data, user.id)


@router.patch("/variants/{item_id}", response_model=VariantOut)
async def update_variant(
    item_id: uuid.UUID,
    body: VariantUpdate,
    user: User = Depends(editor),
    session: AsyncSession = Depends(get_session),
):
    return await KnowledgeService(session).update(
        VehicleVariant, item_id, _payload(body), user.id, "Varian"
    )


@router.delete("/variants/{item_id}", status_code=204)
async def delete_variant(
    item_id: uuid.UUID, user: User = Depends(editor), session: AsyncSession = Depends(get_session)
) -> None:
    await KnowledgeService(session).delete(VehicleVariant, item_id, user.id, "Varian")


# ---------------------------------------------------------------- articles
@router.get("/articles", response_model=list[ArticleOut])
async def list_articles(
    category: str | None = Query(default=None),
    status: str | None = Query(default=None, pattern="^(draft|approved|archived)$"),
    vehicle_model_id: uuid.UUID | None = None,
    _: User = Depends(reader),
    session: AsyncSession = Depends(get_session),
):
    return await KnowledgeService(session).list_articles(category, status, vehicle_model_id)


@router.post("/articles", response_model=ArticleOut, status_code=201)
async def create_article(
    body: ArticleCreate, user: User = Depends(editor), session: AsyncSession = Depends(get_session)
):
    return await KnowledgeService(session).create(
        KnowledgeBaseArticle, _payload(body, exclude_unset=False), user.id
    )


@router.patch("/articles/{item_id}", response_model=ArticleOut)
async def update_article(
    item_id: uuid.UUID,
    body: ArticleUpdate,
    user: User = Depends(editor),
    session: AsyncSession = Depends(get_session),
):
    return await KnowledgeService(session).update(
        KnowledgeBaseArticle, item_id, _payload(body), user.id, "Artikel"
    )


@router.delete("/articles/{item_id}", status_code=204)
async def delete_article(
    item_id: uuid.UUID, user: User = Depends(editor), session: AsyncSession = Depends(get_session)
) -> None:
    await KnowledgeService(session).delete(KnowledgeBaseArticle, item_id, user.id, "Artikel")


# ---------------------------------------------------------------- preview
@router.get("/ai-context", response_model=KnowledgePreview)
async def ai_context_preview(
    vehicle: str | None = None,
    _: User = Depends(reader),
    session: AsyncSession = Depends(get_session),
):
    """Shows exactly which approved knowledge the AI receives."""
    ctx = await KnowledgeService(session).build_context(vehicle)
    return KnowledgePreview(vehicle_models=ctx.vehicle_models, text=ctx.text)
