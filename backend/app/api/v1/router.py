from fastapi import APIRouter

from app.api.v1 import auth, conversations, health, simulator, webhooks
from app.core.config import Settings


def build_api_router(settings: Settings) -> APIRouter:
    router = APIRouter(prefix="/api/v1")
    router.include_router(health.router)
    router.include_router(auth.router)
    router.include_router(conversations.router)
    router.include_router(webhooks.router)
    # Simulator routes do not even exist in production.
    if settings.simulator_enabled and not settings.is_production:
        router.include_router(simulator.router)
    return router
