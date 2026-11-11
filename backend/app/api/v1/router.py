from fastapi import APIRouter

from app.api.v1 import admin_queue, auth, conversations, dashboard, health, inbox, knowledge, routing, settings, simulator, webhooks
from app.core.config import Settings


def build_api_router(app_settings: Settings) -> APIRouter:
    router = APIRouter(prefix="/api/v1")
    router.include_router(health.router)
    router.include_router(auth.router)
    router.include_router(conversations.router)
    router.include_router(webhooks.router)
    router.include_router(knowledge.router)
    router.include_router(settings.router)
    router.include_router(routing.router)
    router.include_router(admin_queue.router)
    router.include_router(inbox.router)
    router.include_router(dashboard.router)
    # Simulator routes do not even exist in production.
    if app_settings.simulator_enabled and not app_settings.is_production:
        router.include_router(simulator.router)
    return router
