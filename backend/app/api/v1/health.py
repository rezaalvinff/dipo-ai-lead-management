import logging

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.api.deps import get_ctx
from app.core.context import AppContext
from app.core.database import check_database
from app.core.redis import check_redis

router = APIRouter(tags=["system"])
logger = logging.getLogger(__name__)


@router.get("/health")
async def health(ctx: AppContext = Depends(get_ctx)) -> JSONResponse:
    checks: dict[str, str] = {}
    for name, check in (
        ("database", lambda: check_database(ctx.engine)),
        ("redis", lambda: check_redis(ctx.redis)),
    ):
        try:
            await check()
            checks[name] = "ok"
        except Exception as exc:  # noqa: BLE001 - report any failure
            logger.warning("Health check %s failed: %s", name, exc)
            checks[name] = "error"

    healthy = all(v == "ok" for v in checks.values())
    s = ctx.settings
    return JSONResponse(
        status_code=200 if healthy else 503,
        content={
            "status": "ok" if healthy else "degraded",
            "app_env": s.app_env,
            "simulator_enabled": s.simulator_enabled,
            "providers": {
                "whatsapp": s.whatsapp_provider,
                "ai": s.ai_provider,
                "conversion": s.conversion_provider,
                "job_queue": s.job_queue,
            },
            "checks": checks,
        },
    )
